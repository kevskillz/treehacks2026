"""
Local subprocess-based sandbox for development.
Mirrors the modal_sandbox.py interface using local subprocess calls.

Enable with SANDBOX_MODE=local in .env.
All commands run locally via subprocess instead of in a Modal cloud VM.
"""

import os
import shlex
import shutil
import logging
import subprocess
import uuid as _uuid
from uuid import UUID

from models import RepoConfig

# Re-export shared types and helper functions so callers can import
# from either module interchangeably. The helper functions
# (exec_in_sandbox, commit_changes, etc.) work with both Modal and
# local sandboxes because they call sandbox_ctx.sandbox.exec() which
# is duck-typed.
from modal_sandbox import (
    SandboxContext,
    SandboxError,
    CloneError,
    BranchError,
    exec_in_sandbox,
    commit_changes,
    push_branch,
    get_git_diff,
    get_git_status,
    get_repo_structure,
)

logger = logging.getLogger(__name__)


# =====================================================
# LOCAL PROCESS / SANDBOX WRAPPERS
# =====================================================


class _StreamReader:
    """
    Wraps a text-mode pipe to provide both iteration and .read().

    Modal's process.stdout / process.stderr expose the same two
    interfaces, so this lets LocalProcess be a drop-in replacement.
    """

    def __init__(self, pipe):
        self._pipe = pipe

    def __iter__(self):
        for line in self._pipe:
            yield line

    def read(self):
        return self._pipe.read()


class LocalProcess:
    """
    Wraps subprocess.Popen to match Modal's process interface.

    Attributes:
        stdout: _StreamReader — iterable and supports .read()
        stderr: _StreamReader — iterable and supports .read()
        returncode: int | None — set after .wait()
    """

    def __init__(self, proc: subprocess.Popen):
        self._proc = proc
        self.stdout = _StreamReader(proc.stdout)
        self.stderr = _StreamReader(proc.stderr)
        self.returncode = None

    def wait(self):
        self._proc.wait()
        self.returncode = self._proc.returncode


class LocalSandbox:
    """
    Mimics modal.Sandbox interface using local subprocess calls.

    The .exec() method spawns a subprocess and returns a LocalProcess
    with the same interface as Modal's process objects. This lets all
    existing code (exec_in_sandbox, get_repo_structure, etc.) work
    unchanged.
    """

    def __init__(self, workdir: str, env: dict):
        self._workdir = workdir
        self._env = {**os.environ, **env}

    def exec(self, *cmd: str) -> LocalProcess:
        """Execute a command locally, returning a process handle."""
        proc = subprocess.Popen(
            list(cmd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line-buffered for real-time streaming
            cwd=self._workdir,
            env=self._env,
        )
        return LocalProcess(proc)

    def terminate(self):
        """No-op; cleanup_sandbox handles directory removal."""
        pass


# =====================================================
# SANDBOX LIFECYCLE
# =====================================================


def create_sandbox(
    project_id: UUID,
    repo_config: RepoConfig,
    timeout: int = 1800,
) -> SandboxContext:
    """
    Create a local sandbox environment.

    Clones the repo into /tmp/treehacks-sandbox-{project_id}/repo,
    creates a feature branch, and configures git.

    Args:
        project_id: Project UUID
        repo_config: Repository configuration
        timeout: Unused (kept for interface compatibility)

    Returns:
        SandboxContext with a LocalSandbox handle
    """
    branch_name = f"fix/issue-{str(project_id)[:8]}-{_uuid.uuid4().hex[:4]}"
    github_token = repo_config.github_token or os.getenv("GITHUB_TOKEN", "")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

    if github_token:
        git_remote = (
            f"https://x-access-token:{github_token}@github.com/"
            f"{repo_config.github_owner}/{repo_config.github_repo}.git"
        )
    else:
        git_remote = (
            f"https://github.com/{repo_config.github_owner}/"
            f"{repo_config.github_repo}.git"
        )

    base_dir = f"/tmp/treehacks-sandbox-{project_id}"
    repo_dir = os.path.join(base_dir, "repo")

    logger.info(
        f"Creating local sandbox for project {project_id} "
        f"(repo: {repo_config.github_owner}/{repo_config.github_repo})"
    )

    # Clean up any leftover sandbox from a previous run
    if os.path.exists(base_dir):
        shutil.rmtree(base_dir)
    os.makedirs(base_dir, exist_ok=True)

    openai_api_key = os.getenv("OPENAI_API_KEY", "")

    env = {
        "ANTHROPIC_API_KEY": anthropic_key,
        "OPENAI_API_KEY": openai_api_key,
        "CODEX_API_KEY": openai_api_key,
        "GITHUB_TOKEN": github_token,
        "GH_TOKEN": github_token,
    }

    try:
        logger.info("Cloning repository locally...")
        _run_local(
            [
                "git", "clone",
                "--branch", repo_config.github_branch,
                "--depth", "1",
                git_remote,
                repo_dir,
            ],
            env=env,
        )

        logger.info(f"Repository cloned, creating branch {branch_name}...")
        _run_local(
            ["git", "checkout", "-b", branch_name],
            cwd=repo_dir, env=env,
        )
        _run_local(
            ["git", "config", "user.email", "bot@treehacks.dev"],
            cwd=repo_dir, env=env,
        )
        _run_local(
            ["git", "config", "user.name", "TreeHacks Bot"],
            cwd=repo_dir, env=env,
        )

        # Configure gh CLI with the token
        _run_local(["gh", "auth", "setup-git"], cwd=repo_dir, env=env)

        # NOTE: Dependencies are NOT installed here — they are deferred to
        # the coder phase (install_dependencies) so that the approval flow
        # (context detection, issue creation, plan generation) is faster.

        logger.info(f"Local sandbox ready for project {project_id}")

        sandbox = LocalSandbox(repo_dir, env)

        return SandboxContext(
            sandbox=sandbox,
            repo_dir=repo_dir,
            branch_name=branch_name,
            git_remote=git_remote,
        )

    except Exception as e:
        # Clean up on failure
        if os.path.exists(base_dir):
            shutil.rmtree(base_dir, ignore_errors=True)
        logger.error(f"Failed to create local sandbox: {e}")
        raise SandboxError(f"Failed to create local sandbox: {e}")


def cleanup_sandbox(sandbox_ctx: SandboxContext) -> None:
    """Clean up local sandbox by removing the temporary directory."""
    try:
        base_dir = os.path.dirname(sandbox_ctx.repo_dir)
        if os.path.exists(base_dir) and "treehacks-sandbox" in base_dir:
            shutil.rmtree(base_dir, ignore_errors=True)
            logger.info(f"Local sandbox cleaned up: {base_dir}")
        else:
            logger.info(
                "Skipping cleanup — path does not look like a sandbox dir"
            )
    except Exception as e:
        logger.warning(f"Failed to clean up local sandbox (non-fatal): {e}")


# =====================================================
# DEFERRED DEPENDENCY INSTALL
# =====================================================


def install_dependencies(sandbox_ctx: SandboxContext) -> None:
    """
    Install project dependencies inside the sandbox.

    Called by the coder workflow right before running Codex CLI,
    NOT during sandbox creation, so that the approval flow stays fast.
    """
    repo_dir = sandbox_ctx.repo_dir
    env = sandbox_ctx.sandbox._env if hasattr(sandbox_ctx.sandbox, '_env') else None

    logger.info("Installing dependencies...")
    try:
        _run_local(["yarn", "install"], cwd=repo_dir, env=env)
        logger.info("Dependencies installed with yarn")
    except SandboxError:
        try:
            _run_local(["npm", "install"], cwd=repo_dir, env=env)
            logger.info("Dependencies installed with npm")
        except SandboxError as e:
            logger.warning(f"Dependency install failed (non-fatal): {e}")


# =====================================================
# INTERNAL HELPERS
# =====================================================


def _run_local(
    cmd: list[str],
    cwd: str | None = None,
    env: dict | None = None,
) -> str:
    """Run a command locally and return stdout. Raises SandboxError on failure."""
    full_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=full_env,
    )
    if result.returncode != 0:
        error_msg = result.stderr or result.stdout or "Unknown error"
        raise SandboxError(
            f"Command failed: {' '.join(cmd)}: {error_msg}"
        )
    return result.stdout
