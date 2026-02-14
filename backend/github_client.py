"""
GitHub integration via gh CLI. Issue creation and PR creation.
"""

import subprocess
import json
import logging
from dataclasses import dataclass
from typing import List
from models import RepoConfig

logger = logging.getLogger(__name__)


@dataclass
class GitHubIssue:
    number: int
    title: str
    body: str
    labels: List[str]
    author: str
    created_at: str
    state: str


@dataclass
class PullRequest:
    number: int
    url: str


def _gh_env(repo_config: RepoConfig) -> dict:
    env = {}
    if repo_config.github_token:
        env["GH_TOKEN"] = repo_config.github_token
    return env


def create_issue(
    title: str,
    body: str,
    labels: List[str],
    repo_config: RepoConfig,
) -> GitHubIssue:
    """Create a GitHub issue. Uses gh CLI."""
    repo = f"{repo_config.github_owner}/{repo_config.github_repo}"
    cmd = [
        "gh", "issue", "create",
        "--repo", repo,
        "--title", title,
        "--body", body,
    ]
    for label in labels:
        cmd.extend(["--label", label])
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env={**_gh_env(repo_config), **subprocess.os.environ},
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh issue create failed: {result.stderr}")
    # Parse issue number from output (e.g. "https://github.com/owner/repo/issues/123")
    out = result.stdout.strip()
    try:
        num = int(out.split("/")[-1]) if "/" in out else int(out)
    except ValueError:
        num = 0
    return GitHubIssue(
        number=num,
        title=title,
        body=body,
        labels=labels,
        author="",
        created_at="",
        state="open",
    )


def create_pull_request(sandbox_context, github_issue: GitHubIssue, verification_results, repo_config: RepoConfig) -> PullRequest:
    """Create PR from current branch in sandbox. Uses gh CLI from repo path."""
    import os
    repo_path = getattr(sandbox_context, "repo_path", sandbox_context)
    if hasattr(repo_path, "__fspath__"):
        repo_path = os.fspath(repo_path)
    branch = getattr(sandbox_context, "branch_name", None) or "vector-auto"
    title = f"Fix: {github_issue.title}"
    body = f"Fixes #{github_issue.number}\n\n{github_issue.body}"
    repo = f"{repo_config.github_owner}/{repo_config.github_repo}"
    cmd = [
        "gh", "pr", "create",
        "--repo", repo,
        "--base", repo_config.github_branch,
        "--head", branch,
        "--title", title,
        "--body", body,
    ]
    result = subprocess.run(
        cmd,
        cwd=repo_path,
        capture_output=True,
        text=True,
        env={**_gh_env(repo_config), **subprocess.os.environ},
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh pr create failed: {result.stderr}")
    out = result.stdout.strip()
    # Parse PR number from URL
    try:
        num = int(out.split("/")[-1]) if "/" in out else 0
    except ValueError:
        num = 0
    url = out if out.startswith("http") else f"https://github.com/{repo}/pull/{num}"
    return PullRequest(number=num, url=url)
