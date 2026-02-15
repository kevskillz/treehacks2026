"""
Core orchestrator for Claude Code CLI integration via Modal sandboxes.
Manages coding sessions and workflow coordination.

Replaces the old GrokCoderOrchestrator that used local subprocess calls.
Now all coding happens inside Modal VMs with Claude Code CLI.
"""

import json
import logging
import os
from uuid import UUID
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional

from models import ProjectStatus, LogLevel
import db

# Sandbox mode: "modal" (cloud VM) or "local" (subprocess)
SANDBOX_MODE = os.getenv("SANDBOX_MODE", "modal")

if SANDBOX_MODE == "local":
    from local_sandbox import create_sandbox, cleanup_sandbox
else:
    from modal_sandbox import create_sandbox, cleanup_sandbox

# Shared helpers work with both sandbox types via duck-typing
from modal_sandbox import (
    exec_in_sandbox,
    commit_changes,
    push_branch,
    get_git_diff,
    SandboxContext,
    SandboxError,
)
from github_client import create_pull_request, GitHubIssue
from testing import (
    detect_repo_context,
    generate_test_cases,
    verify_and_iterate,
    RepoContext,
)

logger = logging.getLogger(__name__)


# =====================================================
# EXCEPTIONS
# =====================================================


class WorkflowError(Exception):
    """Base exception for workflow errors."""
    pass


class GitHubError(WorkflowError):
    """GitHub API or CLI error."""
    pass


class ClaudeSessionError(WorkflowError):
    """Claude Code session error."""
    pass


class VerificationError(WorkflowError):
    """Verification (tests, build, lint) failed."""
    pass


# =====================================================
# DATA CLASSES
# =====================================================


@dataclass
class IssueData:
    """Minimal issue data extracted from project."""
    number: int
    title: str
    body: str


# =====================================================
# CLAUDE CODE SESSION (runs inside Modal sandbox)
# =====================================================


class ClaudeCodeSession:
    """
    Manages Claude Code CLI running inside a Modal sandbox.

    Replaces GrokCoderSession. Instead of local subprocess.Popen,
    we run `claude` commands via sandbox.exec().
    """

    def __init__(self, sandbox_ctx: SandboxContext):
        self.sandbox_ctx = sandbox_ctx

    def run_prompt(self, prompt: str, timeout: int = 600) -> str:
        """
        Run a single prompt using Claude Code CLI in headless mode.
        Uses stream-json output for real-time logging of Claude's actions.

        Args:
            prompt: Prompt text
            timeout: Timeout in seconds

        Returns:
            Output text from Claude Code (last result text)
        """
        logger.info(f"Running Claude Code prompt ({len(prompt)} chars)")

        escaped_prompt = prompt.replace("'", "'\\''")

        # In Modal mode, stdbuf forces line-buffered stdout so we
        # get real-time streaming instead of buffered chunks.
        # On macOS (local mode), stdbuf is not available — but
        # subprocess already streams line-by-line.
        stdbuf_prefix = "stdbuf -oL " if SANDBOX_MODE == "modal" else ""

        cmd = (
            f"cd {self.sandbox_ctx.repo_dir} && "
            f"{stdbuf_prefix}claude -p '{escaped_prompt}' "
            f"--model claude-sonnet-4-20250514 "
            f"--dangerously-skip-permissions "
            f"--output-format stream-json "
            f"--verbose "
            f"--max-turns 25"
        )

        process = self.sandbox_ctx.sandbox.exec(
            "bash", "-c", cmd,
        )

        # Stream stdout line-by-line — each line is a JSON event from Claude Code
        stdout_lines = []
        result_text = ""
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            stdout_lines.append(line)
            # Parse the JSON event for readable log output
            try:
                event = json.loads(line)
                etype = event.get("type", "")
                if etype == "assistant" and "message" in event:
                    msg = event["message"]
                    for block in msg.get("content", []):
                        btype = block.get("type", "")
                        if btype == "text":
                            text = block["text"][:200]
                            logger.info(f"[claude-code] 💬 {text}")
                        elif btype == "tool_use":
                            name = block.get("name", "?")
                            inp = str(block.get("input", ""))[:150]
                            logger.info(f"[claude-code] 🔧 {name}: {inp}")
                elif etype == "result":
                    cost = event.get("cost_usd", "?")
                    duration = event.get("duration_ms", "?")
                    result_text = event.get("result", "")
                    logger.info(f"[claude-code] ✅ Done — cost: ${cost}, duration: {duration}ms")
                elif etype == "system":
                    logger.info(f"[claude-code] ⚙️  {event.get('subtype', '')} {str(event.get('data', ''))[:150]}")
                else:
                    logger.info(f"[claude-code] [{etype}] {line[:150]}")
            except json.JSONDecodeError:
                logger.info(f"[claude-code] {line[:200]}")

        stderr = process.stderr.read()
        process.wait()
        returncode = process.returncode
        stdout = "\n".join(stdout_lines)

        if returncode != 0:
            logger.warning(
                f"Claude Code exited with code {returncode}: {stderr[:500]}"
            )

        logger.info(f"Claude Code finished: {len(stdout)} chars output")
        return result_text or stdout


def run_claude_fix(sandbox_ctx: SandboxContext, fix_prompt: str) -> str:
    """
    Run a fix prompt through Claude Code in the sandbox.
    Used as the callback for verify_and_iterate.
    """
    session = ClaudeCodeSession(sandbox_ctx)
    return session.run_prompt(fix_prompt)


# =====================================================
# CODER ORCHESTRATOR
# =====================================================


class CoderOrchestrator:
    """
    Main workflow coordination for the coding system.

    Flow:
    1. Create Modal sandbox (cloud VM)
    2. Clone repo + create branch
    3. Detect repo context
    4. Generate test cases with Claude
    5. Run Claude Code CLI for implementation
    6. Verify (test, build, lint, review) and iterate
    7. Commit, push, create PR
    8. Update Supabase with results
    9. Cleanup sandbox
    """

    def __init__(self, supabase):
        self.supabase = supabase

    def execute_issue_workflow(
        self,
        project_id: UUID,
        repo_config_id: UUID,
    ) -> dict:
        """
        Execute the full coding workflow for a project.

        Args:
            project_id: Project UUID (must have github_issue_url set)
            repo_config_id: Repository config UUID

        Returns:
            Result dict with status, pr_url, pr_number
        """
        logger.info(f"Starting workflow for project: {project_id}")

        repo_config = db.get_repo_config(self.supabase, repo_config_id)
        if not repo_config:
            raise WorkflowError(f"Repository config not found: {repo_config_id}")

        sandbox_ctx = None
        db_sandbox = None

        try:
            # Step 1: Initialize
            self._log_step(project_id, "workflow_start", "Starting coding workflow")

            # Step 2: Get project data
            project = db.get_project(self.supabase, project_id)
            if not project:
                raise WorkflowError(f"Project not found: {project_id}")

            # Step 3: Create Modal sandbox
            self._log_step(project_id, "create_sandbox", "Creating Modal cloud sandbox")
            sandbox_ctx = create_sandbox(project_id, repo_config)

            # Step 4: Detect repo context
            self._log_step(project_id, "detect_context", "Detecting repository context")
            repo_context = detect_repo_context(sandbox_ctx)

            # Step 5: Get existing plan
            plan = None
            if project.plan_id:
                plan = db.get_plan(self.supabase, project.plan_id)

            # Step 6: Generate test cases
            self._log_step(project_id, "generate_tests", "Generating test cases")

            issue_data = IssueData(
                number=project.github_issue_number or 0,
                title=project.title,
                body=project.description or "",
            )

            test_cases = generate_test_cases(issue_data, repo_context)

            # Step 7: Start Claude Code session
            self._log_step(project_id, "start_claude_session", "Starting Claude Code CLI in sandbox")
            db.update_project_status(self.supabase, project_id, ProjectStatus.EXECUTING)

            claude_session = ClaudeCodeSession(sandbox_ctx)

            # Store sandbox in database
            db_sandbox = db.create_modal_sandbox(self.supabase, {
                "sandbox_id": str(project_id),
                "session_id": str(project_id),
                "sandbox_path": sandbox_ctx.repo_dir,
                "branch_name": sandbox_ctx.branch_name,
                "project_id": str(project_id),
                "status": "active",
            })

            # Step 8: Send implementation prompt
            self._log_step(project_id, "implement_feature", "Implementing feature with Claude Code")
            implementation_prompt = self._build_implementation_prompt(
                issue_data, plan, test_cases
            )
            output = claude_session.run_prompt(implementation_prompt)
            logger.info(f"Implementation output: {len(output)} chars")

            # Step 9: Verification and iteration cycle
            self._log_step(project_id, "verification_cycle", "Running tests and verification")

            success, verification_results = verify_and_iterate(
                sandbox_ctx,
                repo_config,
                run_claude_fix,
                max_iterations=1,
                skip_review=True,
            )

            if not success:
                self._log_step(
                    project_id,
                    "verification_failed",
                    "Verification failed after max iterations",
                    LogLevel.ERROR,
                )
                db.update_project_status(
                    self.supabase, project_id, ProjectStatus.FAILED
                )
                db.update_modal_sandbox(self.supabase, db_sandbox.id, {
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                })
                return {"status": "failed", "reason": "verification_failed"}

            # Step 10: Commit changes
            self._log_step(project_id, "commit_changes", "Committing changes")
            commit_message = (
                f"Fix: {issue_data.title}\n\n"
                f"Fixes #{issue_data.number}\n\n"
                f"Generated by @coder (Claude Code)"
            )
            commit_changes(sandbox_ctx, commit_message)

            # Step 11: Push branch
            self._log_step(project_id, "push_branch", "Pushing branch to remote")
            push_branch(sandbox_ctx)

            # Step 12: Create PR
            self._log_step(project_id, "create_pr", "Creating pull request")
            github_issue = GitHubIssue(
                number=issue_data.number,
                title=issue_data.title,
                body=issue_data.body,
                labels=[],
                author="treehacks-bot",
                created_at="",
                state="open",
            )
            pr = create_pull_request(
                sandbox_ctx, github_issue, verification_results, repo_config
            )

            db.update_project_status(
                self.supabase,
                project_id,
                ProjectStatus.EXECUTING,
                {
                    "github_pr_number": pr.number,
                    "github_pr_url": pr.url,
                },
            )

            # Update sandbox record with results
            db.update_modal_sandbox(self.supabase, db_sandbox.id, {
                "pr_number": pr.number,
                "pr_url": pr.url,
                "test_results": verification_results.get("tests"),
                "build_results": verification_results.get("build"),
                "lint_results": verification_results.get("lint"),
                "review_results": verification_results.get("review"),
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })

            # Step 13: Mark complete
            db.update_project_status(
                self.supabase, project_id, ProjectStatus.COMPLETED
            )
            self._log_step(
                project_id,
                "workflow_complete",
                f"Workflow complete! PR: {pr.url}",
            )

            return {
                "status": "success",
                "pr_url": pr.url,
                "pr_number": pr.number,
            }

        except Exception as e:
            logger.error(f"Workflow failed: {e}", exc_info=True)
            self._log_step(
                project_id,
                "workflow_error",
                f"Workflow failed: {e}",
                LogLevel.ERROR,
            )
            db.update_project_status(
                self.supabase, project_id, ProjectStatus.FAILED
            )
            if db_sandbox:
                db.update_modal_sandbox(self.supabase, db_sandbox.id, {
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                })
            raise

        finally:
            if sandbox_ctx:
                self._log_step(project_id, "cleanup", "Cleaning up Modal sandbox")
                cleanup_sandbox(sandbox_ctx)

    def _log_step(
        self,
        project_id: UUID,
        step_name: str,
        message: str,
        log_level: LogLevel = LogLevel.INFO,
    ) -> None:
        """Log a workflow step to the database."""
        db.create_execution_log(
            self.supabase, project_id, message, log_level, step_name
        )
        logger.info(f"[{step_name}] {message}")

    def _build_implementation_prompt(
        self, issue: IssueData, plan, test_cases: str
    ) -> str:
        """Build comprehensive prompt for Claude Code."""
        return f"""I need you to implement a fix for the following GitHub issue:

# Issue Details
**Title:** {issue.title}
**Number:** #{issue.number}
**Description:**
{issue.body}

# Implementation Plan
{plan.content if plan else "Follow the issue requirements"}

# Test Cases (Implement These FIRST!)
{test_cases}

# Instructions
1. Implement the feature according to the plan
2. If tests exist, ensure they pass
3. Follow the project's coding conventions
4. Consider edge cases and error handling

# IMPORTANT CONSTRAINTS
- Do NOT run dev servers interactively (npm run dev, yarn dev, next dev, etc.)
- Do NOT wait for or expect interactive user input
- You can run: npm install, npm run build, npm test, tsc --noEmit, eslint
- If no test framework exists, skip test implementation — do NOT add one

Implement the feature now. Focus on code changes only.
"""
