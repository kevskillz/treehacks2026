"""
FastAPI app for TreeHacks 2026 backend.
Handles webhooks, plan generation, and coding workflow orchestration.
"""

from contextlib import asynccontextmanager
import threading
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import logging
import uuid
from uuid import UUID

# Load environment variables FIRST
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sandbox mode: "modal" (cloud VM) or "local" (subprocess)
SANDBOX_MODE = os.getenv("SANDBOX_MODE", "modal")

# Now import modules that need env vars
from supabase import create_client, Client
from models import (
    UpdateProjectStatusRequest,
    CreateExecutionLogRequest,
    CreateRepoConfigRequest,
    ExecuteCoderRequest,
    ProjectStatus,
    LogLevel,
)
import db
from llm import claude_client
from coder import CoderOrchestrator

# =====================================================
# LIFESPAN (background poller)
# =====================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = threading.Event()
    poller = threading.Thread(target=_poll_status_changes, args=(stop_event,), daemon=True)
    poller.start()
    logger.info("Background status poller started")
    yield
    stop_event.set()
    poller.join(timeout=10)


# Initialize FastAPI
app = FastAPI(title="TreeHacks 2026 API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Supabase
supabase: Client = create_client(
    os.getenv("SUPABASE_URL", ""),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
)

# Initialize Coder Orchestrator
coder_orchestrator = CoderOrchestrator(supabase)

# Store active executions (in-memory for MVP)
active_executions: dict = {}

# Hold sandbox references between approve-project and approve-plan requests.
# The Modal VM stays alive for 30 min (timeout=1800). We just park the Python
# object here so the second HTTP request can pick it up without re-provisioning.
_sandbox_cache: dict[str, object] = {}   # project_id -> SandboxContext
_context_cache: dict[str, object] = {}   # project_id -> RepoContext dataclass


# =====================================================
# HEALTH CHECK
# =====================================================


@app.get("/")
async def root():
    return {"message": "TreeHacks 2026 API", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "treehacks-backend"}


# =====================================================
# PROJECT ENDPOINTS
# =====================================================


@app.get("/api/projects/{project_id}")
async def get_project(project_id: UUID):
    """Get a project with all related data (tweets, plan, logs)."""
    try:
        data = db.get_project_with_tweets(supabase, project_id)
        if not data:
            raise HTTPException(status_code=404, detail="Project not found")

        logs = db.get_execution_logs(supabase, project_id)

        return {
            "project": data["project"].model_dump(mode="json"),
            "tweets": [t.model_dump(mode="json") for t in data["tweets"]],
            "plan": data["plan"].model_dump(mode="json") if data["plan"] else None,
            "logs": [log.model_dump(mode="json") for log in logs],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting project: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/generate-plan")
def generate_plan_endpoint(project_id: UUID):
    """Generate implementation plan for a project."""
    try:
        db.update_project_status(supabase, project_id, ProjectStatus.PLANNING)
        db.create_execution_log(
            supabase, project_id, "Plan generation started", LogLevel.INFO, "generate_plan"
        )

        plan = generate_implementation_plan(str(project_id))

        if plan:
            return {
                "status": "success",
                "message": "Plan generated",
                "plan_id": str(plan.id),
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to generate plan")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/projects/{project_id}/status")
async def update_project_status_endpoint(
    project_id: UUID, data: UpdateProjectStatusRequest
):
    """Update project status."""
    try:
        project = db.update_project_status(
            supabase, project_id, data.status, data.metadata
        )
        db.create_execution_log(
            supabase,
            project_id,
            f"Status updated to: {data.status.value}",
            LogLevel.INFO,
            "status_update",
            data.metadata,
        )
        logger.info(f"Project {project_id} status updated to {data.status.value}")
        return {"status": "updated", "project": project.model_dump(mode="json")}

    except Exception as e:
        logger.error(f"Error updating status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/logs")
async def add_execution_log(
    project_id: UUID, data: CreateExecutionLogRequest
):
    """Add execution log."""
    try:
        log = db.create_execution_log(
            supabase, project_id, data.message, data.log_level, data.step_name, data.metadata
        )
        return {"status": "logged", "log": log.model_dump(mode="json")}

    except Exception as e:
        logger.error(f"Error adding log: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/projects/{project_id}/logs")
async def get_execution_logs_endpoint(project_id: UUID):
    """Get all execution logs for a project."""
    try:
        logs = db.get_execution_logs(supabase, project_id)
        return {"logs": [log.model_dump(mode="json") for log in logs]}

    except Exception as e:
        logger.error(f"Error getting logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# PLAN ENDPOINTS
# =====================================================


@app.get("/api/plans/{plan_id}")
async def get_plan_endpoint(plan_id: UUID):
    """Get a plan with its project."""
    try:
        data = db.get_plan_with_project(supabase, plan_id)
        if not data:
            raise HTTPException(status_code=404, detail="Plan not found")

        return {
            "plan": data["plan"].model_dump(mode="json"),
            "project": data["project"].model_dump(mode="json") if data["project"] else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/plans/{plan_id}/approve")
def approve_plan_endpoint(plan_id: UUID, body: dict | None = None):
    """
    Approve a plan and trigger code execution.

    1. Approves the plan
    2. Sets project status to EXECUTING
    3. Triggers the Codex CLI workflow to implement the changes
    """
    try:
        user_id = body.get("user_id") if body else None
        content = body.get("content") if body else None

        plan = db.approve_plan(supabase, plan_id, user_id, content)
        db.update_project_status(supabase, plan.project_id, ProjectStatus.EXECUTING)
        db.create_execution_log(
            supabase,
            plan.project_id,
            "Plan approved, starting code execution",
            LogLevel.INFO,
            "plan_approval",
        )

        logger.info(f"Plan {plan_id} approved, project moved to executing")

        project = db.get_project(supabase, plan.project_id)
        if not project:
            raise HTTPException(
                status_code=500, detail="Project not found after plan approval"
            )

        # Trigger the coder workflow, reusing the sandbox from approve-project if available
        pid = str(plan.project_id)
        cached_sandbox = _sandbox_cache.pop(pid, None)
        cached_context = _context_cache.pop(pid, None)

        if cached_sandbox:
            logger.info(f"REUSING cached sandbox for project {pid}")
        else:
            logger.info(f"No cached sandbox for project {pid}, will create fresh one")

        logger.info(f"AUTO-TRIGGERING CODER WORKFLOW for project {plan.project_id}")

        try:
            result = coder_orchestrator.execute_issue_workflow(
                plan.project_id,
                project.repo_config_id,
                existing_sandbox_ctx=cached_sandbox,
                cached_repo_context=cached_context,
            )
            return {
                "status": "approved",
                "plan": plan.model_dump(mode="json"),
                "execution": {"status": "completed", "result": result},
            }

        except Exception as workflow_error:
            logger.error(f"WORKFLOW FAILED: {workflow_error}", exc_info=True)
            return {
                "status": "approved",
                "plan": plan.model_dump(mode="json"),
                "execution": {"status": "failed", "error": str(workflow_error)},
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/approve")
def approve_project_request(project_id: UUID, body: dict | None = None):
    """
    Approve a project request and create GitHub issue.

    1. Creates Modal sandbox to detect code context
    2. Enriches issue description with codebase context
    3. Creates GitHub issue
    4. Auto-generates implementation plan
    """
    sandbox_ctx = None
    auto_generate_plan = True
    if body:
        auto_generate_plan = body.get("auto_generate_plan", True)

    try:
        project = db.get_project(supabase, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if project.status != ProjectStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail=f"Project must be in pending status (current: {project.status.value})",
            )

        repo_config = db.get_repo_config(supabase, project.repo_config_id)
        if not repo_config:
            raise HTTPException(status_code=404, detail="Repository config not found")

        if SANDBOX_MODE == "local":
            from local_sandbox import create_sandbox as create_sb, cleanup_sandbox as cleanup_sb
        else:
            from modal_sandbox import create_sandbox as create_sb, cleanup_sandbox as cleanup_sb

        # Create sandbox and detect code context
        logger.info(f"Creating sandbox to detect code context for project {project_id}")
        db.create_execution_log(
            supabase, project_id, "Detecting code context", LogLevel.INFO, "detect_context"
        )

        sandbox_ctx = create_sb(project_id, repo_config)
        repo_context_obj = detect_repo_context_for_approval(sandbox_ctx)

        repo_context = {
            "primary_language": repo_context_obj.primary_language,
            "test_framework": repo_context_obj.test_framework,
            "build_system": repo_context_obj.build_system,
            "structure_summary": repo_context_obj.structure_summary,
        }

        logger.info(f"Detected: {repo_context['primary_language']} with {repo_context['test_framework']}")

        # Enrich issue description with code context
        db.create_execution_log(
            supabase, project_id, "Enriching issue with code context", LogLevel.INFO, "enrich_issue"
        )
        enriched = claude_client.enrich_issue_with_context(
            title=project.title,
            description=project.description or "",
            repo_context=repo_context,
        )
        enriched_title = enriched["title"][:80]
        enriched_description = enriched["description"]

        # Create GitHub issue inside the sandbox
        logger.info(f"Creating GitHub issue for project {project_id}")
        db.create_execution_log(
            supabase, project_id, "Creating GitHub issue", LogLevel.INFO, "create_issue"
        )

        from github_client import create_issue as gh_create_issue

        labels = [project.ticket_type]
        if project.severity_score > 100:
            labels.append("high-priority")

        issue = gh_create_issue(
            sandbox_ctx,
            title=enriched_title,
            body=enriched_description,
            labels=labels,
            repo_config=repo_config,
        )

        issue_url = (
            f"https://github.com/{repo_config.github_owner}/"
            f"{repo_config.github_repo}/issues/{issue.number}"
        )

        logger.info(f"GitHub issue #{issue.number} created: {issue_url}")
        db.update_project_status(
            supabase,
            project_id,
            ProjectStatus.PLANNING,
            {"github_issue_number": issue.number, "github_issue_url": issue_url},
        )
        db.create_execution_log(
            supabase,
            project_id,
            f"GitHub issue #{issue.number} created successfully",
            LogLevel.INFO,
            "issue_created",
        )

        # Keep sandbox alive for reuse by the coder workflow.
        # Store it in the in-memory cache keyed by project_id.
        pid = str(project_id)
        _sandbox_cache[pid] = sandbox_ctx
        _context_cache[pid] = repo_context_obj  # Store the RepoContext dataclass, not the dict
        logger.info(f"Sandbox cached for project {pid} (will be reused by coder workflow)")

        # Prevent the error-path cleanup from touching this sandbox
        sandbox_ctx = None

        # Auto-generate plan (uses cached repo_context, no new sandbox needed)
        plan_id = None
        if auto_generate_plan:
            logger.info(f"Auto-generating plan for project {project_id}")
            try:
                plan = generate_implementation_plan(
                    str(project_id), repo_context=repo_context
                )
                plan_id = str(plan.id) if plan else None
            except Exception as plan_error:
                logger.error(f"Failed to generate plan: {plan_error}")
                db.create_execution_log(
                    supabase,
                    project_id,
                    f"Plan generation failed: {plan_error}",
                    LogLevel.WARNING,
                    "plan_generation_failed",
                )

        return {
            "status": "approved",
            "github_issue_url": issue_url,
            "github_issue_number": issue.number,
            "plan_id": plan_id,
            "message": "Project approved and GitHub issue created",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving project: {e}", exc_info=True)
        db.create_execution_log(
            supabase, project_id, f"Approval failed: {e}", LogLevel.ERROR, "approval_error"
        )
        # Clean up cached sandbox on error
        pid = str(project_id)
        stale = _sandbox_cache.pop(pid, None)
        _context_cache.pop(pid, None)
        if stale:
            cleanup_sb(stale)
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # Only clean up if sandbox_ctx is still set (i.e. we didn't cache it)
        if sandbox_ctx:
            if SANDBOX_MODE == "local":
                from local_sandbox import cleanup_sandbox as cleanup_sb2
            else:
                from modal_sandbox import cleanup_sandbox as cleanup_sb2
            cleanup_sb2(sandbox_ctx)


# =====================================================
# REPOSITORY ENDPOINTS
# =====================================================


@app.post("/api/repos")
async def create_repo_config_endpoint(data: CreateRepoConfigRequest):
    """Create a new repository configuration."""
    try:
        repo_config = db.create_repo_config(supabase, data.model_dump())
        logger.info(
            f"Created repo config {repo_config.id} for "
            f"{data.github_owner}/{data.github_repo}"
        )
        return {
            "status": "created",
            "repo_config": repo_config.model_dump(mode="json"),
        }

    except Exception as e:
        logger.error(f"Error creating repo config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/repos/{repo_config_id}/projects")
async def get_repo_projects(repo_config_id: UUID):
    """Get all projects for a repository."""
    try:
        projects = db.get_projects_by_repo(supabase, repo_config_id)
        return {"projects": [p.model_dump(mode="json") for p in projects]}

    except Exception as e:
        logger.error(f"Error getting repo projects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/repos/{repo_config_id}/active-project")
async def get_active_project_endpoint(repo_config_id: UUID):
    """Get or create the active project for a repository."""
    try:
        project = db.get_or_create_active_project(supabase, repo_config_id)
        return {
            "project_id": str(project.id),
            "project": project.model_dump(mode="json"),
        }

    except Exception as e:
        logger.error(f"Error getting active project: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# TWEET PROCESSING ENDPOINT
# =====================================================


@app.post("/api/tweets/process")
def process_tweet_endpoint(body: dict):
    """Process a new tweet (generate embedding and cluster)."""
    try:
        tweet_id = body.get("tweet_id")
        if not tweet_id:
            raise HTTPException(status_code=400, detail="tweet_id required")

        result = process_new_tweet(tweet_id)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing tweet: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# CODER ENDPOINTS
# =====================================================


@app.post("/api/coder/execute")
def execute_coder_workflow(data: ExecuteCoderRequest):
    """Execute the full coding workflow for an approved project."""
    try:
        project = db.get_project(supabase, data.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if project.status != ProjectStatus.EXECUTING:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Project must be in 'executing' status "
                    f"(current: {project.status.value}). "
                    f"Approve the plan first."
                ),
            )

        if not project.github_issue_url:
            raise HTTPException(
                status_code=400,
                detail="Project missing GitHub issue. Approve the project first.",
            )

        repo_config = db.get_repo_config(supabase, project.repo_config_id)
        if not repo_config:
            raise HTTPException(status_code=404, detail="Repository config not found")

        execution_id = str(uuid.uuid4())
        logger.info(
            f"STARTING WORKFLOW: {execution_id} for project {data.project_id}"
        )

        try:
            result = coder_orchestrator.execute_issue_workflow(
                data.project_id, project.repo_config_id
            )
            return {
                "status": "completed",
                "execution_id": execution_id,
                "project_id": str(data.project_id),
                "github_issue_url": project.github_issue_url,
                "result": result,
            }

        except Exception as workflow_error:
            logger.error(f"WORKFLOW FAILED: {workflow_error}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(workflow_error))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/coder/status/{project_id}")
async def get_coder_status(project_id: UUID):
    """Get real-time status of coder execution."""
    try:
        project = db.get_project(supabase, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        logs = db.get_execution_logs(supabase, project_id)
        session = db.get_modal_sandbox_by_project(supabase, project_id)

        progress_map = {
            "pending": 0.0,
            "planning": 0.2,
            "provisioning": 0.3,
            "executing": 0.6,
            "completed": 1.0,
            "failed": 0.0,
        }
        progress = progress_map.get(project.status.value, 0.0)
        current_step = logs[0].step_name if logs else None

        return {
            "status": project.status.value,
            "current_step": current_step,
            "progress": progress,
            "logs": [log.model_dump(mode="json") for log in logs[:20]],
            "session": session.model_dump(mode="json") if session else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting coder status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# HELPER FUNCTIONS
# =====================================================


def detect_repo_context_for_approval(sandbox_ctx):
    """Detect repo context using Modal sandbox (for the approval flow)."""
    from testing import detect_repo_context
    return detect_repo_context(sandbox_ctx)


def process_new_tweet(tweet_id: str):
    """Process a new tweet using the simplified single-project model."""
    logger.info(f"Processing tweet {tweet_id}")

    tweet = db.get_tweet_by_tweet_id(supabase, tweet_id)
    if not tweet:
        logger.error(f"Tweet {tweet_id} not found")
        return {"status": "error", "message": "Tweet not found"}

    if tweet.processed:
        logger.info(f"Tweet {tweet_id} already processed")
        return {"status": "already_processed"}

    if not tweet.project_id:
        logger.error(f"Tweet {tweet_id} has no project_id")
        return {
            "status": "error",
            "message": "Tweet must have project_id.",
        }

    try:
        project = db.get_project(supabase, tweet.project_id)
        if not project:
            return {"status": "error", "message": "Project not found"}

        db.update_tweet(supabase, tweet.id, {"processed": True})

        all_tweets = db.get_tweets_by_project(supabase, project.id)
        logger.info(f"Found {len(all_tweets)} total tweets for project {project.id}")

        tweet_texts = [t.tweet_text for t in all_tweets]
        aggregated = claude_client.aggregate_tweets_into_project(tweet_texts)

        total_likes = sum(t.likes_count for t in all_tweets)
        total_retweets = sum(t.retweets_count for t in all_tweets)
        tweet_count = len(all_tweets)
        severity_score = (tweet_count * 10) + (total_likes * 2) + (total_retweets * 5)

        db.update_project_fields(supabase, project.id, {
            "title": aggregated["title"],
            "description": aggregated["description"],
            "ticket_type": aggregated["ticket_type"],
            "tweet_count": tweet_count,
            "severity_score": severity_score,
        })

        logger.info(f"Successfully processed tweet, updated project {project.id}")
        return {
            "status": "success",
            "project_id": str(project.id),
            "tweet_count": tweet_count,
            "action": "project_updated",
        }

    except Exception as e:
        logger.error(f"Error processing tweet {tweet_id}: {e}", exc_info=True)
        raise


def generate_implementation_plan(
    project_id: str,
    repo_context: dict | None = None,
    sandbox_ctx=None,
    keep_sandbox: bool = False,
):
    """Generate implementation plan for a project using Claude.

    Args:
        project_id: Project UUID string.
        repo_context: Pre-computed repo context dict (skips detection).
        sandbox_ctx: Existing sandbox to reuse (skips creating a new one).
        keep_sandbox: If True, don't clean up sandbox on exit and return
            ``(plan, sandbox_ctx, repo_context)`` instead of just ``plan``.
    """
    logger.info(f"Generating plan for project {project_id}")

    data = db.get_project_with_tweets(supabase, project_id)
    if not data:
        raise ValueError(f"Project {project_id} not found")

    project = data["project"]
    tweets = data["tweets"]

    repo = db.get_repo_config(supabase, project.repo_config_id)
    if not repo:
        raise ValueError(f"Repo config not found for project {project_id}")

    owns_sandbox = sandbox_ctx is None  # True if we created it ourselves
    try:
        # Always include project title/description, plus tweets if available
        feedback_text = f"**{project.title}**\n\n{project.description or ''}"
        if tweets:
            tweet_texts = [t.tweet_text for t in tweets]
            tweets_section = "\n".join([f"- {t}" for t in tweet_texts])
            feedback_text += f"\n\n## Related User Tweets\n{tweets_section}"

        if repo_context:
            logger.info("Using pre-computed repo context")
        else:
            if sandbox_ctx is None:
                if SANDBOX_MODE == "local":
                    from local_sandbox import create_sandbox as create_sb
                else:
                    from modal_sandbox import create_sandbox as create_sb

                logger.info("Creating temporary sandbox for plan generation")
                sandbox_ctx = create_sb(UUID(project_id), repo)

            repo_context_obj = detect_repo_context_for_approval(sandbox_ctx)
            repo_context = {
                "primary_language": repo_context_obj.primary_language,
                "test_framework": repo_context_obj.test_framework,
                "build_system": repo_context_obj.build_system,
                "structure_summary": repo_context_obj.structure_summary,
            }

        logger.info(
            f"Using context: {repo_context['primary_language']} "
            f"with {repo_context['test_framework']}"
        )

        plan_content = claude_client.generate_plan(
            feedback_text,
            repo.github_owner,
            repo.github_repo,
            repo.github_branch,
            repo_context=repo_context,
        )

        plan = db.create_plan(supabase, {
            "title": project.title,
            "content": plan_content,
            "project_id": str(project_id),
            "version": 1,
        })

        supabase.table("projects").update({
            "plan_id": str(plan.id),
            "status": ProjectStatus.PROVISIONING.value,
        }).eq("id", str(project_id)).execute()

        db.create_execution_log(
            supabase,
            project_id,
            "Plan generated, awaiting user approval",
            LogLevel.INFO,
            "plan_complete",
        )

        logger.info(f"Plan {plan.id} generated for project {project_id}")

        if keep_sandbox:
            return plan, sandbox_ctx, repo_context
        return plan

    except Exception as e:
        logger.error(f"Error generating plan for project {project_id}: {e}")
        db.update_project_status(supabase, project_id, ProjectStatus.FAILED)
        raise

    finally:
        # Only clean up if we created the sandbox AND we're not keeping it
        if sandbox_ctx and owns_sandbox and not keep_sandbox:
            if SANDBOX_MODE == "local":
                from local_sandbox import cleanup_sandbox as cleanup_sb
            else:
                from modal_sandbox import cleanup_sandbox as cleanup_sb
            cleanup_sb(sandbox_ctx)


# =====================================================
# BACKGROUND STATUS POLLER
# =====================================================

_processing: set[str] = set()


def _poll_status_changes(stop_event: threading.Event):
    """Poll Supabase for projects whose status changed externally."""
    POLL_INTERVAL = 10  # seconds

    while not stop_event.is_set():
        try:
            # --- planning → generate plan → provisioning ---
            rows = (
                supabase.table("projects")
                .select("id, repo_config_id")
                .eq("status", "planning")
                .execute()
                .data
            )
            for row in rows:
                pid = row["id"]
                if pid in _processing:
                    continue
                _processing.add(pid)
                logger.info(f"[poller] Detected project {pid} in 'planning' — generating plan")
                try:
                    # Create sandbox once and keep it for the coder workflow
                    if SANDBOX_MODE == "local":
                        from local_sandbox import create_sandbox as create_sb
                    else:
                        from modal_sandbox import create_sandbox as create_sb

                    repo = db.get_repo_config(supabase, row["repo_config_id"])
                    sbx = create_sb(UUID(pid), repo)
                    result = generate_implementation_plan(
                        pid, sandbox_ctx=sbx, keep_sandbox=True
                    )
                    plan, sbx, ctx = result
                    _sandbox_cache[pid] = sbx
                    _context_cache[pid] = ctx
                    logger.info(f"[poller] Plan generated for {pid}, sandbox cached for reuse")
                except Exception as e:
                    logger.error(f"[poller] Plan generation failed for {pid}: {e}", exc_info=True)
                    try:
                        db.update_project_status(supabase, pid, ProjectStatus.FAILED)
                    except Exception:
                        pass
                finally:
                    _processing.discard(pid)

            # --- executing → coder workflow → completed/failed ---
            rows = (
                supabase.table("projects")
                .select("id, repo_config_id")
                .eq("status", "executing")
                .execute()
                .data
            )
            for row in rows:
                pid = row["id"]
                rcid = row["repo_config_id"]
                if pid in _processing:
                    continue
                _processing.add(pid)
                logger.info(f"[poller] Detected project {pid} in 'executing' — starting coder workflow")
                try:
                    cached_sandbox = _sandbox_cache.pop(pid, None)
                    cached_context = _context_cache.pop(pid, None)
                    if cached_sandbox:
                        logger.info(f"[poller] Reusing cached sandbox for {pid}")
                    coder_orchestrator.execute_issue_workflow(
                        pid, rcid,
                        existing_sandbox_ctx=cached_sandbox,
                        cached_repo_context=cached_context,
                    )
                    logger.info(f"[poller] Coder workflow completed for {pid}")
                except Exception as e:
                    logger.error(f"[poller] Coder workflow failed for {pid}: {e}", exc_info=True)
                    try:
                        db.update_project_status(supabase, pid, ProjectStatus.FAILED)
                    except Exception:
                        pass
                finally:
                    _processing.discard(pid)

        except Exception as e:
            logger.error(f"[poller] Unexpected error in polling loop: {e}", exc_info=True)

        stop_event.wait(POLL_INTERVAL)


# =====================================================
# RUN
# =====================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
