"""
Database functions for Supabase interactions.
"""

from supabase import Client
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from models import (
    UserFeedback,
    Project,
    Plan,
    ExecutionLog,
    RepoConfig,
    Account,
    Notification,
    CoderSession,
    ProjectStatus,
    LogLevel,
    NotificationType,
)

import logging

logger = logging.getLogger(__name__)


# ---------- User feedback (from Twilio SMS once Claude has determined it) ----------
def create_feedback(
    supabase: Client,
    phone_number: str,
    summary: str,
    raw_messages: Optional[str] = None,
) -> UserFeedback:
    """Store feedback once Twilio handler has determined it from the user."""
    data = {
        "phone_number": phone_number,
        "summary": summary,
        "raw_messages": raw_messages,
    }
    result = supabase.table("user_feedback").insert(data).execute()
    return UserFeedback(**result.data[0])


def get_feedback_by_phone(supabase: Client, phone_number: str) -> List[UserFeedback]:
    """List feedback entries for a phone number (most recent first)."""
    result = (
        supabase.table("user_feedback")
        .select("*")
        .eq("phone_number", phone_number)
        .order("created_at", desc=True)
        .execute()
    )
    return [UserFeedback(**f) for f in result.data] if result.data else []


def list_feedback(supabase: Client, limit: int = 100) -> List[UserFeedback]:
    """List recent feedback across all users."""
    result = (
        supabase.table("user_feedback")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return [UserFeedback(**f) for f in result.data] if result.data else []


# ---------- Projects ----------
def get_project(supabase: Client, project_id: UUID) -> Optional[Project]:
    result = supabase.table("projects").select("*").eq("id", str(project_id)).single().execute()
    return Project(**result.data) if result.data else None


def get_projects_by_repo(supabase: Client, repo_config_id: UUID) -> List[Project]:
    result = (
        supabase.table("projects")
        .select("*")
        .eq("repo_config_id", str(repo_config_id))
        .order("severity_score", desc=True)
        .execute()
    )
    return [Project(**p) for p in result.data] if result.data else []


def get_or_create_active_project(supabase: Client, repo_config_id: UUID) -> Project:
    """Get existing pending project for repo or create one. Data from DB only (no tweet tracking)."""
    result = (
        supabase.table("projects")
        .select("*")
        .eq("repo_config_id", str(repo_config_id))
        .eq("status", "pending")
        .limit(1)
        .execute()
    )
    if result.data and len(result.data) > 0:
        return Project(**result.data[0])
    project_data = {
        "title": "Pending feedback",
        "description": "",
        "ticket_type": "feature",
        "repo_config_id": str(repo_config_id),
        "status": "pending",
        "severity_score": 0,
    }
    return create_project(supabase, project_data)


def create_project(supabase: Client, project_data: Dict[str, Any]) -> Project:
    result = supabase.table("projects").insert(project_data).execute()
    return Project(**result.data[0])


def update_project_fields(
    supabase: Client, project_id: UUID, updates: Dict[str, Any]
) -> Project:
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = supabase.table("projects").update(updates).eq("id", str(project_id)).execute()
    return Project(**result.data[0])


def update_project_status(
    supabase: Client,
    project_id: UUID,
    status: ProjectStatus,
    metadata: Optional[Dict[str, Any]] = None,
) -> Project:
    updates = {
        "status": status.value,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if metadata:
        for key in ("github_pr_url", "github_pr_number", "github_issue_url", "github_issue_number"):
            if key in metadata:
                updates[key] = metadata[key]
    result = supabase.table("projects").update(updates).eq("id", str(project_id)).execute()
    return Project(**result.data[0])


def get_project_with_plan(supabase: Client, project_id: UUID) -> Optional[Dict[str, Any]]:
    """Get project and its plan. All data from DB (no tweet tracking)."""
    project = get_project(supabase, project_id)
    if not project:
        return None
    plan = get_plan(supabase, project.plan_id) if project.plan_id else None
    return {"project": project, "plan": plan}


def get_plan(supabase: Client, plan_id: UUID) -> Optional[Plan]:
    result = supabase.table("plans").select("*").eq("id", str(plan_id)).single().execute()
    return Plan(**result.data) if result.data else None


def create_plan(supabase: Client, plan_data: Dict[str, Any]) -> Plan:
    result = supabase.table("plans").insert(plan_data).execute()
    return Plan(**result.data[0])


def approve_plan(
    supabase: Client,
    plan_id: UUID,
    user_id: Optional[UUID] = None,
    content: Optional[str] = None,
) -> Plan:
    now = datetime.now(timezone.utc).isoformat()
    updates = {"approved": True, "approved_at": now, "updated_at": now}
    if user_id:
        updates["approved_by"] = str(user_id)
    if content is not None:
        updates["content"] = content
    result = supabase.table("plans").update(updates).eq("id", str(plan_id)).execute()
    return Plan(**result.data[0])


def get_plan_with_project(supabase: Client, plan_id: UUID) -> Optional[Dict[str, Any]]:
    plan = get_plan(supabase, plan_id)
    if not plan:
        return None
    project = get_project(supabase, plan.project_id)
    return {"plan": plan, "project": project}


def create_execution_log(
    supabase: Client,
    project_id: UUID,
    message: str,
    log_level: LogLevel = LogLevel.INFO,
    step_name: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> ExecutionLog:
    log_data = {
        "project_id": str(project_id),
        "message": message,
        "log_level": log_level.value,
        "step_name": step_name,
        "metadata": metadata or {},
    }
    result = supabase.table("execution_logs").insert(log_data).execute()
    return ExecutionLog(**result.data[0])


def get_execution_logs(supabase: Client, project_id: UUID) -> List[ExecutionLog]:
    result = (
        supabase.table("execution_logs")
        .select("*")
        .eq("project_id", str(project_id))
        .order("created_at", desc=True)
        .execute()
    )
    return [ExecutionLog(**log) for log in result.data] if result.data else []


def get_repo_config(supabase: Client, repo_config_id: UUID) -> Optional[RepoConfig]:
    result = (
        supabase.table("repo_configs").select("*").eq("id", str(repo_config_id)).single().execute()
    )
    return RepoConfig(**result.data) if result.data else None


def create_repo_config(supabase: Client, repo_config_data: Dict[str, Any]) -> RepoConfig:
    result = supabase.table("repo_configs").insert(repo_config_data).execute()
    return RepoConfig(**result.data[0])


def get_account(supabase: Client, user_id: UUID) -> Optional[Account]:
    result = supabase.table("accounts").select("*").eq("id", str(user_id)).single().execute()
    return Account(**result.data) if result.data else None


def create_notification(
    supabase: Client,
    project_id: UUID,
    notification_type: NotificationType,
    message: str,
    recipient_tweet_id: Optional[str] = None,
) -> Notification:
    notification_data = {
        "project_id": str(project_id),
        "notification_type": notification_type.value,
        "message": message,
        "recipient_tweet_id": recipient_tweet_id,
    }
    result = supabase.table("notifications").insert(notification_data).execute()
    return Notification(**result.data[0])


def create_coder_session(supabase: Client, session_data: Dict[str, Any]) -> CoderSession:
    result = supabase.table("coder_sessions").insert(session_data).execute()
    return CoderSession(**result.data[0])


def update_coder_session(
    supabase: Client, session_id: UUID, updates: Dict[str, Any]
) -> CoderSession:
    if "completed_at" in updates and updates["completed_at"] is None:
        updates["completed_at"] = datetime.now(timezone.utc).isoformat()
    result = supabase.table("coder_sessions").update(updates).eq("id", str(session_id)).execute()
    return CoderSession(**result.data[0])


def get_coder_session_by_project(supabase: Client, project_id: UUID) -> Optional[CoderSession]:
    result = (
        supabase.table("coder_sessions")
        .select("*")
        .eq("project_id", str(project_id))
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return CoderSession(**result.data[0]) if result.data else None
