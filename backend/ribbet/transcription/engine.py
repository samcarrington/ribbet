"""Kyutai STT 1B transcription engine.

Wraps moshi_mlx for Apple Silicon-optimized streaming STT.
The TranscriptionEngine class manages model lifecycle and streaming inference.
The TranscriptSegment/TranscriptionResult classes are plain data, fully testable.

Runtime prerequisites (``pip install "ribbet[ml]"``):
  - moshi_mlx >= 0.3.0  (brings mlx, rustymimi, sentencepiece, huggingface-hub)
  - mlx >= 0.22 (Apple Silicon only — will not install on x86)
  - First load downloads ~2 GB of weights from HuggingFace Hub.

If moshi_mlx is absent the engine still loads but ``load()`` and
``transcribe_chunk()`` raise ``RuntimeError`` with an actionable message.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal sentinel for the "stub not wired" state (kept for test compat)
# ---------------------------------------------------------------------------


class _StubNotImplemented(NotImplementedError):
    """Raised by transcribe_chunk stub to signal real inference is not yet wired."""


# ---------------------------------------------------------------------------
# Public data classes
# ---------------------------------------------------------------------------


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
        """Get text from the last N seconds of confirmed (non-partial) transcript.

        Uses the latest *confirmed* segment end_time as the reference point so
        that a trailing partial segment does not shift the cutoff forward and
        incorrectly exclude recently confirmed text.
        """
        if not self.segments:
            return ""
        confirmed = [s for s in self.segments if not s.is_partial]
        if not confirmed:
            return ""
        latest = confirmed[-1].end_time
        cutoff = latest - last_seconds
        return " ".join(s.text for s in confirmed if s.start_time >= cutoff)


# ---------------------------------------------------------------------------
# Streaming inference state (wraps moshi_mlx internals)
# ---------------------------------------------------------------------------


class _MoshiInferenceState:
    """Holds per-session moshi_mlx streaming state.

    One instance is created per ``TranscriptionEngine.load()`` call and reused
    across all ``transcribe_chunk()`` calls in that session, so the causal
    attention KV-cache accumulates correctly across chunk boundaries.

    Step size: moshi_mlx processes audio in 1920-sample frames at 24 kHz
    (= 80 ms per step).  Any leftover samples smaller than one frame are
    buffered and prepended to the next chunk.
    """

    FRAME_SAMPLES = 1920  # 80 ms at 24 kHz — hard-coded in moshi_mlx

    def __init__(
        self,
        model,
        audio_tokenizer,
        text_tokenizer,
        lm_config,
        stt_config: dict,
        sample_rate: int = 24000,
    ):
        import mlx.core as mx
        from moshi_mlx import models, utils

        self._model = model
        self._audio_tokenizer = audio_tokenizer
        self._text_tokenizer = text_tokenizer
        self._lm_config = lm_config
        self._stt_config = stt_config
        self._sample_rate = sample_rate

        # We set a generous max_steps; LmGen rejects calls beyond this.
        # 3 hours @ 80 ms/step = 135 000 steps — more than enough.
        _max_steps = 135_000

        self._gen = models.LmGen(
            model=self._model,
            max_steps=_max_steps,
            text_sampler=utils.Sampler(top_k=25, temp=0.0),  # greedy for STT
            audio_sampler=utils.Sampler(top_k=250, temp=0.8),
            check=False,
        )

        # Accumulated step counter and wall-clock tracking
        self._step_idx: int = 0
        self._leftover: np.ndarray = np.array([], dtype=np.float32)

        # The model has an audio_delay_seconds offset — text tokens are emitted
        # that many seconds *after* the corresponding audio was fed in.
        self._text_delay: float = stt_config.get("audio_delay_seconds", 0.5)
        # Frame duration in seconds
        self._frame_duration: float = self.FRAME_SAMPLES / sample_rate  # 0.08 s

    def feed(self, audio: np.ndarray, chunk_start_time: float) -> list[TranscriptSegment]:
        """Feed a chunk of mono float32 audio and return any new text segments.

        Internally processes complete 1920-sample frames; incomplete trailing
        samples are buffered for the next call.
        """
        import mlx.core as mx

        segments: list[TranscriptSegment] = []

        # Prepend any buffered leftover from the previous call
        audio = np.concatenate([self._leftover, audio])
        self._leftover = np.array([], dtype=np.float32)

        n_frames = len(audio) // self.FRAME_SAMPLES
        if n_frames == 0:
            # Not enough samples for even one frame — buffer everything
            self._leftover = audio
            return segments

        # Save the tail
        self._leftover = audio[n_frames * self.FRAME_SAMPLES :]
        audio = audio[: n_frames * self.FRAME_SAMPLES]

        # Reshape to (1, n_samples) as expected by rustymimi
        pcm_2d = audio[np.newaxis, :]  # shape (1, n_samples)

        other_codebooks = self._lm_config.other_codebooks

        for frame_idx in range(n_frames):
            frame = pcm_2d[:, frame_idx * self.FRAME_SAMPLES : (frame_idx + 1) * self.FRAME_SAMPLES]

            # Encode one frame with rustymimi (returns int32 codes)
            other_audio_tokens = self._audio_tokenizer.encode_step(frame)
            other_audio_tokens = mx.array(other_audio_tokens).transpose(0, 2, 1)[
                :, :, :other_codebooks
            ]

            text_token = self._gen.step(other_audio_tokens[0])
            text_token_id = text_token[0].item()

            # 0 = padding/silence, 3 = EOS — skip both
            if text_token_id not in (0, 3):
                piece = self._text_tokenizer.id_to_piece(text_token_id)
                text = piece.replace("\u2581", " ").strip()  # ▁ is SentencePiece word boundary
                if text:
                    # Timestamps: audio was fed at step_idx * frame_duration seconds
                    # relative to the chunk_start_time; subtract the model text delay.
                    audio_ts = chunk_start_time + frame_idx * self._frame_duration
                    seg_start = max(0.0, audio_ts - self._text_delay)
                    seg_end = seg_start + self._frame_duration
                    segments.append(
                        TranscriptSegment(
                            text=text,
                            start_time=seg_start,
                            end_time=seg_end,
                            is_partial=False,
                        )
                    )

            self._step_idx += 1

        return segments


# ---------------------------------------------------------------------------
# TranscriptionEngine
# ---------------------------------------------------------------------------


class TranscriptionEngine:
    """Manages Kyutai STT 1B model loading and streaming inference.

    Usage::

        engine = TranscriptionEngine(model_repo="kyutai/stt-1b-en_fr", quantization=4)
        await engine.load()
        # Feed audio chunks:
        segments = await engine.transcribe_chunk(audio_numpy_array, chunk_start_time)
        await engine.unload()

    If ``moshi_mlx`` is not installed, ``load()`` raises ``RuntimeError`` with
    installation instructions rather than crashing at import time.
    """

    def __init__(self, model_repo: str, quantization: int = 4):
        self.model_repo = model_repo
        self.quantization = quantization
        self._model = None
        self._mimi = None  # rustymimi.Tokenizer
        self._text_tokenizer = None  # sentencepiece.SentencePieceProcessor
        self._lm_config = None
        self._stt_config: dict = {}
        self._inference_state: _MoshiInferenceState | None = None
        self._loaded = False
        self._lock = asyncio.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    # ------------------------------------------------------------------
    # Model lifecycle
    # ------------------------------------------------------------------

    async def load(self) -> None:
        """Load the STT model. Idempotent — safe to call multiple times.

        First call downloads ~2 GB of weights on first run (subsequent runs
        use the HuggingFace Hub cache at ``~/.cache/huggingface/hub``).

        Raises:
            RuntimeError: if moshi_mlx / mlx are not installed.
        """
        async with self._lock:
            if self._loaded:
                logger.debug("STT model already loaded; skipping.")
                return

            logger.info(
                "Loading STT model %s (quantization=%d)...",
                self.model_repo,
                self.quantization,
            )

            # Validate dependencies first — clear error if missing
            self._assert_deps()

            # Delegate to a thread pool so we don't block the event loop during
            # the (potentially slow) weight loading and compilation steps.
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._load_sync)

            self._loaded = True
            logger.info("STT model loaded successfully")

    def _assert_deps(self) -> None:
        """Raise RuntimeError with actionable message if ML deps are missing."""
        missing: list[str] = []
        for mod in ("mlx.core", "moshi_mlx", "rustymimi", "sentencepiece"):
            try:
                __import__(mod)
            except ImportError:
                missing.append(mod)
        if missing:
            raise RuntimeError(
                f"Missing ML dependencies: {', '.join(missing)}. "
                "Install with: pip install 'ribbet[ml]'  "
                "(requires Apple Silicon Mac with macOS 13+)."
            )

    def _load_sync(self) -> None:
        """Synchronous weight-loading logic — runs in a thread pool executor."""
        import json

        import mlx.core as mx
        import mlx.nn as nn
        import rustymimi
        import sentencepiece
        from huggingface_hub import hf_hub_download
        from moshi_mlx import models

        # ----------------------------------------------------------------
        # Download / locate model files via HuggingFace Hub
        # ----------------------------------------------------------------
        logger.debug("Fetching config.json from %s", self.model_repo)
        config_path = hf_hub_download(self.model_repo, "config.json")
        with open(config_path) as fh:
            raw_config = json.load(fh)

        self._stt_config = raw_config.get("stt_config", {})
        logger.debug("stt_config: %s", self.stt_config)

        # Resolve filenames declared in config
        mimi_name = raw_config.get("mimi_name", "tokenizer-e351c8d8-checkpoint125.safetensors")
        moshi_name = raw_config.get("moshi_name", "model.safetensors")
        tokenizer_name = raw_config.get("tokenizer_name", "tokenizer_spm_32k_3.model")

        logger.debug("Downloading mimi weights: %s", mimi_name)
        mimi_path = hf_hub_download(self.model_repo, mimi_name)

        logger.debug("Downloading model weights: %s", moshi_name)
        moshi_path = hf_hub_download(self.model_repo, moshi_name)

        logger.debug("Downloading text tokenizer: %s", tokenizer_name)
        tokenizer_path = hf_hub_download(self.model_repo, tokenizer_name)

        # ----------------------------------------------------------------
        # Build LmConfig and instantiate model
        # ----------------------------------------------------------------
        lm_config = models.LmConfig.from_config_dict(raw_config)
        model = models.Lm(lm_config)
        model.set_dtype(mx.bfloat16)

        # Apply quantization only when the weights file is NOT already quantized.
        # Pre-quantized safetensors (*.q4.safetensors / *.q8.safetensors) already
        # have quantized weights baked in; calling nn.quantize() on top would
        # double-quantize them and corrupt the model.
        weights_already_quantized = moshi_path.endswith(".q4.safetensors") or moshi_path.endswith(
            ".q8.safetensors"
        )
        if not weights_already_quantized:
            if self.quantization == 4:
                nn.quantize(model, bits=4, group_size=32)
            elif self.quantization == 8:
                nn.quantize(model, bits=8, group_size=64)

        logger.debug("Loading model weights from %s", moshi_path)
        model.load_weights(moshi_path, strict=True)

        # ----------------------------------------------------------------
        # Audio tokenizer (rustymimi)
        # ----------------------------------------------------------------
        mimi_codebooks = max(lm_config.generated_codebooks, lm_config.other_codebooks)
        audio_tokenizer = rustymimi.Tokenizer(mimi_path, num_codebooks=mimi_codebooks)

        # ----------------------------------------------------------------
        # Text tokenizer (SentencePiece)
        # ----------------------------------------------------------------
        text_tokenizer = sentencepiece.SentencePieceProcessor(tokenizer_path)

        # ----------------------------------------------------------------
        # Warm up — forces MLX to compile the compute graph once so the first
        # real chunk doesn't incur JIT compilation latency.
        # ----------------------------------------------------------------
        logger.debug("Warming up model...")
        model.warmup()
        logger.debug("Warm-up complete")

        # ----------------------------------------------------------------
        # Store references; create fresh inference state
        # ----------------------------------------------------------------
        self._model = model
        self._mimi = audio_tokenizer
        self._text_tokenizer = text_tokenizer
        self._lm_config = lm_config
        self._inference_state = _MoshiInferenceState(
            model=model,
            audio_tokenizer=audio_tokenizer,
            text_tokenizer=text_tokenizer,
            lm_config=lm_config,
            stt_config=self._stt_config,
        )

    @property
    def stt_config(self) -> dict:
        return self._stt_config

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    async def transcribe_chunk(
        self, audio: np.ndarray, chunk_start_time: float
    ) -> list[TranscriptSegment]:
        """Transcribe an audio chunk and return new segments.

        Args:
            audio: float32 numpy array of mono audio samples at 24 kHz.
            chunk_start_time: wall-clock offset of this chunk's start within
                the session (seconds since session start).

        Returns:
            List of new ``TranscriptSegment`` objects decoded during this chunk.
            May be empty if no new text tokens were emitted.

        Raises:
            RuntimeError: if ``load()`` has not been called.
            RuntimeError: if moshi_mlx dependencies are missing.
        """
        if not self._loaded:
            raise RuntimeError("Model not loaded. Call load() first.")

        if self._inference_state is None:
            # Should never happen after a successful load(), but guard anyway.
            raise RuntimeError("Inference state is None despite model being loaded.")

        # Run synchronous inference in a thread pool to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        segments = await loop.run_in_executor(
            None,
            self._inference_state.feed,
            audio.astype(np.float32),
            float(chunk_start_time),
        )
        return segments

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    async def unload(self) -> None:
        """Release model resources and reset internal state."""
        async with self._lock:
            self._inference_state = None
            self._model = None
            self._mimi = None
            self._text_tokenizer = None
            self._lm_config = None
            self._stt_config = {}
            self._loaded = False
            logger.info("STT model unloaded")
