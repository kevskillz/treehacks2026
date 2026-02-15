"""
Notification assistant for a developer building projects.

Polls the projects table for:
1. New projects (sends feedback notification)
2. Status transitions: planning → provisioning → executing → completed
"""

import os
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client, Client
from poke_notifier import PokeNotifier

# Load environment variables from root .env file
root_dir = Path(__file__).resolve().parent.parent.parent
env_path = root_dir / ".env"
load_dotenv(dotenv_path=env_path)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "10"))


def get_supabase_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY env vars must be set")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ── 1. New projects ──────────────────────────────────────────────────

def poll_new_projects(supabase: Client, poke_notifier: PokeNotifier, since: str,
                      tracked_projects: dict):
    """Detect new projects and send feedback notification."""
    try:
        response = (
            supabase.table("projects")
            .select("*")
            .gt("created_at", since)
            .order("created_at", desc=False)
            .execute()
        )

        for project in response.data:
            pid = project.get("id")
            title = project.get("title", "Untitled feedback")
            description = project.get("description", "No description provided")
            status = project.get("status", "pending")

            if pid not in tracked_projects:
                tracked_projects[pid] = status
                logger.info("New project %s created (status=%s)", pid, status)

                message = (
                    f"New feedback: {title}\n\n"
                    f"{description}\n\n"
                    f"Do you want to build a plan for this?"
                )

                instructions = (
                    f"\n\n---\nResponse handling:\n"
                    f"- If user says \"yes\": "
                    f"Set status = \"planning\" in the projects table for project id = {pid}.\n"
                    f"- If user says \"no\": "
                    f"Keep status as \"pending\" in the projects table for project id = {pid}."
                )

                poke_notifier.notify_poke_assistant(
                    message=message + instructions)
                logger.info("New project notification sent for %s", pid)
    except Exception as e:
        logger.error("Error polling new projects: %s", e)


# ── 2. Status-change notifications ──────────────────────────────────

def build_transition_message(supabase: Client, project: dict, pid: str,
                             old_status: str, new_status: str) -> str | None:
    """Return the Poke message for a given status transition."""

    # planning → provisioning : plan created, ask to execute
    if old_status == "planning" and new_status == "provisioning":
        github_issue_url = project.get("github_issue_url", "N/A")

        # Fetch plan content
        plan_content = None
        plan_id = project.get("plan_id")
        if plan_id:
            try:
                plan_resp = (
                    supabase.table("plans")
                    .select("content")
                    .eq("id", plan_id)
                    .execute()
                )
                if plan_resp.data:
                    plan_content = plan_resp.data[0].get("content")
            except Exception as e:
                logger.error("Error fetching plan %s: %s", plan_id, e)

        plan_content = plan_content or "No plan content available"

        message = (
            f"Issue created at: {github_issue_url}"
            f"Plan: {plan_content}\n\n"
            f"Do you want to execute this plan?"
        )
        instructions = (
            f"\n\n---\nResponse handling:\n"
            f"- If user says \"yes\": "
            f"Set status = \"executing\" in the projects table for project id = {pid}.\n"
            f"- If user says \"no\": Keep status the same."
        )
        return message + instructions

    # provisioning → executing : execution started
    if old_status == "provisioning" and new_status == "executing":
        title = project.get("title", "Untitled")
        return f"Plan execution has started for \"{title}\"."

    # executing → completed : done, share PR link
    if old_status == "executing" and new_status == "completed":
        github_pr_url = project.get("github_pr_url", "N/A")
        return (
            f"Plan has been executed and built.\n"
            f"Github PR link: {github_pr_url}"
        )

    # Any other transition
    return f"Project status changed from \"{old_status}\" to \"{new_status}\"."


def poll_status_changes(supabase: Client, poke_notifier: PokeNotifier,
                        tracked_projects: dict):
    """Fetch ALL projects in one query and check for status changes."""
    if not tracked_projects:
        logger.debug("No tracked projects, skipping status check")
        return

    try:
        # Single batch query for all tracked projects
        response = (
            supabase.table("projects")
            .select("*")
            .in_("id", list(tracked_projects.keys()))
            .execute()
        )
        logger.debug("Status poll returned %d projects", len(response.data))

        for project in response.data:
            pid = project.get("id")
            current_status = project.get("status")
            last_status = tracked_projects.get(pid)

            if current_status == last_status:
                continue

            # Status changed — build and send notification
            logger.info("Status change detected for project %s: %s → %s",
                        pid, last_status, current_status)

            msg = build_transition_message(supabase, project, pid,
                                           last_status, current_status)
            if msg:
                poke_notifier.notify_poke_assistant(message=msg)
                logger.info("Poke notification sent for %s → %s",
                            last_status, current_status)

            tracked_projects[pid] = current_status

    except Exception as e:
        logger.error("Error polling project statuses: %s", e)


# ── Main loop ────────────────────────────────────────────────────────

def seed_tracked_projects(supabase: Client) -> dict[str, str]:
    """Load all existing projects so we can detect status changes from the start."""
    tracked: dict[str, str] = {}
    try:
        response = supabase.table("projects").select("id, status").execute()
        for project in response.data:
            tracked[project["id"]] = project.get("status", "pending")
        logger.info("Seeded %d existing projects for tracking", len(tracked))
    except Exception as e:
        logger.error("Error seeding tracked projects: %s", e)
    return tracked


def poll_and_notify():
    """Continuously poll Supabase projects table and send Poke notifications."""
    supabase = get_supabase_client()
    poke_notifier = PokeNotifier()

    last_checked = datetime.now(timezone.utc) - \
        timedelta(seconds=POLL_INTERVAL_SECONDS)

    # {project_id: last_known_status} — seed with all existing projects
    tracked_projects = seed_tracked_projects(supabase)

    logger.info("Starting Supabase poller (interval=%ds, tracking %d projects)",
                POLL_INTERVAL_SECONDS, len(tracked_projects))

    while True:
        since = last_checked.isoformat()
        now = datetime.now(timezone.utc)

        # 1. Detect new projects and send feedback notifications
        poll_new_projects(supabase, poke_notifier, since, tracked_projects)

        # 2. Check every tracked project for status transitions (single query)
        poll_status_changes(supabase, poke_notifier, tracked_projects)

        last_checked = now
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    poll_and_notify()
