"""
Claude (Anthropic) API integration: SMS feedback, plan generation, issue enrichment, tweet aggregation.
"""

import os
import json
import logging
from typing import Optional, List, Dict, Any

from anthropic import Anthropic

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-3-5-haiku-20241022"

FEEDBACK_SYSTEM_PROMPT = """You are a friendly feedback assistant over SMS. Your only job is to gather clear, actionable feedback from the user.

- Keep replies SHORT (SMS-friendly: 1-3 sentences, under 320 chars when possible).
- Be conversational and warm. Ask one question at a time.
- If the user's message is vague, brief, or unclear, ask a single short follow-up to clarify (e.g., "What worked best?" "Anything we could improve?").
- Once you have clear, specific feedback (what they liked, what could improve, or a clear "no feedback"), acknowledge it and thank them (e.g. "Thanks, we've got your feedback!").
- When you have gathered clear feedback and are thanking the user, you MUST end your reply with exactly a newline, then "FEEDBACK_SUMMARY:" and then a single line summarizing the feedback (e.g. "FEEDBACK_SUMMARY: User wants dark mode and faster load times"). This line is for our database only and will not be shown to the user.
- Do not lecture, repeat long summaries, or send paragraphs. Emojis are OK sparingly.
- If the user says they're done or have nothing to add, accept that and thank them, and still add FEEDBACK_SUMMARY: with a short summary (e.g. "No additional feedback")."""


def get_client() -> Anthropic:
    """Return Anthropic client (lazy init with API key from env)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable is required")
    return Anthropic(api_key=api_key)


def get_feedback_reply(
    user_message: str,
    history: list[dict],
    model: Optional[str] = None,
) -> tuple[str, Optional[str]]:
    """
    Get Claude's reply for the next turn in a feedback conversation.

    Args:
        user_message: Latest message from the user (SMS body).
        history: List of {"role": "user"|"assistant", "content": "..."} (no system message).
        model: Optional model override; default from env or claude-3-5-haiku.

    Returns:
        (reply_text, summary_or_none). summary_or_none is set when Claude has determined
        clear feedback (FEEDBACK_SUMMARY: ... in the reply); then reply_text is the part
        to show the user (without the FEEDBACK_SUMMARY line).
    """
    model = model or os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")
    client = get_client()

    messages = []
    for turn in history:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": user_message})

    resp = client.messages.create(
        model=model,
        max_tokens=350,
        system=FEEDBACK_SYSTEM_PROMPT,
        messages=messages,
    )

    text = ""
    for block in resp.content:
        if hasattr(block, "text"):
            text += block.text
    text = text.strip() or "Thanks for your message!"

    summary = None
    if "FEEDBACK_SUMMARY:" in text:
        parts = text.split("FEEDBACK_SUMMARY:", 1)
        user_part = parts[0].strip()
        summary = parts[1].strip() if len(parts) > 1 else ""
        return (user_part or "Thanks for your feedback!", summary if summary else None)
    return (text, None)


def _chat(model: str, system: str, user_content: str, max_tokens: int = 1024) -> str:
    client = get_client()
    resp = client.messages.create(
        model=model or os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL),
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    text = ""
    for block in resp.content:
        if hasattr(block, "text"):
            text += block.text
    return text.strip()


def generate_plan(
    tweet_texts: List[str],
    repo_owner: str,
    repo_name: str,
    repo_branch: str = "main",
    repo_context: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate implementation plan from user feedback (no code snippets)."""
    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
    tweets_summary = "\n".join([f"- {t}" for t in tweet_texts])
    context_section = f"Repo: {repo_owner}/{repo_name} Branch: {repo_branch}"
    if repo_context:
        context_section += f"\nLanguage: {repo_context.get('primary_language')}\nTest: {repo_context.get('test_framework')}\nStructure:\n{repo_context.get('structure_summary', '')}"
    system = "You are an expert software architect. Generate clear implementation plans. No code snippets—only file paths and descriptions."
    user_msg = f"User feedback:\n{tweets_summary}\n\n{context_section}\n\nGenerate a PLAN.md: Summary, Files to Modify, Implementation Steps, Testing, Risks. Markdown only, no code blocks."
    return _chat(model, system, user_msg, max_tokens=2000)


def enrich_issue_with_context(title: str, description: str, repo_context: Dict[str, Any]) -> Dict[str, str]:
    """Enrich issue title/description with codebase context."""
    prompt = f"Original title: {title}\nDescription: {description}\nRepo: {repo_context}\nEnhance with file paths and technical context. No code snippets. Output JSON: {{\"title\": \"...\", \"description\": \"...\"}}"
    out = _chat(DEFAULT_MODEL, "Output valid JSON only.", prompt, max_tokens=1500)
    try:
        data = json.loads(out)
        return {"title": data.get("title", title)[:80], "description": data.get("description", description)}
    except Exception:
        return {"title": title, "description": description}


def verify_issue_formatting(title: str, description: str) -> Dict[str, str]:
    """Clean title and description formatting. Output JSON."""
    prompt = f"Title: {title}\nDescription: {description}\nClean markdown, no code. Output JSON: {{\"title\": \"...\", \"description\": \"...\"}}"
    out = _chat(DEFAULT_MODEL, "Output valid JSON only.", prompt, max_tokens=1500)
    try:
        data = json.loads(out)
        return {"title": (data.get("title", title) or title)[:80], "description": data.get("description", description) or description}
    except Exception:
        return {"title": title, "description": description}


def aggregate_tweets_into_project(tweet_texts: List[str]) -> Dict[str, str]:
    """Aggregate tweets into one project title, description, ticket_type."""
    summary = "\n".join([f"{i+1}. {t}" for i, t in enumerate(tweet_texts)])
    prompt = f"Tweets:\n{summary}\n\nOutput JSON: {{\"title\": \"short title\", \"description\": \"markdown description\", \"ticket_type\": \"feature|bug|enhancement|question\"}}"
    out = _chat(DEFAULT_MODEL, "Output valid JSON only.", prompt, max_tokens=1500)
    try:
        data = json.loads(out)
        tt = data.get("ticket_type", "feature")
        if tt not in ("bug", "feature", "enhancement", "question"):
            tt = "feature"
        return {"title": data.get("title", "User feedback"), "description": data.get("description", summary), "ticket_type": tt}
    except Exception:
        return {"title": "User feedback", "description": summary, "ticket_type": "feature"}
