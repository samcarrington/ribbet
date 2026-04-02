"""Tests for the insight extraction module."""

import pytest
import json
from ribbet.insights.prompts import build_insight_prompt, parse_insight_response
from ribbet.insights.extractor import InsightExtractor


def test_build_insight_prompt_includes_transcript():
    prompt = build_insight_prompt("We need to finish the budget report by Friday.")
    assert "budget report" in prompt
    assert "topics" in prompt.lower() or "topic" in prompt.lower()


def test_parse_insight_response_valid_json():
    raw = json.dumps(
        {
            "topics": [{"label": "Budget", "prominence": 0.9, "keywords": ["budget", "report"]}],
            "actions": [{"text": "Finish budget report by Friday", "timestamp_hint": "recent"}],
            "decisions": [],
        }
    )
    result = parse_insight_response(raw)
    assert len(result["topics"]) == 1
    assert result["topics"][0]["label"] == "Budget"
    assert len(result["actions"]) == 1


def test_parse_insight_response_malformed_returns_empty():
    result = parse_insight_response("this is not json at all")
    assert result["topics"] == []
    assert result["actions"] == []
    assert result["decisions"] == []


def test_parse_insight_response_extracts_json_from_markdown():
    raw = """Here are the insights:
```json
{
    "topics": [{"label": "Q3 Plan", "prominence": 0.7, "keywords": ["Q3", "plan"]}],
    "actions": [],
    "decisions": [{"text": "Approved Q3 plan", "timestamp_hint": "recent"}]
}
```
"""
    result = parse_insight_response(raw)
    assert len(result["topics"]) == 1
    assert len(result["decisions"]) == 1
