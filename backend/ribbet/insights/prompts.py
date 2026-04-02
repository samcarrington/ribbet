"""Prompt templates and response parsing for insight extraction."""

from __future__ import annotations

import json
import re


INSIGHT_SYSTEM_PROMPT = """You are a meeting analyst. Given a transcript excerpt, extract:

1. **Topics**: Main discussion topics with prominence (0.0-1.0) and keywords.
2. **Action Items**: Tasks that someone needs to do.
3. **Decisions**: Conclusions or agreements reached.

Respond ONLY with valid JSON in this exact format:
{
  "topics": [{"label": "Topic Name", "prominence": 0.8, "keywords": ["kw1", "kw2"]}],
  "actions": [{"text": "Description of action item", "timestamp_hint": "recent"}],
  "decisions": [{"text": "Description of decision", "timestamp_hint": "recent"}]
}

Rules:
- Be concise. Each item should be one sentence.
- Only include items clearly stated or implied in the transcript.
- If nothing is found for a category, use an empty array.
- Do NOT invent or hallucinate content.
"""


def build_insight_prompt(transcript_window: str) -> str:
    """Build the user prompt for insight extraction."""
    return f"""Analyze this meeting transcript excerpt and extract topics, action items, and decisions.

TRANSCRIPT:
{transcript_window}

Respond with JSON only."""


def parse_insight_response(raw: str) -> dict:
    """Parse the LLM response into structured insight data.

    Handles raw JSON, JSON wrapped in markdown code blocks, and malformed responses.
    """
    empty: dict = {"topics": [], "actions": [], "decisions": []}

    # Try to extract JSON from markdown code blocks
    code_block_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    json_str = code_block_match.group(1).strip() if code_block_match else raw.strip()

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        return empty

    # Validate structure
    result = {
        "topics": parsed.get("topics", []),
        "actions": parsed.get("actions", []),
        "decisions": parsed.get("decisions", []),
    }

    # Validate each topic has required fields
    result["topics"] = [t for t in result["topics"] if isinstance(t, dict) and "label" in t]
    for t in result["topics"]:
        t.setdefault("prominence", 0.5)
        t.setdefault("keywords", [])

    return result
