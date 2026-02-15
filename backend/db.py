"""
Database functions for Supabase interactions.
All CRUD operations and queries go here.
"""

from supabase import Client
from typing import List, Optional, Dict, Any
from uuid import UUID
from models import (
    Tweet,
    Project,
    Plan,
    ExecutionLog,
    RepoConfig,
    Account,
    Notification,
    ModalSandbox,
    ProjectStatus,
    LogLevel,
    NotificationType,
)
import logging

logger = logging.getLogger(__name__)


# =====================================================
# TWEET OPERATIONS
# =====================================================


def get_tweet(supabase: Client, tweet_id: UUID) -> Optional[Tweet]:
    """Get a single tweet by its UUID primary key."""
    result = (
        supabase.table("tweets")
        .select("*")
        .eq("id", str(tweet_id))
        .single()
        .execute()
    )
    return Tweet(**result.data) if result.data else None


def get_tweet_by_tweet_id(supabase: Client, tweet_id: str) -> Optional[Tweet]:
    """Get a single tweet by its X/Twitter tweet_id (text field)."""
    result = (
        supabase.table("tweets")
        .select("*")
        .eq("tweet_id", tweet_id)
        .single()
        .execute()
    )
    return Tweet(**result.data) if result.data else None


def get_tweets_by_project(supabase: Client, project_id: UUID) -> List[Tweet]:
    """Get all tweets for a project."""
    result = (
        supabase.table("tweets")
        .select("*")
        .eq("project_id", str(project_id))
        .execute()
    )
    return [Tweet(**tweet) for tweet in result.data] if result.data else []


def create_tweet(supabase: Client, tweet_data: Dict[str, Any]) -> Tweet:
    """Create a new tweet."""
    result = supabase.table("tweets").insert(tweet_data).execute()
    return Tweet(**result.data[0])


def update_tweet(
    supabase: Client, tweet_id: UUID, updates: Dict[str, Any]
) -> Tweet:
    """Update a tweet."""
    result = (
        supabase.table("tweets")
        .update(updates)
        .eq("id", str(tweet_id))
        .execute()
    )
    return Tweet(**result.data[0])


def assign_tweet_to_project(
    supabase: Client,
    tweet_id: UUID,
    project_id: UUID,
    processed: bool = True,
) -> None:
    """Assign a tweet to a project."""
    updates: Dict[str, Any] = {"project_id": str(project_id)}
    if processed:
        updates["processed"] = True
    supabase.table("tweets").update(updates).eq("id", str(tweet_id)).execute()


# =====================================================
# PROJECT OPERATIONS
# =====================================================


def get_project(supabase: Client, project_id: UUID) -> Optional[Project]:
    """Get a single project by ID."""
    result = (
        supabase.table("projects")
        .select("*")
        .eq("id", str(project_id))
        .single()
        .execute()
    )
    return Project(**result.data) if result.data else None


def get_projects_by_status(
    supabase: Client, status: ProjectStatus
) -> List[Project]:
    """Get all projects with a specific status."""
    result = (
        supabase.table("projects")
        .select("*")
        .eq("status", status.value)
        .execute()
    )
    return [Project(**p) for p in result.data] if result.data else []


def get_projects_by_repo(
    supabase: Client, repo_config_id: UUID
) -> List[Project]:
    """Get all projects for a repository."""
    result = (
        supabase.table("projects")
        .select("*")
        .eq("repo_config_id", str(repo_config_id))
        .order("severity_score", desc=True)
        .execute()
    )
    return [Project(**p) for p in result.data] if result.data else []


def get_or_create_active_project(
    supabase: Client, repo_config_id: UUID
) -> Project:
    """
    Get the active (pending) project for a repo, or create one.
    """
    result = (
        supabase.table("projects")
        .select("*")
        .eq("repo_config_id", str(repo_config_id))
        .eq("status", "pending")
        .limit(1)
        .execute()
    )

    if result.data and len(result.data) > 0:
        logger.info(f"Found existing active project for repo {repo_config_id}")
        return Project(**result.data[0])

    logger.info(f"Creating new pending project for repo {repo_config_id}")
    project_data = {
        "title": "Pending user feedback",
        "description": "Aggregating user feedback...",
        "ticket_type": "feature",
        "repo_config_id": str(repo_config_id),
        "status": "pending",
        "tweet_count": 0,
        "severity_score": 0,
    }
    return create_project(supabase, project_data)


def create_project(
    supabase: Client, project_data: Dict[str, Any]
) -> Project:
    """Create a new project."""
    result = supabase.table("projects").insert(project_data).execute()
    return Project(**result.data[0])


def update_project_fields(
    supabase: Client, project_id: UUID, updates: Dict[str, Any]
) -> Project:
    """Update multiple project fields at once."""
    from datetime import datetime, timezone

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = (
        supabase.table("projects")
        .update(updates)
        .eq("id", str(project_id))
        .execute()
    )
    return Project(**result.data[0])


def update_project_status(
    supabase: Client,
    project_id: UUID,
    status: ProjectStatus,
    metadata: Optional[Dict[str, Any]] = None,
) -> Project:
    """Update project status and optionally add metadata."""
    from datetime import datetime, timezone

    updates: Dict[str, Any] = {
        "status": status.value,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if metadata:
        for key in (
            "github_pr_url",
            "github_pr_number",
            "github_issue_url",
            "github_issue_number",
        ):
            if key in metadata:
                updates[key] = metadata[key]

    result = (
        supabase.table("projects")
        .update(updates)
        .eq("id", str(project_id))
        .execute()
    )
    return Project(**result.data[0])


def get_project_with_tweets(
    supabase: Client, project_id: UUID
) -> Optional[Dict[str, Any]]:
    """Get a project with all related tweets and plan."""
    project = get_project(supabase, project_id)
    if not project:
        return None

    tweets = get_tweets_by_project(supabase, project_id)
    plan = None
    if project.plan_id:
        plan = get_plan(supabase, project.plan_id)

    return {"project": project, "tweets": tweets, "plan": plan}


# =====================================================
# PLAN OPERATIONS
# =====================================================


def get_plan(supabase: Client, plan_id: UUID) -> Optional[Plan]:
    """Get a single plan by ID."""
    result = (
        supabase.table("plans")
        .select("*")
        .eq("id", str(plan_id))
        .single()
        .execute()
    )
    return Plan(**result.data) if result.data else None


def create_plan(supabase: Client, plan_data: Dict[str, Any]) -> Plan:
    """Create a new plan."""
    result = supabase.table("plans").insert(plan_data).execute()
    return Plan(**result.data[0])


def approve_plan(
    supabase: Client,
    plan_id: UUID,
    user_id: Optional[UUID] = None,
    content: Optional[str] = None,
) -> Plan:
    """Approve a plan and optionally update its content."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    updates: Dict[str, Any] = {
        "approved": True,
        "approved_at": now,
        "updated_at": now,
    }
    if user_id:
        updates["approved_by"] = str(user_id)
    if content is not None:
        updates["content"] = content

    result = (
        supabase.table("plans")
        .update(updates)
        .eq("id", str(plan_id))
        .execute()
    )
    return Plan(**result.data[0])


def get_plan_with_project(
    supabase: Client, plan_id: UUID
) -> Optional[Dict[str, Any]]:
    """Get a plan with its associated project."""
    plan = get_plan(supabase, plan_id)
    if not plan:
        return None
    project = get_project(supabase, plan.project_id)
    return {"plan": plan, "project": project}


# =====================================================
# EXECUTION LOG OPERATIONS
# =====================================================


def create_execution_log(
    supabase: Client,
    project_id: UUID,
    message: str,
    log_level: LogLevel = LogLevel.INFO,
    step_name: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> ExecutionLog:
    """Create an execution log entry."""
    log_data = {
        "project_id": str(project_id),
        "message": message,
        "log_level": log_level.value,
        "step_name": step_name,
        "metadata": metadata or {},
    }
    result = supabase.table("execution_logs").insert(log_data).execute()
    return ExecutionLog(**result.data[0])


def get_execution_logs(
    supabase: Client, project_id: UUID
) -> List[ExecutionLog]:
    """Get all execution logs for a project."""
    result = (
        supabase.table("execution_logs")
        .select("*")
        .eq("project_id", str(project_id))
        .order("created_at", desc=True)
        .execute()
    )
    return [ExecutionLog(**log) for log in result.data] if result.data else []


# =====================================================
# REPO CONFIG OPERATIONS
# =====================================================


def get_repo_config(
    supabase: Client, repo_config_id: UUID
) -> Optional[RepoConfig]:
    """Get a repository configuration."""
    result = (
        supabase.table("repo_configs")
        .select("*")
        .eq("id", str(repo_config_id))
        .single()
        .execute()
    )
    return RepoConfig(**result.data) if result.data else None


def get_repo_configs_by_user(
    supabase: Client, user_id: UUID
) -> List[RepoConfig]:
    """Get all repo configs for a user."""
    result = (
        supabase.table("repo_configs")
        .select("*")
        .eq("user_id", str(user_id))
        .execute()
    )
    return [RepoConfig(**c) for c in result.data] if result.data else []


def create_repo_config(
    supabase: Client, repo_config_data: Dict[str, Any]
) -> RepoConfig:
    """Create a new repository configuration."""
    result = supabase.table("repo_configs").insert(repo_config_data).execute()
    return RepoConfig(**result.data[0])


# =====================================================
# ACCOUNT OPERATIONS
# =====================================================


def get_account(supabase: Client, user_id: UUID) -> Optional[Account]:
    """Fetch account profile by user ID."""
    result = (
        supabase.table("accounts")
        .select("*")
        .eq("id", str(user_id))
        .single()
        .execute()
    )
    return Account(**result.data) if result.data else None


def create_account(
    supabase: Client, account_data: Dict[str, Any]
) -> Account:
    """Create a new account profile."""
    result = supabase.table("accounts").insert(account_data).execute()
    return Account(**result.data[0])


def get_default_repo_config_id_for_user(
    supabase: Client, user_id: UUID
) -> Optional[UUID]:
    """Get the default repo_config_id for a user."""
    account = get_account(supabase, user_id)
    if account and account.default_repo_config_id:
        return account.default_repo_config_id
    configs = get_repo_configs_by_user(supabase, user_id)
    return configs[0].id if configs else None


# =====================================================
# VECTOR SEARCH / CLUSTERING
# =====================================================


def find_similar_projects(
    supabase: Client,
    embedding: List[float],
    repo_config_id: UUID,
    similarity_threshold: float = 0.85,
    max_results: int = 5,
) -> List[Dict[str, Any]]:
    """Find similar projects using vector similarity search."""
    result = (
        supabase.rpc(
            "find_similar_projects",
            {
                "input_embedding": embedding,
                "repo_id": str(repo_config_id),
                "similarity_threshold": similarity_threshold,
                "max_results": max_results,
            },
        ).execute()
    )
    return result.data if result.data else []


def update_cluster_centroid(supabase: Client, project_id: UUID) -> None:
    """Update the cluster centroid for a project based on its tweets."""
    supabase.rpc(
        "update_cluster_centroid", {"project_id": str(project_id)}
    ).execute()


def calculate_severity_score(supabase: Client, project_id: UUID) -> int:
    """Calculate severity score for a project."""
    tweets = get_tweets_by_project(supabase, project_id)
    if not tweets:
        return 0
    total_likes = sum(t.likes_count for t in tweets)
    total_retweets = sum(t.retweets_count for t in tweets)
    tweet_count = len(tweets)
    return (tweet_count * 10) + (total_likes * 2) + (total_retweets * 5)


# =====================================================
# NOTIFICATION OPERATIONS
# =====================================================


def create_notification(
    supabase: Client,
    project_id: UUID,
    notification_type: NotificationType,
    message: str,
    recipient_tweet_id: Optional[str] = None,
) -> Notification:
    """Create a notification."""
    notification_data = {
        "project_id": str(project_id),
        "notification_type": notification_type.value,
        "message": message,
        "recipient_tweet_id": recipient_tweet_id,
    }
    result = (
        supabase.table("notifications").insert(notification_data).execute()
    )
    return Notification(**result.data[0])


def get_notifications_by_project(
    supabase: Client, project_id: UUID
) -> List[Notification]:
    """Get all notifications for a project."""
    result = (
        supabase.table("notifications")
        .select("*")
        .eq("project_id", str(project_id))
        .order("created_at", desc=True)
        .execute()
    )
    return [Notification(**n) for n in result.data] if result.data else []


def mark_notification_sent(
    supabase: Client, notification_id: UUID, tweet_id: str
) -> Notification:
    """Mark a notification as sent."""
    from datetime import datetime, timezone

    updates = {
        "sent": True,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "tweet_id": tweet_id,
    }
    result = (
        supabase.table("notifications")
        .update(updates)
        .eq("id", str(notification_id))
        .execute()
    )
    return Notification(**result.data[0])


def mark_notification_failed(
    supabase: Client, notification_id: UUID, error_message: str
) -> Notification:
    """Mark a notification as failed."""
    updates = {"sent": False, "error_message": error_message}
    result = (
        supabase.table("notifications")
        .update(updates)
        .eq("id", str(notification_id))
        .execute()
    )
    return Notification(**result.data[0])


# =====================================================
# HELPER FUNCTIONS
# =====================================================


def update_project_severity(supabase: Client, project_id: UUID) -> None:
    """Recalculate and update the severity score for a project."""
    severity = calculate_severity_score(supabase, project_id)
    supabase.table("projects").update({"severity_score": severity}).eq(
        "id", str(project_id)
    ).execute()


# =====================================================
# MODAL SANDBOX OPERATIONS (replaces coder_sessions)
# =====================================================


def create_modal_sandbox(
    supabase: Client, sandbox_data: Dict[str, Any]
) -> ModalSandbox:
    """Create a new modal sandbox record."""
    result = (
        supabase.table("coder_sessions").insert(sandbox_data).execute()
    )
    return ModalSandbox(**result.data[0])


def update_modal_sandbox(
    supabase: Client, sandbox_id: UUID, updates: Dict[str, Any]
) -> ModalSandbox:
    """Update a modal sandbox record."""
    from datetime import datetime, timezone

    if "completed_at" in updates and updates["completed_at"] is None:
        updates["completed_at"] = datetime.now(timezone.utc).isoformat()
    result = (
        supabase.table("coder_sessions")
        .update(updates)
        .eq("id", str(sandbox_id))
        .execute()
    )
    return ModalSandbox(**result.data[0])


def get_modal_sandbox(
    supabase: Client, sandbox_id: UUID
) -> Optional[ModalSandbox]:
    """Get a modal sandbox by ID."""
    result = (
        supabase.table("coder_sessions")
        .select("*")
        .eq("id", str(sandbox_id))
        .single()
        .execute()
    )
    return ModalSandbox(**result.data) if result.data else None


def get_modal_sandbox_by_project(
    supabase: Client, project_id: UUID
) -> Optional[ModalSandbox]:
    """Get the most recent modal sandbox for a project."""
    result = (
        supabase.table("coder_sessions")
        .select("*")
        .eq("project_id", str(project_id))
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return ModalSandbox(**result.data[0]) if result.data else None


def get_modal_sandboxes_by_status(
    supabase: Client, status: str
) -> List[ModalSandbox]:
    """Get all modal sandboxes with a specific status."""
    result = (
        supabase.table("coder_sessions")
        .select("*")
        .eq("status", status)
        .execute()
    )
    return [ModalSandbox(**s) for s in result.data] if result.data else []
