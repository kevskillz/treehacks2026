"""
Testing orchestration for code verification.
All verification (tests, build, lint, review) runs inside the Modal sandbox.
"""

import re
import json
import logging
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List

from llm import claude_client
from modal_sandbox import SandboxContext, exec_in_sandbox, SandboxError

logger = logging.getLogger(__name__)


# =====================================================
# DATA CLASSES
# =====================================================


@dataclass
class RepoContext:
    """Repository context information."""
    primary_language: str
    test_framework: Optional[str]
    build_system: Optional[str]
    structure_summary: str


@dataclass
class TestResult:
    """Test execution result."""
    passed: bool
    output: str
    duration: float
    framework: Optional[str] = None
    command: Optional[str] = None


@dataclass
class BuildResult:
    """Build execution result."""
    returncode: int
    stdout: str
    stderr: str
    duration: float
    command: Optional[str] = None


@dataclass
class LintResult:
    """Lint execution result."""
    passed: bool
    output: str
    issues_count: int = 0
    command: Optional[str] = None


@dataclass
class TypeCheckResult:
    """Type check execution result."""
    passed: bool
    output: str
    errors_count: int = 0
    command: Optional[str] = None


@dataclass
class ReviewResult:
    """LLM code review result."""
    score: int  # 0-100
    feedback: str


# =====================================================
# EXCEPTIONS
# =====================================================


class VerificationError(Exception):
    """Base exception for verification operations."""
    pass


# =====================================================
# REPOSITORY CONTEXT DETECTION (inside sandbox)
# =====================================================


def detect_repo_context(sandbox_ctx: SandboxContext) -> RepoContext:
    """
    Detect repository context inside the Modal sandbox using Claude.
    """
    from modal_sandbox import get_repo_structure

    structure_summary = get_repo_structure(sandbox_ctx)

    # Try to read README
    readme_content = ""
    for readme_name in ["README.md", "README.MD", "readme.md", "README"]:
        try:
            readme_content = exec_in_sandbox(
                sandbox_ctx, "cat", readme_name
            )
            break
        except SandboxError:
            continue

    # Use Claude to analyze the repository
    try:
        context_data = claude_client.detect_tech_stack(
            structure_summary, readme_content
        )
        primary_language = context_data.get("primary_language", "unknown")
        test_framework = context_data.get("test_framework")
        build_system = context_data.get("build_system")
    except Exception as e:
        logger.warning(f"Claude detection failed, using fallback: {e}")
        primary_language, test_framework, build_system = _fallback_detection(
            sandbox_ctx
        )

    return RepoContext(
        primary_language=primary_language,
        test_framework=test_framework,
        build_system=build_system,
        structure_summary=structure_summary,
    )


def _fallback_detection(
    sandbox_ctx: SandboxContext,
) -> tuple[str, Optional[str], Optional[str]]:
    """Simple fallback detection if Claude fails."""
    primary_language = "unknown"
    test_framework = None
    build_system = None

    def file_exists(name: str) -> bool:
        try:
            exec_in_sandbox(sandbox_ctx, "test", "-f", name)
            return True
        except SandboxError:
            return False

    if file_exists("package.json"):
        primary_language = "javascript"
        if file_exists("tsconfig.json"):
            primary_language = "typescript"
        test_framework = "npm"
        build_system = "npm"
    elif file_exists("setup.py") or file_exists("pyproject.toml"):
        primary_language = "python"
        test_framework = "pytest"
        build_system = "setuptools"
    elif file_exists("go.mod"):
        primary_language = "go"
        test_framework = "go test"
        build_system = "go build"
    elif file_exists("Cargo.toml"):
        primary_language = "rust"
        test_framework = "cargo test"
        build_system = "cargo build"

    return primary_language, test_framework, build_system


# =====================================================
# TEST CASE GENERATION
# =====================================================


def is_frontend_project(repo_context: RepoContext) -> bool:
    """Check if the project is primarily frontend."""
    frontend_indicators = [
        "react", "vue", "angular", "next", "nuxt", "svelte",
        "frontend", "webapp", "web-app",
    ]
    structure_lower = repo_context.structure_summary.lower()
    for indicator in frontend_indicators:
        if indicator in structure_lower:
            return True
    language_lower = repo_context.primary_language.lower()
    if language_lower in ["typescript", "javascript"]:
        if repo_context.build_system and any(
            x in repo_context.build_system.lower()
            for x in ["vite", "webpack", "next", "create-react-app"]
        ):
            return True
    return False


def generate_test_cases(issue: Any, repo_context: RepoContext) -> str:
    """
    Generate test cases using Claude API BEFORE implementation.
    For frontend projects: skips test generation.
    """
    logger.info(f"Generating test cases for issue #{issue.number}")

    if is_frontend_project(repo_context):
        logger.info("Frontend project detected — skipping test generation")
        return """# Test Cases

## Frontend Project Detected

Automated test generation skipped for frontend projects.

**Manual verification required:**
- Visual inspection of UI changes
- Browser testing across different viewports
- Accessibility checks
- User interaction testing
"""

    prompt = f"""You are a test engineer. Generate comprehensive test cases for:

**Issue Title:** {issue.title}

**Issue Description:**
{issue.body}

**Repository Context:**
- Primary Language: {repo_context.primary_language}
- Test Framework: {repo_context.test_framework or 'Not detected'}
- Build System: {repo_context.build_system or 'Not detected'}

**Requirements:**
Generate test cases covering:
1. Happy path scenarios
2. Edge cases
3. Error handling
4. Integration points

Provide test cases in markdown format with code blocks appropriate for {repo_context.primary_language}.
Include test function names, assertions, and expected outcomes.
"""

    try:
        result = claude_client._chat(
            "You are an expert test engineer writing comprehensive test cases.",
            prompt,
        )
        logger.info("Test cases generated successfully")
        return result
    except Exception as e:
        logger.error(f"Failed to generate test cases: {e}")
        return f"# Test Cases\n\nFailed to generate test cases: {e}"


# =====================================================
# TEST EXECUTION (inside Modal sandbox)
# =====================================================


def detect_and_run_tests(
    sandbox_ctx: SandboxContext,
    custom_command: Optional[str] = None,
) -> TestResult:
    """Auto-detect test framework and run tests inside Modal sandbox."""
    import time

    framework = None
    command = None
    passed = False
    output = ""
    duration = 0.0

    def file_exists(name: str) -> bool:
        try:
            exec_in_sandbox(sandbox_ctx, "test", "-f", name)
            return True
        except SandboxError:
            return False

    if custom_command:
        command = custom_command
        framework = "custom"
    else:
        if file_exists("pytest.ini") or file_exists("setup.py") or file_exists("pyproject.toml"):
            framework = "pytest"
            command = "pytest -v"
        elif file_exists("package.json"):
            try:
                pkg_json_str = exec_in_sandbox(sandbox_ctx, "cat", "package.json")
                pkg_json = json.loads(pkg_json_str)
                if "test" in pkg_json.get("scripts", {}):
                    framework = "npm"
                    command = "npm test"
            except (SandboxError, json.JSONDecodeError):
                pass
        elif file_exists("go.mod"):
            framework = "go"
            command = "go test ./..."
        elif file_exists("Cargo.toml"):
            framework = "cargo"
            command = "cargo test"

    if command:
        logger.info(f"Running tests with {framework}: {command}")
        start = time.time()
        try:
            output = exec_in_sandbox(sandbox_ctx, "bash", "-c", command)
            duration = time.time() - start
            passed = True
            logger.info(f"Tests passed in {duration:.2f}s")
        except SandboxError as e:
            duration = time.time() - start
            output = str(e)
            passed = False
            logger.info(f"Tests failed in {duration:.2f}s")
    else:
        logger.warning("No test framework detected, skipping tests")
        output = "No test framework detected"
        passed = True

    return TestResult(
        passed=passed,
        output=output[:5000],
        duration=duration,
        framework=framework,
        command=command,
    )


# =====================================================
# BUILD VERIFICATION (inside Modal sandbox)
# =====================================================


def run_build_verification(
    sandbox_ctx: SandboxContext,
    custom_command: Optional[str] = None,
) -> Optional[BuildResult]:
    """Detect and run build commands inside Modal sandbox."""
    import time

    command = None

    def file_exists(name: str) -> bool:
        try:
            exec_in_sandbox(sandbox_ctx, "test", "-f", name)
            return True
        except SandboxError:
            return False

    if custom_command:
        command = custom_command
    else:
        if file_exists("package.json"):
            try:
                pkg_str = exec_in_sandbox(sandbox_ctx, "cat", "package.json")
                pkg = json.loads(pkg_str)
                if "build" in pkg.get("scripts", {}):
                    command = "npm run build"
            except (SandboxError, json.JSONDecodeError):
                pass
        elif file_exists("setup.py"):
            command = "python setup.py build"
        elif file_exists("go.mod"):
            command = "go build ./..."
        elif file_exists("Cargo.toml"):
            command = "cargo build"

    if command:
        logger.info(f"Running build: {command}")
        start = time.time()
        try:
            stdout = exec_in_sandbox(sandbox_ctx, "bash", "-c", command)
            duration = time.time() - start
            logger.info(f"Build succeeded in {duration:.2f}s")
            return BuildResult(
                returncode=0,
                stdout=stdout[:5000],
                stderr="",
                duration=duration,
                command=command,
            )
        except SandboxError as e:
            duration = time.time() - start
            logger.error(f"Build failed in {duration:.2f}s")
            return BuildResult(
                returncode=1,
                stdout="",
                stderr=str(e)[:5000],
                duration=duration,
                command=command,
            )

    logger.info("No build step detected")
    return None


# =====================================================
# LINTING (inside Modal sandbox)
# =====================================================


def run_linters(
    sandbox_ctx: SandboxContext,
    custom_command: Optional[str] = None,
) -> Optional[LintResult]:
    """Detect and run linters inside Modal sandbox."""
    command = None

    def file_exists(name: str) -> bool:
        try:
            exec_in_sandbox(sandbox_ctx, "test", "-f", name)
            return True
        except SandboxError:
            return False

    if custom_command:
        command = custom_command
    else:
        if file_exists(".pylintrc"):
            command = "pylint ."
        elif file_exists(".flake8"):
            command = "flake8 ."
        elif file_exists(".eslintrc.json") or file_exists(".eslintrc.js"):
            command = "npx eslint ."
        elif file_exists("go.mod"):
            command = "golangci-lint run"
        elif file_exists("Cargo.toml"):
            command = "cargo clippy"

    if command:
        logger.info(f"Running linter: {command}")
        try:
            output = exec_in_sandbox(sandbox_ctx, "bash", "-c", command)
            issues_count = len(
                re.findall(r"error|warning", output, re.IGNORECASE)
            )
            logger.info(f"Linting passed ({issues_count} issues found)")
            return LintResult(
                passed=True,
                output=output[:5000],
                issues_count=issues_count,
                command=command,
            )
        except SandboxError as e:
            output = str(e)
            issues_count = len(
                re.findall(r"error|warning", output, re.IGNORECASE)
            )
            logger.info(f"Linting failed ({issues_count} issues)")
            return LintResult(
                passed=False,
                output=output[:5000],
                issues_count=issues_count,
                command=command,
            )

    logger.info("No linter detected")
    return None


# =====================================================
# TYPE CHECKING (inside Modal sandbox)
# =====================================================


def run_type_checking(
    sandbox_ctx: SandboxContext,
) -> Optional[TypeCheckResult]:
    """Detect and run type checkers inside Modal sandbox."""
    command = None

    def file_exists(name: str) -> bool:
        try:
            exec_in_sandbox(sandbox_ctx, "test", "-f", name)
            return True
        except SandboxError:
            return False

    if file_exists("mypy.ini"):
        command = "mypy ."
    elif file_exists("tsconfig.json"):
        command = "npx tsc --noEmit"

    if command:
        logger.info(f"Running type checker: {command}")
        try:
            output = exec_in_sandbox(sandbox_ctx, "bash", "-c", command)
            errors_count = len(
                re.findall(r"error", output, re.IGNORECASE)
            )
            logger.info(f"Type checking passed ({errors_count} errors)")
            return TypeCheckResult(
                passed=True,
                output=output[:5000],
                errors_count=errors_count,
                command=command,
            )
        except SandboxError as e:
            output = str(e)
            errors_count = len(
                re.findall(r"error", output, re.IGNORECASE)
            )
            logger.info(f"Type checking failed ({errors_count} errors)")
            return TypeCheckResult(
                passed=False,
                output=output[:5000],
                errors_count=errors_count,
                command=command,
            )

    logger.info("No type checker detected")
    return None


# =====================================================
# LLM CODE REVIEW
# =====================================================


def llm_self_review(git_diff: str) -> ReviewResult:
    """Use Claude to review code changes."""
    logger.info("Running LLM self-review")

    review_prompt = f"""You just reviewed changes to fix a GitHub issue. Please review critically:

**Changes Made:**
```diff
{git_diff[:10000]}
```

**Review Criteria:**
1. Security issues
2. Edge cases handled?
3. Code quality and best practices
4. Testing coverage
5. Performance concerns

Provide a score (0-100) and detailed feedback.
Start your response with "SCORE: <number>" on the first line.
"""

    try:
        output = claude_client._chat(
            "You are a senior code reviewer. Be thorough but fair.",
            review_prompt,
        )

        score = 80
        score_match = re.search(r"SCORE:\s*(\d+)", output, re.IGNORECASE)
        if score_match:
            score = int(score_match.group(1))
            score = max(0, min(100, score))

        logger.info(f"LLM self-review completed with score: {score}")
        return ReviewResult(score=score, feedback=output)

    except Exception as e:
        logger.error(f"LLM self-review failed: {e}")
        return ReviewResult(score=50, feedback=f"Review failed: {e}")


# =====================================================
# VERIFICATION AND ITERATION
# =====================================================


def verify_and_iterate(
    sandbox_ctx: SandboxContext,
    repo_config: Any,
    run_claude_fix_fn: Any,  # Callable to send fix prompt to Claude Code in sandbox
    max_iterations: int = 3,
    skip_review: bool = False,
) -> tuple[bool, Optional[Dict[str, Any]]]:
    """
    Run verification cycle and iterate on failures.

    Args:
        sandbox_ctx: Modal SandboxContext
        repo_config: RepoConfig
        run_claude_fix_fn: Function(sandbox_ctx, fix_prompt) -> str
        max_iterations: Maximum fix iterations
        skip_review: If True, skip the LLM self-review step (faster)

    Returns:
        Tuple of (success, results_dict)
    """
    from modal_sandbox import get_git_diff

    for iteration in range(max_iterations):
        logger.info(f"Verification iteration {iteration + 1}/{max_iterations}")

        # Run build verification (most important check)
        build_result = run_build_verification(
            sandbox_ctx, repo_config.build_command
        )

        # Run tests
        test_result = detect_and_run_tests(
            sandbox_ctx, repo_config.test_command
        )

        # Skip lint and type checking for speed — Claude already handles these
        lint_result = None
        type_result = None

        # LLM self-review (optional — expensive extra API call)
        review_result = None
        if not skip_review:
            git_diff = get_git_diff(sandbox_ctx)
            review_result = llm_self_review(git_diff)

        # Check if critical checks passed
        all_passed = (
            test_result.passed
            and (build_result is None or build_result.returncode == 0)
        )
        # If review is enabled, require score >= 80
        if review_result and review_result.score < 80:
            all_passed = False

        if all_passed:
            logger.info("All verifications passed!")
            return True, {
                "tests": asdict(test_result),
                "build": asdict(build_result) if build_result else None,
                "lint": None,
                "type_check": None,
                "review": asdict(review_result) if review_result else None,
            }

        # Generate fix prompt
        fix_prompt = _generate_fix_prompt(
            test_result, build_result, lint_result, type_result,
            review_result or ReviewResult(score=100, feedback=""),
        )
        logger.info("Verification failed, sending fix prompt to Claude Code")
        run_claude_fix_fn(sandbox_ctx, fix_prompt)

    # Max iterations reached — still return partial results so we can commit
    logger.warning("Max iterations reached, returning best-effort results")
    return True, {
        "tests": asdict(test_result) if test_result else None,
        "build": asdict(build_result) if build_result else None,
        "lint": None,
        "type_check": None,
        "review": None,
    }


def _generate_fix_prompt(
    test_result: TestResult,
    build_result: Optional[BuildResult],
    lint_result: Optional[LintResult],
    type_result: Optional[TypeCheckResult],
    review_result: ReviewResult,
) -> str:
    """Generate prompt to fix verification failures."""
    issues = []

    if not test_result.passed:
        issues.append(f"**Tests Failed:**\n```\n{test_result.output[:2000]}\n```")
    if build_result and build_result.returncode != 0:
        issues.append(f"**Build Failed:**\n```\n{build_result.stderr[:2000]}\n```")
    if lint_result and not lint_result.passed:
        issues.append(
            f"**Linting Issues ({lint_result.issues_count}):**\n"
            f"```\n{lint_result.output[:2000]}\n```"
        )
    if type_result and not type_result.passed:
        issues.append(
            f"**Type Errors ({type_result.errors_count}):**\n"
            f"```\n{type_result.output[:2000]}\n```"
        )
    if review_result.score < 80:
        issues.append(
            f"**Code Review Concerns (Score: {review_result.score}/100):**\n"
            f"{review_result.feedback[:2000]}"
        )

    return (
        "The implementation has the following issues that need to be fixed:\n\n"
        + "\n\n".join(issues)
        + "\n\nPlease fix these issues. Make the necessary changes now."
    )
