"""
Sandbox: clone repo, create branch, commit, push. Optional context cache.
"""

import subprocess
import shutil
import json
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any
from uuid import UUID
from models import RepoConfig

logger = logging.getLogger(__name__)


@dataclass
class SandboxContext:
    sandbox_dir: Path
    repo_path: Path
    branch_name: str
    git_remote: str


def _base_path() -> Path:
    return Path(__file__).resolve().parent.parent / ".vector" / "sandbox"


def create_sandbox(project_id: str, repo_config: RepoConfig) -> SandboxContext:
    """Clone repo into .vector/sandbox/{project_id}, create branch, return context."""
    base = _base_path()
    sandbox_dir = base / str(project_id)
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    repo_path = sandbox_dir / repo_config.github_repo
    if repo_path.exists():
        shutil.rmtree(repo_path)
    repo_url = f"https://github.com/{repo_config.github_owner}/{repo_config.github_repo}.git"
    subprocess.run(
        ["git", "clone", "--branch", repo_config.github_branch, repo_url, str(repo_path)],
        check=True,
        capture_output=True,
    )
    branch_name = f"vector/{project_id}"[:60]
    subprocess.run(["git", "checkout", "-b", branch_name], cwd=repo_path, check=True, capture_output=True)
    return SandboxContext(
        sandbox_dir=sandbox_dir,
        repo_path=repo_path,
        branch_name=branch_name,
        git_remote=repo_url,
    )


def get_existing_sandbox(project_id: str) -> Optional[SandboxContext]:
    """Return existing sandbox context if sandbox dir and repo exist."""
    base = _base_path()
    sandbox_dir = base / str(project_id)
    if not sandbox_dir.exists():
        return None
    # Repo folder name is from config; we don't have it here, so look for a single dir
    subdirs = [d for d in sandbox_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
    if len(subdirs) != 1:
        return None
    repo_path = subdirs[0]
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        branch_name = r.stdout.strip() if r.returncode == 0 else f"vector/{project_id}"
    except Exception:
        branch_name = f"vector/{project_id}"
    return SandboxContext(
        sandbox_dir=sandbox_dir,
        repo_path=repo_path,
        branch_name=branch_name,
        git_remote="",
    )


def cleanup_sandbox(project_id: str, keep_on_success: bool = False) -> None:
    """Remove sandbox directory for project."""
    base = _base_path()
    sandbox_dir = base / str(project_id)
    if sandbox_dir.exists():
        shutil.rmtree(sandbox_dir)
        logger.info("Cleaned up sandbox %s", project_id)


def commit_changes(repo_path: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo_path, check=True, capture_output=True)


def push_branch(repo_path: Path, branch_name: str) -> None:
    subprocess.run(
        ["git", "push", "-u", "origin", branch_name],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )


def save_repo_context(project_id: UUID, context: Dict[str, Any]) -> None:
    base = _base_path()
    sandbox_dir = base / str(project_id)
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    path = sandbox_dir / "context.json"
    path.write_text(json.dumps(context, indent=2))


def load_repo_context(project_id: str) -> Optional[Dict[str, Any]]:
    base = _base_path()
    path = base / str(project_id) / "context.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())
