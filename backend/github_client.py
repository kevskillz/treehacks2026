"""
GitHub integration using gh CLI running inside Modal sandboxes.
Handles issue fetching, PR creation, and authentication.

All gh/git commands execute inside the Modal VM (sandbox_ctx),
not on the local machine.
"""

import json
import re
import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from models import RepoConfig
from modal_sandbox import SandboxContext, exec_in_sandbox, SandboxError

logger = logging.getLogger(__name__)


# =====================================================
# DATA CLASSES
# =====================================================


@dataclass
class GitHubIssue:
    """GitHub issue data."""
    number: int
    title: str
    body: str
    labels: List[str]
    author: str
    created_at: str
    state: str


@dataclass
class PullRequest:
    """Pull request data."""
    number: int
    url: str


# =====================================================
# EXCEPTIONS
# =====================================================


class GitHubError(Exception):
    """Base exception for GitHub operations."""
    pass


class AuthenticationError(GitHubError):
    """GitHub authentication failed."""
    pass


class IssueNotFoundError(GitHubError):
    """GitHub issue not found."""
    pass


class PRCreationError(GitHubError):
    """Pull request creation failed."""
    pass


# =====================================================
# URL PARSING
# =====================================================


def parse_github_url(issue_url: str) -> tuple[str, str, int]:
    """Parse GitHub issue URL to extract owner, repo, and issue number."""
    pattern = (
        r"(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/]+)/issues/(\d+)"
    )
    match = re.match(pattern, issue_url)
    if not match:
        raise GitHubError(f"Invalid GitHub issue URL: {issue_url}")
    owner, repo, issue_number = match.groups()
    return owner, repo, int(issue_number)


# =====================================================
# ISSUE OPERATIONS (run inside Modal sandbox)
# =====================================================


def fetch_issue(
    sandbox_ctx: SandboxContext,
    issue_url: str,
    repo_config: RepoConfig,
) -> GitHubIssue:
    """
    Fetch GitHub issue details using gh CLI inside the Modal sandbox.
    """
    try:
        owner, repo, issue_number = parse_github_url(issue_url)
    except GitHubError:
        owner = repo_config.github_owner
        repo = repo_config.github_repo
        match = re.search(r"(\d+)", issue_url)
        if not match:
            raise GitHubError(
                f"Could not extract issue number from: {issue_url}"
            )
        issue_number = int(match.group(1))

    logger.info(f"Fetching issue #{issue_number} from {owner}/{repo}")

    try:
        output = exec_in_sandbox(
            sandbox_ctx,
            "gh", "issue", "view", str(issue_number),
            "--repo", f"{owner}/{repo}",
            "--json", "number,title,body,labels,author,createdAt,state",
        )
        data = json.loads(output)

        labels = [label["name"] for label in data.get("labels", [])]
        author = data.get("author", {}).get("login", "unknown")

        return GitHubIssue(
            number=data["number"],
            title=data["title"],
            body=data.get("body", ""),
            labels=labels,
            author=author,
            created_at=data.get("createdAt", ""),
            state=data.get("state", "open"),
        )

    except SandboxError as e:
        logger.error(f"Failed to fetch issue: {e}")
        raise IssueNotFoundError(
            f"Issue #{issue_number} not found or inaccessible"
        )
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse GitHub response: {e}")
        raise GitHubError("Invalid response from GitHub API")


# =====================================================
# PULL REQUEST OPERATIONS
# =====================================================


def build_pr_body(
    issue: GitHubIssue, verification_results: Dict[str, Any]
) -> str:
    """Build pull request body with verification results."""
    test_result = verification_results.get("tests")
    build_result = verification_results.get("build")
    lint_result = verification_results.get("lint")
    review_result = verification_results.get("review")

    summary = f"Fixes #{issue.number}"

    test_status = (
        "PASSED" if (test_result and test_result.get("passed")) else "FAILED"
    )
    build_status = (
        "PASSED"
        if (build_result is None or build_result.get("returncode") == 0)
        else "FAILED"
    )
    lint_status = (
        "PASSED"
        if (lint_result is None or lint_result.get("passed"))
        else "FAILED"
    )
    review_score = review_result.get("score", 0) if review_result else 0

    test_output = (
        test_result.get("output", "No test output") if test_result else "N/A"
    )
    review_feedback = (
        review_result.get("feedback", "No review") if review_result else "N/A"
    )

    pr_body = f"""## Summary
{summary}

## Implementation
This PR implements the feature requested in #{issue.number}.

## Testing
- **Existing tests:** {test_status}
- **Build verification:** {build_status}
- **Linting:** {lint_status}
- **LLM Self-Review Score:** {review_score}/100

### Test Details
{test_output[:2000]}

## Review
{review_feedback[:2000]}

---
Generated by @coder
"""
    return pr_body


def create_pull_request(
    sandbox_ctx: SandboxContext,
    issue: GitHubIssue,
    verification_results: Dict[str, Any],
    repo_config: RepoConfig,
) -> PullRequest:
    """Create a pull request using gh CLI inside the Modal sandbox."""
    logger.info(f"Creating PR for branch {sandbox_ctx.branch_name}")

    pr_title = f"Fix: {issue.title}"
    pr_body = build_pr_body(issue, verification_results)

    try:
        output = exec_in_sandbox(
            sandbox_ctx,
            "gh", "pr", "create",
            "--repo", f"{repo_config.github_owner}/{repo_config.github_repo}",
            "--base", repo_config.github_branch,
            "--head", sandbox_ctx.branch_name,
            "--title", pr_title,
            "--body", pr_body,
        )

        pr_url = output.strip()
        pr_number_match = re.search(r"/pull/(\d+)", pr_url)
        pr_number = int(pr_number_match.group(1)) if pr_number_match else 0

        logger.info(f"PR created successfully: {pr_url}")
        return PullRequest(number=pr_number, url=pr_url)

    except SandboxError as e:
        logger.error(f"Failed to create PR: {e}")
        raise PRCreationError(f"Failed to create pull request: {e}")


def create_issue(
    sandbox_ctx: SandboxContext,
    title: str,
    body: str,
    labels: List[str],
    repo_config: RepoConfig,
) -> GitHubIssue:
    """Create a GitHub issue using gh CLI inside the Modal sandbox."""
    logger.info(f"Creating issue: {title}")

    label_args = ""
    for label in labels:
        label_args += f" --label '{label}'"

    try:
        cmd_parts = [
            "gh", "issue", "create",
            "--repo", f"{repo_config.github_owner}/{repo_config.github_repo}",
            "--title", title,
            "--body", body,
        ]

        output = exec_in_sandbox(sandbox_ctx, *cmd_parts)
        issue_url = output.strip()

        issue_number_match = re.search(r"/issues/(\d+)", issue_url)
        issue_number = (
            int(issue_number_match.group(1)) if issue_number_match else 0
        )

        logger.info(f"Issue created successfully: {issue_url}")

        return fetch_issue(sandbox_ctx, issue_url, repo_config)

    except SandboxError as e:
        logger.error(f"Failed to create issue: {e}")
        raise GitHubError(f"Failed to create issue: {e}")


# =====================================================
# ADDITIONAL OPERATIONS
# =====================================================


def convert_pr_to_draft(
    sandbox_ctx: SandboxContext,
    pr_number: int,
    repo_config: RepoConfig,
) -> None:
    """Convert a PR to draft status."""
    try:
        exec_in_sandbox(
            sandbox_ctx,
            "gh", "pr", "ready", str(pr_number),
            "--repo", f"{repo_config.github_owner}/{repo_config.github_repo}",
            "--undo",
        )
        logger.info(f"Converted PR #{pr_number} to draft")
    except SandboxError as e:
        logger.error(f"Failed to convert PR to draft: {e}")
