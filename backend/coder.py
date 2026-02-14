"""
Orchestrator for code implementation using Claude (Anthropic) with tool use.
Replaces Grok Code CLI: Claude updates code via read_file/write_file/run_bash, then we create PR.
"""

import logging
import os
import subprocess
from pathlib import Path
from uuid import UUID
from datetime import datetime, timezone
from dataclasses import dataclass

from anthropic import Anthropic

from models import ProjectStatus, LogLevel
import db
from sandbox import create_sandbox, cleanup_sandbox, commit_changes, push_branch, get_existing_sandbox, load_repo_context
from github_client import create_pull_request, GitHubIssue
from testing import detect_repo_context, generate_test_cases_with_claude, verify_and_iterate, RepoContext

logger = logging.getLogger(__name__)


class WorkflowError(Exception):
    pass


@dataclass
class IssueData:
    number: int
    title: str
    body: str


# Tool definitions for Claude (edit code in repo_path)
def _make_tools(repo_path: Path):
    repo_path = Path(repo_path)
    def read_file(path: str) -> str:
        p = (repo_path / path).resolve()
        if not str(p).startswith(str(repo_path.resolve())):
            return "Error: path outside repo"
        if not p.exists():
            return "Error: file not found"
        return p.read_text(encoding="utf-8", errors="replace")
    def write_file(path: str, contents: str) -> str:
        p = (repo_path / path).resolve()
        if not str(p).startswith(str(repo_path.resolve())):
            return "Error: path outside repo"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(contents, encoding="utf-8")
        return "OK"
    def run_bash(command: str) -> str:
        r = subprocess.run(
            command,
            shell=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}\nreturncode: {r.returncode}"
    return [
        {
            "name": "read_file",
            "description": "Read contents of a file in the repo. Path is relative to repo root.",
            "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        },
        {
            "name": "write_file",
            "description": "Write contents to a file. Path relative to repo root. Creates dirs if needed.",
            "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "contents": {"type": "string"}}, "required": ["path", "contents"]},
        },
        {
            "name": "run_bash",
            "description": "Run a shell command in the repo root (e.g. npm test, npm run build). No interactive commands.",
            "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
        },
    ], {"read_file": read_file, "write_file": write_file, "run_bash": run_bash}


class ClaudeCoderSession:
    """Uses Claude API with tool use to edit code in repo_path. Same interface as old Grok session: send_prompt, read_output."""

    def __init__(self, cwd: Path, session_id: str):
        self.cwd = Path(cwd)
        self.session_id = session_id
        self._pending_prompt = None
        self.process = None

    def start(self) -> None:
        logger.info("Claude coder session started: %s", self.session_id)

    def send_prompt(self, prompt: str) -> None:
        self._pending_prompt = prompt

    def read_output(self, timeout: int = 300) -> str:
        if not self._pending_prompt:
            return ""
        prompt = self._pending_prompt
        self._pending_prompt = None
        return self._run_with_tools(prompt, timeout)

    def _run_with_tools(self, prompt: str, timeout: int) -> str:
        client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        model = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")
        tools, tool_impl = _make_tools(self.cwd)
        messages = [{"role": "user", "content": prompt}]
        max_rounds = 30
        all_text = []

        for _ in range(max_rounds):
            resp = client.messages.create(
                model=model,
                max_tokens=4096,
                tools=tools,
                messages=messages,
            )
            content = resp.content
            if not content:
                break
            tool_results = []
            for block in content:
                if block.type == "text":
                    all_text.append(block.text)
                elif block.type == "tool_use":
                    tool_id = block.id
                    name = block.name
                    args = block.input if hasattr(block, "input") else {}
                    fn = tool_impl.get(name)
                    result = "Error: unknown tool"
                    if fn:
                        try:
                            if name == "read_file":
                                result = fn(args.get("path", ""))
                            elif name == "write_file":
                                result = fn(args.get("path", ""), args.get("contents", ""))
                            elif name == "run_bash":
                                result = fn(args.get("command", ""))
                        except Exception as e:
                            result = str(e)
                    tool_results.append({"type": "tool_result", "tool_use_id": tool_id, "content": result})
            messages.append({"role": "assistant", "content": content})
            if not tool_results:
                break
            messages.append({"role": "user", "content": tool_results})
        return "\n".join(all_text) if all_text else "Done."

    def is_alive(self) -> bool:
        return False

    def terminate(self) -> None:
        pass


class ClaudeCoderOrchestrator:
    """Runs the full workflow: sandbox, test cases, Claude code session, verify, commit, push, PR."""

    def __init__(self, supabase):
        self.supabase = supabase

    def _log_step(self, project_id: UUID, step_name: str, message: str, log_level: LogLevel = LogLevel.INFO):
        db.create_execution_log(self.supabase, project_id, message, log_level, step_name)
        logger.info("[%s] %s", step_name, message)

    def execute_issue_workflow(self, project_id: UUID, repo_config_id: UUID) -> dict:
        repo_config = db.get_repo_config(self.supabase, repo_config_id)
        if not repo_config:
            raise WorkflowError(f"Repo config not found: {repo_config_id}")
        sandbox_ctx = None
        claude_session = None
        db_session = None
        try:
            self._log_step(project_id, "workflow_start", "Starting Claude code workflow")
            project = db.get_project(self.supabase, project_id)
            if not project:
                raise WorkflowError(f"Project not found: {project_id}")

            sandbox_ctx = get_existing_sandbox(str(project_id))
            if not sandbox_ctx:
                self._log_step(project_id, "create_sandbox", "Creating sandbox")
                sandbox_ctx = create_sandbox(str(project_id), repo_config)
            else:
                self._log_step(project_id, "reuse_sandbox", "Reusing sandbox")

            repo_context = load_repo_context(str(project_id))
            if repo_context:
                repo_context_obj = RepoContext(
                    primary_language=repo_context["primary_language"],
                    test_framework=repo_context.get("test_framework"),
                    build_system=repo_context.get("build_system"),
                    structure_summary=repo_context.get("structure_summary", ""),
                )
            else:
                self._log_step(project_id, "detect_context", "Detecting repo context")
                repo_context_obj = detect_repo_context(sandbox_ctx.repo_path)

            plan = db.get_plan(self.supabase, project.plan_id) if project.plan_id else None
            issue_data = IssueData(
                number=project.github_issue_number or 0,
                title=project.title,
                body=project.description or "",
            )
            self._log_step(project_id, "generate_tests", "Generating test cases with Claude")
            test_cases = generate_test_cases_with_claude(issue_data, repo_context_obj)
            (sandbox_ctx.sandbox_dir / "TESTS.md").write_text(test_cases)

            self._log_step(project_id, "start_claude_session", "Starting Claude code session")
            db.update_project_status(self.supabase, project_id, ProjectStatus.EXECUTING)
            claude_session = ClaudeCoderSession(cwd=sandbox_ctx.repo_path, session_id=str(project_id))
            claude_session.start()
            db_session = db.create_coder_session(
                self.supabase,
                {"session_id": claude_session.session_id, "sandbox_path": str(sandbox_ctx.sandbox_dir), "branch_name": sandbox_ctx.branch_name, "project_id": str(project_id)},
            )

            impl_prompt = self._build_implementation_prompt(issue_data, plan, test_cases)
            self._log_step(project_id, "implement_feature", "Implementing with Claude")
            claude_session.send_prompt(impl_prompt)
            claude_session.read_output(timeout=300)

            self._log_step(project_id, "verification_cycle", "Running verification")
            success, verification_results = verify_and_iterate(sandbox_ctx, claude_session, repo_config, max_iterations=3)
            if not success:
                self._log_step(project_id, "verification_failed", "Verification failed", LogLevel.ERROR)
                db.update_project_status(self.supabase, project_id, ProjectStatus.FAILED)
                db.update_coder_session(self.supabase, db_session.id, {"status": "failed", "completed_at": datetime.now(timezone.utc).isoformat()})
                return {"status": "failed", "reason": "verification_failed"}

            self._log_step(project_id, "commit_changes", "Committing")
            commit_changes(sandbox_ctx.repo_path, f"Fix: {issue_data.title}\n\nFixes #{issue_data.number}\n\nGenerated by Vector (Claude)")
            self._log_step(project_id, "push_branch", "Pushing branch")
            push_branch(sandbox_ctx.repo_path, sandbox_ctx.branch_name)

            self._log_step(project_id, "create_pr", "Creating PR")
            gh_issue = GitHubIssue(number=issue_data.number, title=issue_data.title, body=issue_data.body, labels=[], author="", created_at="", state="open")
            pr = create_pull_request(sandbox_ctx, gh_issue, verification_results, repo_config)
            db.update_project_status(
                self.supabase,
                project_id,
                ProjectStatus.EXECUTING,
                {"github_pr_number": pr.number, "github_pr_url": pr.url},
            )
            db.update_coder_session(
                self.supabase,
                db_session.id,
                {
                    "pr_number": pr.number,
                    "pr_url": pr.url,
                    "test_results": verification_results.tests.__dict__ if hasattr(verification_results.tests, "__dict__") else {},
                    "build_results": verification_results.build.__dict__ if verification_results.build and hasattr(verification_results.build, "__dict__") else None,
                    "lint_results": verification_results.lint.__dict__ if verification_results.lint and hasattr(verification_results.lint, "__dict__") else None,
                    "review_results": verification_results.review.__dict__ if hasattr(verification_results.review, "__dict__") else {},
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            db.update_project_status(self.supabase, project_id, ProjectStatus.COMPLETED)
            self._log_step(project_id, "workflow_complete", f"Workflow complete! PR: {pr.url}")
            return {"status": "success", "pr_url": pr.url, "pr_number": pr.number}
        except Exception as e:
            logger.exception("Workflow failed: %s", e)
            self._log_step(project_id, "workflow_error", str(e), LogLevel.ERROR)
            db.update_project_status(self.supabase, project_id, ProjectStatus.FAILED)
            if db_session:
                db.update_coder_session(self.supabase, db_session.id, {"status": "failed", "completed_at": datetime.now(timezone.utc).isoformat()})
            raise
        finally:
            if sandbox_ctx:
                self._log_step(project_id, "cleanup", "Cleaning up sandbox")
                cleanup_sandbox(str(project_id), keep_on_success=False)

    def _build_implementation_prompt(self, issue, plan, test_cases: str) -> str:
        return f"""Implement the following GitHub issue.

# Issue
**Title:** {issue.title}
**Number:** #{issue.number}
**Description:**
{issue.body}

# Implementation Plan
{plan.content if plan else "Follow the issue requirements."}

# Test Cases (verify behavior)
{test_cases}

# Instructions
1. Use read_file to inspect relevant files, write_file to create/edit files, run_bash to run tests/build.
2. Do NOT run dev servers (npm run dev, etc.). You may run: npm install, npm run build, npm test, pytest, etc.
3. Make minimal, focused changes. When done, say you are done."""
