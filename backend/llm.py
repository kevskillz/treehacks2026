"""
LLM integration using OpenAI SDK.
Handles plan generation, sentiment, tech-stack detection, and tweet aggregation.
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

from openai import OpenAI
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load .env file from the same directory as this script
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)

# OpenAI models
PLANNING_MODEL = "gpt-5-mini"
UTILITY_MODEL = "gpt-4.1-nano"


# Pydantic Models for structured outputs
class TechStack(BaseModel):
    """Repository tech stack information."""
    primary_language: str = Field(
        description="Main programming language (e.g., python, javascript, typescript)"
    )
    test_framework: Optional[str] = Field(
        default=None,
        description="Testing framework used (e.g., pytest, jest)",
    )
    build_system: Optional[str] = Field(
        default=None,
        description="Build/package manager (e.g., npm, setuptools, cargo)",
    )


class ProjectAggregation(BaseModel):
    """Aggregated project information from tweets."""
    title: str = Field(description="Concise, actionable title (max 80 chars)")
    description: str = Field(
        description="Comprehensive description combining all feedback in markdown"
    )
    ticket_type: str = Field(
        description="One of: bug, feature, enhancement, question"
    )


class OpenAIClient:
    """Client for OpenAI API."""

    def __init__(self):
        """Initialize OpenAI client with API key."""
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def _chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = UTILITY_MODEL,
    ) -> str:
        """Send a single-turn chat message via OpenAI and return the text response."""
        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content

    def _chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = UTILITY_MODEL,
    ) -> str:
        """Send a chat message with response_format=json_object to guarantee valid JSON."""
        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content

    def _planning_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = PLANNING_MODEL,
        max_tokens: int = 4096,
    ) -> str:
        """Chat with the planning model using the Responses API (required for codex models)."""
        response = self.client.responses.create(
            model=model,
            instructions=system_prompt,
            input=user_prompt,
        )
        return response.output_text

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    def get_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text.
        NOTE: Not supported yet — returning zero vector for hackathon MVP.
        """
        logger.warning("Embeddings not supported — returning zero vector")
        return [0.0] * 1536

    # ------------------------------------------------------------------
    # Plan Generation
    # ------------------------------------------------------------------

    def generate_plan(
        self,
        feedback_text: str,
        repo_owner: str,
        repo_name: str,
        repo_branch: str = "main",
        repo_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate implementation plan from user feedback."""
        try:

            context_section = (
                f"# Repository Context\n\n"
                f"Repository: {repo_owner}/{repo_name}\n"
                f"Branch: {repo_branch}"
            )

            if repo_context:
                context_section += (
                    f"\nPrimary Language: {repo_context.get('primary_language', 'unknown')}\n"
                    f"Test Framework: {repo_context.get('test_framework', 'unknown')}\n"
                    f"Build System: {repo_context.get('build_system', 'unknown')}\n\n"
                    f"## Repository Structure\n```\n"
                    f"{repo_context.get('structure_summary', 'Not available')}\n```"
                )

            system_msg = (
                "You are an expert software architect. Generate clear, actionable "
                "implementation plans based on actual repository structure. "
                "Never include code snippets — only describe what needs to be done."
            )

            user_msg = (
                f"User Feedback:\n\n{feedback_text}\n\n"
                f"{context_section}\n\n"
                "Generate a detailed implementation plan (PLAN.md) to address this "
                "feedback. The plan should include:\n\n"
                "1. **Summary**: Brief overview of the issue/feature request\n"
                "2. **Files to Modify**: List specific files that need changes\n"
                "3. **Implementation Steps**: Step-by-step instructions describing WHAT to do\n"
                "4. **Testing**: How to verify the changes work\n"
                "5. **Risks**: Any potential issues or dependencies\n\n"
                "**IMPORTANT:** Do NOT include any code snippets or code blocks. "
                "Only reference file paths and describe changes in plain English.\n"
                "Format the plan as clean markdown with NO code blocks."
            )

            return self._planning_chat(system_msg, user_msg)

        except Exception as e:
            logger.error(f"Error generating plan: {e}")
            raise

    # ------------------------------------------------------------------
    # Sentiment & Classification
    # ------------------------------------------------------------------

    def classify_sentiment(self, text: str) -> float:
        """Classify sentiment of text. Returns -1.0 to 1.0."""
        try:
            result = self._chat(
                "Classify the sentiment of the text as a number between -1.0 "
                "(very negative) and 1.0 (very positive). Respond with only the number.",
                text,
            )
            return float(result.strip())
        except Exception as e:
            logger.warning(f"Error classifying sentiment: {e}")
            return 0.0

    def determine_ticket_type(self, tweet_texts: List[str]) -> str:
        """Determine if tweets represent a bug, feature, enhancement, or question."""
        try:
            tweets_summary = "\n".join(tweet_texts)
            result = self._chat(
                "Classify user feedback as: bug, feature, enhancement, or question. "
                "Respond with only one word.",
                tweets_summary,
            )
            ticket_type = result.strip().lower()
            valid_types = ["bug", "feature", "enhancement", "question"]
            return ticket_type if ticket_type in valid_types else "feature"
        except Exception as e:
            logger.warning(f"Error determining ticket type: {e}")
            return "feature"

    def generate_ticket_title(self, tweet_texts: List[str]) -> str:
        """Generate a concise title for a ticket from tweet texts."""
        try:
            tweets_summary = "\n".join(tweet_texts)
            result = self._chat(
                "Generate a short, clear title (max 80 characters) summarizing "
                "this user feedback. Be specific and actionable.",
                tweets_summary,
            )
            return result.strip()
        except Exception as e:
            logger.warning(f"Error generating title: {e}")
            return tweet_texts[0] if tweet_texts else "User feedback"

    # ------------------------------------------------------------------
    # Tech Stack Detection
    # ------------------------------------------------------------------

    def detect_tech_stack(
        self, structure_summary: str, readme_content: str = ""
    ) -> Dict[str, Any]:
        """Detect repository tech stack from structure and README."""
        try:
            prompt = (
                f"Analyze this repository and determine its technical stack:\n\n"
                f"**Repository Structure:**\n```\n{structure_summary}\n```\n\n"
                f"**README (if available):**\n```\n"
                f"{readme_content if readme_content else 'No README found'}\n```\n\n"
                "Based on the structure and README, output a JSON object with:\n"
                '- "primary_language": main programming language\n'
                '- "test_framework": testing framework (or null)\n'
                '- "build_system": build/package manager (or null)\n\n'
                "Output valid JSON only."
            )

            result = self._chat_json(
                "You are a senior engineer analyzing repositories. "
                "Output valid JSON only, nothing else.",
                prompt,
            )

            data = json.loads(result.strip().strip("```json").strip("```"))
            logger.info(
                f"Detected: {data.get('primary_language')}, "
                f"{data.get('test_framework')}, {data.get('build_system')}"
            )
            return {
                "primary_language": data.get("primary_language", "unknown"),
                "test_framework": data.get("test_framework"),
                "build_system": data.get("build_system"),
            }

        except Exception as e:
            logger.error(f"Error detecting tech stack: {e}")
            raise

    # ------------------------------------------------------------------
    # Tweet Aggregation
    # ------------------------------------------------------------------

    def aggregate_tweets_into_project(self, tweet_texts: List[str]) -> dict:
        """
        Aggregate multiple tweets into a comprehensive project description.
        Called every time a new tweet arrives to re-generate the project fields.
        """
        try:
            tweets_summary = "\n".join(
                [f"{i + 1}. {t}" for i, t in enumerate(tweet_texts)]
            )

            prompt = (
                f"Analyze these user feedback tweets and generate a comprehensive "
                f"GitHub issue.\n\nAll User Feedback Tweets:\n{tweets_summary}\n\n"
                "Task: Generate a GitHub issue that captures the full scope of what "
                "users are requesting. Combine all tweets into a cohesive description.\n\n"
                "Output a JSON object with:\n"
                '- "title": concise actionable title (max 80 chars)\n'
                '- "description": comprehensive markdown description\n'
                '- "ticket_type": one of bug, feature, enhancement, question\n\n'
                "Output valid JSON only."
            )

            result = self._chat_json(
                "You are a product manager aggregating user feedback into clear, "
                "actionable GitHub issues. Output valid JSON only.",
                prompt,
            )

            data = json.loads(result.strip().strip("```json").strip("```"))

            valid_types = ["bug", "feature", "enhancement", "question"]
            ticket_type = data.get("ticket_type", "feature")
            if ticket_type not in valid_types:
                ticket_type = "feature"

            logger.info(f"Aggregated {len(tweet_texts)} tweets into project")

            return {
                "title": data.get("title", "User feedback"),
                "description": data.get("description", ""),
                "ticket_type": ticket_type,
            }

        except Exception as e:
            logger.error(f"Error aggregating tweets: {e}")
            return {
                "title": self.generate_ticket_title(tweet_texts),
                "description": "\n\n".join(
                    [f"**Tweet {i + 1}:** {t}" for i, t in enumerate(tweet_texts)]
                ),
                "ticket_type": self.determine_ticket_type(tweet_texts),
            }

    # ------------------------------------------------------------------
    # Issue Enrichment
    # ------------------------------------------------------------------

    def enrich_issue_with_context(
        self,
        title: str,
        description: str,
        repo_context: Dict[str, Any],
    ) -> Dict[str, str]:
        """Enrich issue title and description using code context."""
        try:
            prompt = (
                f"You are enriching a GitHub issue with specific codebase context.\n\n"
                f"**Original Issue Title:** {title}\n\n"
                f"**Original Issue Description:**\n{description}\n\n"
                f"**Repository Context:**\n"
                f"- Primary Language: {repo_context.get('primary_language', 'unknown')}\n"
                f"- Test Framework: {repo_context.get('test_framework', 'Not detected')}\n"
                f"- Build System: {repo_context.get('build_system', 'Not detected')}\n\n"
                f"**Repository Structure:**\n```\n"
                f"{repo_context.get('structure_summary', 'Not available')}\n```\n\n"
                "Enhance the issue with:\n"
                "1. Reference specific files/directories\n"
                "2. Suggest which parts of the codebase might need changes\n"
                "3. Add technical context based on the detected tech stack\n"
                "4. Keep the user's original intent intact\n"
                "5. Title must be clean, concise, no markdown, max 80 chars\n"
                "6. Description must be proper GitHub-flavored markdown\n\n"
                "Do NOT include any actual code snippets.\n\n"
                'Output a JSON object with "title" and "description" keys.'
            )

            result = self._chat_json(
                "You are a senior engineer enriching GitHub issues with codebase "
                "context. Output valid JSON only. No code snippets.",
                prompt,
            )

            data = json.loads(result.strip().strip("```json").strip("```"))
            logger.info("Issue enriched with code context")
            return {
                "title": data.get("title", title),
                "description": data.get("description", description),
            }

        except Exception as e:
            logger.warning(f"Failed to enrich issue with context: {e}")
            return {"title": title, "description": description}


# Global instance — used as `claude_client` for backward compat with imports
claude_client = OpenAIClient()
