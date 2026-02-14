"""
Repo context detection and test-case generation using Claude.
Verification (run tests/build/lint) and iterate with Claude to fix.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class RepoContext:
    primary_language: str
    test_framework: Optional[str]
    build_system: Optional[str]
    structure_summary: str


def detect_repo_context(repo_path: Path) -> RepoContext:
    """Detect language, test framework, build system from repo (simple heuristics)."""
    repo_path = Path(repo_path)
    structure_parts = []
    primary_language = "unknown"
    test_framework = None
    build_system = None

    try:
        for p in repo_path.rglob("*"):
            if p.is_file() and ".git" not in str(p):
                rel = p.relative_to(repo_path)
                structure_parts.append(str(rel))
                name = p.name.lower()
                if name == "package.json":
                    build_system = "npm"
                    if (repo_path / "jest.config.js").exists() or "jest" in (repo_path / "package.json").read_text(errors="ignore"):
                        test_framework = "jest"
                    elif "vitest" in (repo_path / "package.json").read_text(errors="ignore"):
                        test_framework = "vitest"
                    primary_language = "javascript" if primary_language == "unknown" else primary_language
                elif name == "requirements.txt" or name == "pyproject.toml":
                    build_system = "pip"
                    test_framework = "pytest"
                    primary_language = "python"
                elif name == "go.mod":
                    build_system = "go"
                    test_framework = "go test"
                    primary_language = "go"
                elif name == "Cargo.toml":
                    build_system = "cargo"
                    test_framework = "cargo test"
                    primary_language = "rust"
    except Exception as e:
        logger.warning("detect_repo_context error: %s", e)

    structure_summary = "\n".join(sorted(structure_parts)[:200]) if structure_parts else "No files listed"
    if primary_language == "unknown" and build_system:
        primary_language = build_system
    return RepoContext(
        primary_language=primary_language or "unknown",
        test_framework=test_framework,
        build_system=build_system,
        structure_summary=structure_summary,
    )


def generate_test_cases_with_claude(issue, repo_context: RepoContext) -> str:
    """Generate test cases (markdown) for the issue using Claude."""
    from claude import get_client
    import os
    client = get_client()
    model = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")
    prompt = f"""Issue: {issue.title}
Description:
{issue.body}

Repo: {repo_context.primary_language}, test framework: {repo_context.test_framework or 'unknown'}.

Generate concise test cases in markdown (what to test, expected behavior). No code. Keep under 1500 chars."""
    resp = client.messages.create(
        model=model,
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    text = ""
    for block in resp.content:
        if hasattr(block, "text"):
            text += block.text
    return text.strip() or "Test cases: verify behavior manually."


@dataclass
class VerificationResults:
    """Results from verify step."""
    tests: Any
    build: Any
    lint: Any
    review: Any


def verify_and_iterate(
    sandbox_ctx,
    claude_session: Any,
    repo_config,
    max_iterations: int = 3,
) -> tuple[bool, VerificationResults]:
    """Run tests/build/lint; on failure send fix prompt to Claude session and retry."""
    repo_path = Path(getattr(sandbox_ctx, "repo_path", sandbox_ctx))
    test_cmd = repo_config.test_command or ("npm test" if (repo_path / "package.json").exists() else "pytest" if (repo_path / "requirements.txt").exists() else None)
    build_cmd = repo_config.build_command or ("npm run build" if (repo_path / "package.json").exists() else None)
    lint_cmd = repo_config.lint_command

    import subprocess
    results = VerificationResults(tests=None, build=None, lint=None, review=None)

    for iteration in range(max_iterations):
        test_ok = True
        if test_cmd:
            r = subprocess.run(test_cmd, shell=True, cwd=repo_path, capture_output=True, text=True, timeout=120)
            results.tests = type("T", (), {"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr})()
            test_ok = r.returncode == 0
        build_ok = True
        if build_cmd:
            r = subprocess.run(build_cmd, shell=True, cwd=repo_path, capture_output=True, text=True, timeout=180)
            results.build = type("B", (), {"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr})()
            build_ok = r.returncode == 0
        lint_ok = True
        if lint_cmd:
            r = subprocess.run(lint_cmd, shell=True, cwd=repo_path, capture_output=True, text=True, timeout=60)
            results.lint = type("L", (), {"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr})()
            lint_ok = r.returncode == 0

        results.review = type("R", (), {"summary": "ok"})()
        if test_ok and build_ok and lint_ok:
            return True, results

        fix_prompt = f"""Tests or build failed. Fix the code.
Test: {getattr(results.tests, 'stderr', '') or getattr(results.tests, 'stdout', '')}
Build: {getattr(results.build, 'stderr', '') or getattr(results.build, 'stdout', '') if results.build else 'N/A'}
Make minimal changes and ensure tests and build pass. Do not run interactive servers."""
        claude_session.send_prompt(fix_prompt)
        claude_session.read_output(timeout=180)

    return False, results
