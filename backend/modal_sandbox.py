"""
Modal sandbox management for isolated cloud VM code execution.
Replaces the old local filesystem SandboxManager.

Uses Modal's Sandbox API to provision cloud VMs with:
- git, gh CLI, claude CLI pre-installed
- ANTHROPIC_API_KEY and GITHUB_TOKEN injected as secrets
- Full repo clone + branch creation
"""

import os
import logging
import shlex
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

import modal

from models import RepoConfig

logger = logging.getLogger(__name__)


# =====================================================
# MODAL IMAGE DEFINITION
# =====================================================

# Pre-built image with all tools needed for coding
sandbox_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "curl", "jq", "tree")
    # Install GitHub CLI
    .run_commands(
        "curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg "
        "| dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg",
        'echo "deb [arch=$(dpkg --print-architecture) '
        "signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] "
        'https://cli.github.com/packages stable main" '
        "| tee /etc/apt/sources.list.d/github-cli.list > /dev/null",
        "apt-get update && apt-get install -y gh",
    )
    # Install Claude Code CLI
    .run_commands(
        "curl -fsSL https://deb.nodesource.com/setup_20.x | bash -",
        "apt-get install -y nodejs",
        "npm install -g @anthropic-ai/claude-code",
    )
)

# Modal app reference (created at module level for decorator usage)
app = modal.App("treehacks-sandbox")


# =====================================================
# DATA CLASSES
# =====================================================


@dataclass
class SandboxContext:
    """Context for a sandbox environment (Modal or local)."""
    sandbox: Any  # modal.Sandbox or local_sandbox.LocalSandbox
    repo_dir: str  # Path inside the sandbox (e.g., /root/repo)
    branch_name: str
    git_remote: str


# =====================================================
# EXCEPTIONS
# =====================================================


class SandboxError(Exception):
    """Base exception for sandbox operations."""
    pass


class CloneError(SandboxError):
    """Repository cloning failed."""
    pass


class BranchError(SandboxError):
    """Branch creation/management failed."""
    pass


# =====================================================
# SANDBOX MANAGER
# =====================================================


class ModalSandboxManager:
    """Manages Modal cloud sandbox environments for code execution."""

    def __init__(self):
        self.app = app

    def create(
        self,
        project_id: UUID,
        repo_config: RepoConfig,
        timeout: int = 1800,
    ) -> SandboxContext:
        """
        Create a new Modal sandbox environment.

        Args:
            project_id: Project UUID
            repo_config: Repository configuration
            timeout: Sandbox timeout in seconds (default 30 min)

        Returns:
            SandboxContext with sandbox handle and metadata

        Raises:
            SandboxError: If sandbox creation fails
        """
        branch_name = f"fix/issue-{str(project_id)[:8]}"
        git_remote = self._build_git_remote(repo_config)
        repo_dir = "/root/repo"

        logger.info(
            f"Creating Modal sandbox for project {project_id} "
            f"(repo: {repo_config.github_owner}/{repo_config.github_repo})"
        )

        try:
            # Build secrets from environment or repo_config
            github_token = repo_config.github_token or os.getenv("GITHUB_TOKEN", "")
            anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

            # Create the sandbox with pre-built image
            # App.lookup is required when running outside of a Modal container
            sandbox_app = modal.App.lookup("treehacks-sandbox", create_if_missing=True)

            sandbox = modal.Sandbox.create(
                image=sandbox_image,
                timeout=timeout,
                encrypted_ports=[],
                secrets=[
                    modal.Secret.from_dict({
                        "ANTHROPIC_API_KEY": anthropic_key,
                        "GITHUB_TOKEN": github_token,
                        "GH_TOKEN": github_token,  # gh CLI uses GH_TOKEN
                    })
                ],
                app=sandbox_app,
            )

            logger.info(f"Modal sandbox created, cloning repository...")

            # Clone repository inside the sandbox
            self._exec_in_sandbox(
                sandbox,
                "git",
                "clone",
                "--branch", repo_config.github_branch,
                "--depth", "1",
                git_remote,
                repo_dir,
            )

            logger.info(f"Repository cloned, creating branch {branch_name}...")

            # Create feature branch
            self._exec_in_sandbox(
                sandbox,
                "git", "checkout", "-b", branch_name,
                workdir=repo_dir,
            )

            # Configure git user for commits
            self._exec_in_sandbox(
                sandbox,
                "git", "config", "user.email", "bot@treehacks.dev",
                workdir=repo_dir,
            )
            self._exec_in_sandbox(
                sandbox,
                "git", "config", "user.name", "TreeHacks Bot",
                workdir=repo_dir,
            )

            # Authenticate gh CLI with token
            self._exec_in_sandbox(
                sandbox,
                "gh", "auth", "setup-git",
                workdir=repo_dir,
            )

            logger.info(f"Sandbox ready for project {project_id}")

            return SandboxContext(
                sandbox=sandbox,
                repo_dir=repo_dir,
                branch_name=branch_name,
                git_remote=git_remote,
            )

        except Exception as e:
            logger.error(f"Failed to create sandbox: {e}")
            raise SandboxError(f"Failed to create Modal sandbox: {e}")

    def cleanup(self, sandbox_ctx: SandboxContext) -> None:
        """Terminate the Modal sandbox."""
        try:
            sandbox_ctx.sandbox.terminate()
            logger.info("Modal sandbox terminated")
        except Exception as e:
            logger.warning(f"Failed to terminate sandbox (non-fatal): {e}")

    def _build_git_remote(self, repo_config: RepoConfig) -> str:
        """Build Git remote URL from repo config, embedding token for auth."""
        token = repo_config.github_token or os.getenv("GITHUB_TOKEN", "")
        if token:
            return (
                f"https://x-access-token:{token}@github.com/"
                f"{repo_config.github_owner}/{repo_config.github_repo}.git"
            )
        return (
            f"https://github.com/{repo_config.github_owner}/"
            f"{repo_config.github_repo}.git"
        )

    def _exec_in_sandbox(
        self,
        sandbox: modal.Sandbox,
        *cmd: str,
        workdir: Optional[str] = None,
    ) -> str:
        """
        Execute a command inside the Modal sandbox.

        Args:
            sandbox: Modal Sandbox instance
            *cmd: Command and arguments
            workdir: Working directory inside sandbox

        Returns:
            Combined stdout output

        Raises:
            SandboxError: If command fails
        """
        exec_args = list(cmd)

        # If workdir is needed, wrap in a shell command
        if workdir:
            shell_cmd = f"cd {shlex.quote(workdir)} && " + " ".join(
                shlex.quote(c) for c in cmd
            )
            process = sandbox.exec("bash", "-c", shell_cmd)
        else:
            process = sandbox.exec(*exec_args)

        stdout = process.stdout.read()
        stderr = process.stderr.read()
        process.wait()
        returncode = process.returncode

        if returncode != 0:
            error_msg = stderr or stdout or "Unknown error"
            logger.error(f"Sandbox exec failed: {' '.join(cmd)} -> {error_msg}")
            raise SandboxError(
                f"Command failed in sandbox: {' '.join(cmd)}: {error_msg}"
            )

        return stdout


# =====================================================
# SANDBOX HELPER FUNCTIONS
# =====================================================


def exec_in_sandbox(
    sandbox_ctx: SandboxContext,
    *cmd: str,
    timeout: int = 300,
) -> str:
    """
    Execute a command in the sandbox's repo directory.

    Convenience wrapper that always runs in the repo directory.

    Args:
        sandbox_ctx: SandboxContext
        *cmd: Command and arguments
        timeout: Timeout in seconds

    Returns:
        stdout output
    """
    shell_cmd = f"cd {shlex.quote(sandbox_ctx.repo_dir)} && " + " ".join(
        shlex.quote(c) for c in cmd
    )
    process = sandbox_ctx.sandbox.exec("bash", "-c", shell_cmd)
    stdout = process.stdout.read()
    stderr = process.stderr.read()
    process.wait()
    returncode = process.returncode

    if returncode != 0:
        error_msg = stderr or stdout or "Unknown error"
        raise SandboxError(f"Command failed: {' '.join(cmd)}: {error_msg}")

    return stdout


def commit_changes(sandbox_ctx: SandboxContext, message: str) -> None:
    """Commit all changes in the sandbox repo."""
    exec_in_sandbox(sandbox_ctx, "git", "add", ".")
    exec_in_sandbox(sandbox_ctx, "git", "commit", "-m", message)
    logger.info(f"Committed changes: {message}")


def push_branch(sandbox_ctx: SandboxContext) -> None:
    """Push branch to remote from within the sandbox."""
    exec_in_sandbox(
        sandbox_ctx,
        "git", "push", "-u", "origin", sandbox_ctx.branch_name,
    )
    logger.info(f"Pushed branch: {sandbox_ctx.branch_name}")


def get_git_diff(sandbox_ctx: SandboxContext) -> str:
    """Get current git diff in the sandbox."""
    try:
        return exec_in_sandbox(sandbox_ctx, "git", "diff", "HEAD")
    except SandboxError:
        return ""


def get_git_status(sandbox_ctx: SandboxContext) -> str:
    """Get current git status in the sandbox."""
    return exec_in_sandbox(sandbox_ctx, "git", "status", "--short")


def get_repo_structure(sandbox_ctx: SandboxContext) -> str:
    """Get repository structure using tree command."""
    try:
        # Use a single quoted string for -I pattern to prevent bash from
        # interpreting pipes and globs
        shell_cmd = (
            f"cd {sandbox_ctx.repo_dir} && "
            "tree -L 3 -I 'node_modules|__pycache__|*.pyc|.git|dist|build|.next|target|venv' "
            "--dirsfirst -a --noreport"
        )
        process = sandbox_ctx.sandbox.exec("bash", "-c", shell_cmd)
        stdout = process.stdout.read()
        stderr = process.stderr.read()
        process.wait()
        if process.returncode != 0:
            raise SandboxError(f"tree failed: {stderr or stdout}")
        return stdout
    except SandboxError as e:
        logger.warning(f"tree command failed: {e}")
        return exec_in_sandbox(sandbox_ctx, "find", ".", "-maxdepth", "3", "-type", "f")


# =====================================================
# CONVENIENCE FUNCTIONS
# =====================================================


def create_sandbox(
    project_id: UUID, repo_config: RepoConfig
) -> SandboxContext:
    """Convenience function to create a sandbox."""
    manager = ModalSandboxManager()
    return manager.create(project_id, repo_config)


def cleanup_sandbox(sandbox_ctx: SandboxContext) -> None:
    """Convenience function to cleanup a sandbox."""
    manager = ModalSandboxManager()
    manager.cleanup(sandbox_ctx)
