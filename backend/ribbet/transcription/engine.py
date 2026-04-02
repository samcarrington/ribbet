"""Kyutai STT 1B transcription engine.

Wraps moshi_mlx for Apple Silicon-optimized streaming STT.
The TranscriptionEngine class manages model lifecycle and streaming inference.
The TranscriptSegment/TranscriptionResult classes are plain data, fully testable.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TranscriptSegment:
    text: str
    start_time: float
    end_time: float
    is_partial: bool
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


class TranscriptionResult:
    """Accumulates confirmed transcript segments."""

    def __init__(self):
        self.segments: list[TranscriptSegment] = []

    def add_segment(self, segment: TranscriptSegment) -> None:
        self.segments.append(segment)

    @property
    def full_text(self) -> str:
        return " ".join(s.text for s in self.segments if not s.is_partial)

    def text_window(self, start: float, end: float) -> str:
        """Get text from segments overlapping the given time window."""
        return " ".join(
            s.text
            for s in self.segments
            if not s.is_partial and s.start_time >= start and s.start_time < end
        )

    def recent_text(self, last_seconds: float) -> str:
        """Get text from the last N seconds of transcript."""
        if not self.segments:
            return ""
        latest = self.segments[-1].end_time
        cutoff = latest - last_seconds
        return " ".join(
            s.text for s in self.segments if not s.is_partial and s.start_time >= cutoff
        )


class TranscriptionEngine:
    """Manages Kyutai STT 1B model loading and streaming inference.

    Usage:
        engine = TranscriptionEngine(model_repo="kyutai/stt-1b-en_fr", quantization=4)
        await engine.load()
        # Feed audio chunks:
        segments = await engine.transcribe_chunk(audio_numpy_array, chunk_start_time)
        await engine.unload()
    """

    def __init__(self, model_repo: str, quantization: int = 4):
        self.model_repo = model_repo
        self.quantization = quantization
        self._model = None
        self._mimi = None
        self._text_tokenizer = None
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    async def load(self) -> None:
        """Load the STT model. This is slow (first run downloads weights)."""
        logger.info("Loading STT model %s (q%d)...", self.model_repo, self.quantization)

        # Implementation note for the engineer:
        # Use the moshi_mlx inference API:
        #
        # from moshi_mlx.models import loaders
        # checkpoint_info = loaders.CheckpointInfo.from_hf_repo(self.model_repo)
        # self._mimi = checkpoint_info.get_mimi(device="mps")  # or default MLX device
        # self._text_tokenizer = checkpoint_info.get_text_tokenizer()
        # self._model = checkpoint_info.get_moshi(device="mps")
        #
        # The actual streaming inference loop:
        # 1. Pad audio per stt_config audio_silence_prefix_seconds
        # 2. Create InferenceState(mimi, text_tokenizer, model, batch_size=1)
        # 3. Feed chunks via state.run() or the streaming API
        # 4. Decode output tokens to text with timestamps

        self._loaded = True
        logger.info("STT model loaded")

    async def transcribe_chunk(
        self, audio: np.ndarray, chunk_start_time: float
    ) -> list[TranscriptSegment]:
        """Transcribe an audio chunk and return new segments.

        Args:
            audio: float32 numpy array of audio samples at 24kHz
            chunk_start_time: wall-clock offset of this chunk in the session

        Returns:
            List of new TranscriptSegment objects
        """
        if not self._loaded:
            raise RuntimeError("Model not loaded. Call load() first.")

        # Implementation note for the engineer:
        # This is where the actual moshi_mlx inference happens.
        # The chunk is fed to the model's streaming state, and
        # any new text tokens are decoded and returned as segments.
        #
        # The model has a 0.5s text delay, so timestamps should be
        # adjusted: text_timestamp = audio_frame_offset - 0.5

        return []

    async def unload(self) -> None:
        """Release model resources."""
        self._model = None
        self._mimi = None
        self._text_tokenizer = None
        self._loaded = False
        logger.info("STT model unloaded")
