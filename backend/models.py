"""
Pydantic models for TreeHacks 2026 backend.
Used for request/response validation and type safety.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from enum import Enum


# =====================================================
# ENUMS
# =====================================================

class ProjectType(str, Enum):
    """Types of projects."""
    BUG = "bug"
    FEATURE = "feature"
    ENHANCEMENT = "enhancement"
    QUESTION = "question"


class ProjectStatus(str, Enum):
    """Status workflow for projects."""
    PENDING = "pending"
    PLANNING = "planning"
    PROVISIONING = "provisioning"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CLOSED = "closed"


class LogLevel(str, Enum):
    """Log levels for execution logs."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    DEBUG = "debug"


class NotificationType(str, Enum):
    """Notification types."""
    ACKNOWLEDGE = "acknowledge"
    CLARIFICATION = "clarification"
    COMPLETION = "completion"
    ERROR = "error"


# =====================================================
# DATABASE MODELS (matching Supabase schema)
# =====================================================

class Tweet(BaseModel):
    """Tweet model."""
    id: UUID
    created_at: datetime
    tweet_id: str
    tweet_text: str
    tweet_author_id: str
    tweet_author_username: str
    tweet_created_at: datetime
    likes_count: int = 0
    retweets_count: int = 0
    replies_count: int = 0
    embedding: Optional[List[float]] = None
    processed: bool = False
    sentiment_score: Optional[float] = None
    project_id: UUID


class Project(BaseModel):
    """Project (clustered tweets)."""
    id: UUID
    created_at: datetime
    updated_at: datetime
    title: str
    description: Optional[str] = None
    ticket_type: ProjectType = ProjectType.FEATURE
    cluster_centroid: Optional[List[float]] = None
    tweet_count: int = 0
    severity_score: int = 0
    status: ProjectStatus = ProjectStatus.PENDING
    github_issue_number: Optional[int] = None
    github_issue_url: Optional[str] = None
    github_pr_number: Optional[int] = None
    github_pr_url: Optional[str] = None
    repo_config_id: UUID
    plan_id: Optional[UUID] = None


class Plan(BaseModel):
    """Implementation plan."""
    id: UUID
    created_at: datetime
    updated_at: datetime
    title: str
    content: str
    approved: bool = False
    approved_by: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    version: int = 1
    parent_plan_id: Optional[UUID] = None
    project_id: UUID


class ExecutionLog(BaseModel):
    """Execution log entry."""
    id: UUID
    created_at: datetime
    log_level: LogLevel = LogLevel.INFO
    message: str
    metadata: dict = Field(default_factory=dict)
    step_name: Optional[str] = None
    project_id: UUID


class RepoConfig(BaseModel):
    """Repository configuration."""
    id: UUID
    created_at: datetime
    updated_at: datetime
    github_owner: str
    github_repo: str
    github_branch: str = "main"
    x_account_handle: str
    x_keywords: List[str] = Field(default_factory=list)
    local_agent_enabled: bool = False
    auto_create_issues: bool = False
    auto_create_prs: bool = False
    user_id: Optional[UUID] = None
    github_token: Optional[str] = None
    test_command: Optional[str] = None
    build_command: Optional[str] = None
    lint_command: Optional[str] = None


class Account(BaseModel):
    """Account-level profile and defaults."""
    id: UUID
    created_at: datetime
    updated_at: datetime
    x_account_handle: str
    github_owner: str
    github_repo: str
    github_branch: str = "main"
    default_repo_config_id: Optional[UUID] = None


class Notification(BaseModel):
    """Notification model."""
    id: UUID
    created_at: datetime
    sent_at: Optional[datetime] = None
    notification_type: NotificationType
    message: str
    tweet_id: Optional[str] = None
    recipient_tweet_id: Optional[str] = None
    sent: bool = False
    error_message: Optional[str] = None
    project_id: UUID


# =====================================================
# MODAL SANDBOX MODEL (replaces CoderSession)
# =====================================================

class ModalSandbox(BaseModel):
    """
    Modal sandbox model for tracking cloud VM coding sessions.
    Replaces the old CoderSession (local Grok CLI).
    """
    id: UUID
    created_at: datetime
    completed_at: Optional[datetime] = None
    sandbox_id: str  # Modal sandbox identifier
    status: str  # active, completed, failed, terminated
    branch_name: Optional[str] = None
    pr_number: Optional[int] = None
    pr_url: Optional[str] = None
    test_results: Optional[dict] = None
    build_results: Optional[dict] = None
    lint_results: Optional[dict] = None
    review_results: Optional[dict] = None
    project_id: UUID


# =====================================================
# REQUEST/RESPONSE MODELS
# =====================================================

class UpdateProjectStatusRequest(BaseModel):
    """Request to update project status."""
    status: ProjectStatus
    metadata: dict = Field(default_factory=dict)


class CreateExecutionLogRequest(BaseModel):
    """Request to create execution log."""
    log_level: LogLevel = LogLevel.INFO
    message: str
    step_name: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class CreateTweetRequest(BaseModel):
    """Request to create a new tweet."""
    tweet_id: str
    tweet_text: str
    tweet_author_id: str
    tweet_author_username: str
    tweet_created_at: datetime
    likes_count: int = 0
    retweets_count: int = 0
    replies_count: int = 0
    project_id: UUID


class CreateProjectRequest(BaseModel):
    """Request to create a project."""
    title: str
    description: Optional[str] = None
    ticket_type: ProjectType = ProjectType.FEATURE
    repo_config_id: UUID


class CreateRepoConfigRequest(BaseModel):
    """Request to create a repo config."""
    github_owner: str
    github_repo: str
    github_branch: str = "main"
    x_account_handle: str
    x_keywords: List[str] = Field(default_factory=list)
    local_agent_enabled: bool = False
    auto_create_issues: bool = False
    auto_create_prs: bool = False
    user_id: Optional[UUID] = None


class GeneratePlanResponse(BaseModel):
    """Response from plan generation."""
    status: str
    message: str
    plan_id: Optional[UUID] = None


class ApprovalResponse(BaseModel):
    """Response from plan approval."""
    status: str
    plan_id: UUID
    project_id: UUID


class ProjectWithTweets(BaseModel):
    """Project with related tweets."""
    project: Project
    tweets: List[Tweet]
    plan: Optional[Plan] = None


class ExecuteCoderRequest(BaseModel):
    """Request to execute coding workflow."""
    project_id: UUID


class CoderStatusResponse(BaseModel):
    """Response for coder status check."""
    status: str
    current_step: Optional[str] = None
    progress: float = 0.0
    logs: List[ExecutionLog] = Field(default_factory=list)
