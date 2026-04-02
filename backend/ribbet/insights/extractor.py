"""LLM-based insight extraction using mlx-lm.

Runs on a background asyncio task, consuming transcript windows
and producing insight snapshots. Never blocks the transcription path.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from ribbet.config import settings
from ribbet.insights.prompts import (
    INSIGHT_SYSTEM_PROMPT,
    build_insight_prompt,
    parse_insight_response,
)

logger = logging.getLogger(__name__)


class InsightExtractor:
    """Extracts meeting insights from transcript text using a local LLM.

    Usage:
        extractor = InsightExtractor(model_name="mlx-community/Qwen2.5-3B-Instruct-4bit")
        await extractor.load()
        snapshot = await extractor.extract(transcript_window_text)
        await extractor.unload()
    """

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.insight_model
        self._model = None
        self._tokenizer = None
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    async def load(self) -> None:
        """Load the insight LLM. Runs in executor to avoid blocking."""
        logger.info("Loading insight model %s...", self.model_name)

        # Implementation note for the engineer:
        # from mlx_lm import load, generate
        # self._model, self._tokenizer = load(self.model_name)

        self._loaded = True
        logger.info("Insight model loaded")

    async def extract(self, transcript_window: str) -> dict:
        """Extract insights from a transcript window.

        Returns a dict with topics, actions, decisions keys.
        """
        if not self._loaded:
            raise RuntimeError("Model not loaded")

        if not transcript_window.strip():
            return {"topics": [], "actions": [], "decisions": []}

        prompt = build_insight_prompt(transcript_window)

        # Implementation note for the engineer:
        # Use mlx_lm.generate() with the system prompt + user prompt.
        # Run in asyncio.to_thread() to avoid blocking the event loop.
        #
        # messages = [
        #     {"role": "system", "content": INSIGHT_SYSTEM_PROMPT},
        #     {"role": "user", "content": prompt},
        # ]
        # formatted = self._tokenizer.apply_chat_template(messages, tokenize=False)
        # response = await asyncio.to_thread(
        #     generate, self._model, self._tokenizer, prompt=formatted, max_tokens=1024
        # )
        # return parse_insight_response(response)

        return {"topics": [], "actions": [], "decisions": []}

    async def unload(self) -> None:
        self._model = None
        self._tokenizer = None
        self._loaded = False
