"""
Pydantic models for Vector backend.
Used for request/response validation and type safety.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from enum import Enum


class ProjectType(str, Enum):
    BUG = "bug"
    FEATURE = "feature"
    ENHANCEMENT = "enhancement"
    QUESTION = "question"


class ProjectStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    PROVISIONING = "provisioning"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CLOSED = "closed"


class LogLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    DEBUG = "debug"


class NotificationType(str, Enum):
    ACKNOWLEDGE = "acknowledge"
    CLARIFICATION = "clarification"
    COMPLETION = "completion"
    ERROR = "error"


class UserFeedback(BaseModel):
    """Stored when Twilio/Claude has determined clear feedback from a user (SMS)."""
    id: UUID
    created_at: datetime
    phone_number: str
    summary: str
    raw_messages: Optional[str] = None  # optional JSON or transcript for reference


class Project(BaseModel):
    id: UUID
    created_at: datetime
    updated_at: datetime
    title: str
    description: Optional[str] = None
    ticket_type: ProjectType = ProjectType.FEATURE
    cluster_centroid: Optional[List[float]] = None
    severity_score: int = 0
    status: ProjectStatus = ProjectStatus.PENDING
    github_issue_number: Optional[int] = None
    github_issue_url: Optional[str] = None
    github_pr_number: Optional[int] = None
    github_pr_url: Optional[str] = None
    repo_config_id: UUID
    plan_id: Optional[UUID] = None


class Plan(BaseModel):
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
    id: UUID
    created_at: datetime
    log_level: LogLevel = LogLevel.INFO
    message: str
    metadata: dict = Field(default_factory=dict)
    step_name: Optional[str] = None
    project_id: UUID


class RepoConfig(BaseModel):
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
    id: UUID
    created_at: datetime
    updated_at: datetime
    x_account_handle: str
    github_owner: str
    github_repo: str
    github_branch: str = "main"
    default_repo_config_id: Optional[UUID] = None


class Notification(BaseModel):
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


class UpdateProjectStatusRequest(BaseModel):
    status: ProjectStatus
    metadata: dict = Field(default_factory=dict)


class CreateExecutionLogRequest(BaseModel):
    log_level: LogLevel = LogLevel.INFO
    message: str
    step_name: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class CreateRepoConfigRequest(BaseModel):
    github_owner: str
    github_repo: str
    github_branch: str = "main"
    x_account_handle: str
    x_keywords: List[str] = Field(default_factory=list)
    local_agent_enabled: bool = False
    auto_create_issues: bool = False
    auto_create_prs: bool = False
    user_id: Optional[UUID] = None


class CoderSession(BaseModel):
    id: UUID
    created_at: datetime
    completed_at: Optional[datetime] = None
    session_id: str
    status: str
    sandbox_path: str
    branch_name: Optional[str] = None
    pr_number: Optional[int] = None
    pr_url: Optional[str] = None
    test_results: Optional[dict] = None
    build_results: Optional[dict] = None
    lint_results: Optional[dict] = None
    review_results: Optional[dict] = None
    project_id: UUID


class ExecuteCoderRequest(BaseModel):
    project_id: UUID


class CoderStatusResponse(BaseModel):
    status: str
    current_step: Optional[str] = None
    progress: float = 0.0
    logs: List[ExecutionLog] = Field(default_factory=list)
