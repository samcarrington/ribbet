"""Tests for the transcription engine.

Tests cover:
  - Data classes (TranscriptSegment, TranscriptionResult) — always run
  - Engine lifecycle (load/unload) — always run (moshi_mlx not required for these)
  - Real inference path — skipped when moshi_mlx/mlx are unavailable (CI-safe)
"""

from __future__ import annotations

import sys

import pytest
import numpy as np
from ribbet.transcription.engine import (
    TranscriptSegment,
    TranscriptionResult,
    TranscriptionEngine,
    _StubNotImplemented,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOSHI_AVAILABLE = False
try:
    import mlx.core  # noqa: F401
    import moshi_mlx  # noqa: F401
    import rustymimi  # noqa: F401
    import sentencepiece  # noqa: F401

    _MOSHI_AVAILABLE = True
except ImportError:
    pass

requires_moshi = pytest.mark.skipif(
    not _MOSHI_AVAILABLE,
    reason="moshi_mlx/mlx not installed — skipping inference tests",
)


# ---------------------------------------------------------------------------
# TranscriptSegment
# ---------------------------------------------------------------------------


def test_transcript_segment_creation():
    seg = TranscriptSegment(
        text="Hello, how are you?",
        start_time=1.0,
        end_time=3.5,
        is_partial=False,
    )
    assert seg.text == "Hello, how are you?"
    assert seg.end_time - seg.start_time == pytest.approx(2.5)


def test_transcript_segment_partial():
    seg = TranscriptSegment(
        text="Hello",
        start_time=1.0,
        end_time=1.5,
        is_partial=True,
    )
    assert seg.is_partial is True


def test_transcript_segment_has_unique_id():
    s1 = TranscriptSegment("a", 0.0, 1.0, False)
    s2 = TranscriptSegment("b", 1.0, 2.0, False)
    assert s1.id != s2.id


# ---------------------------------------------------------------------------
# TranscriptionResult
# ---------------------------------------------------------------------------


def test_transcription_result_accumulation():
    result = TranscriptionResult()
    result.add_segment(TranscriptSegment("Hello", 0.0, 1.0, False))
    result.add_segment(TranscriptSegment("world", 1.0, 2.0, False))
    assert result.full_text == "Hello world"
    assert len(result.segments) == 2


def test_transcription_result_window():
    result = TranscriptionResult()
    for i in range(10):
        result.add_segment(TranscriptSegment(f"word{i}", float(i), float(i + 1), False))
    window = result.text_window(start=5.0, end=8.0)
    assert "word5" in window
    assert "word7" in window
    assert "word9" not in window


def test_recent_text_ignores_trailing_partial():
    """recent_text cutoff must be anchored on the latest confirmed segment.

    If the last segment is partial, using its end_time as the anchor would push
    the cutoff forward and incorrectly exclude recently confirmed text.
    """
    result = TranscriptionResult()
    # Confirmed segments spanning 0–10 s
    for i in range(10):
        result.add_segment(TranscriptSegment(f"word{i}", float(i), float(i + 1), False))
    # Trailing partial segment 10–12 s — must NOT shift the cutoff
    result.add_segment(TranscriptSegment("partial", 10.0, 12.0, is_partial=True))

    # With a 3-second window, cutoff should be anchored at confirmed end=10 → cutoff=7.
    # That means word7, word8, word9 should all be included.
    recent = result.recent_text(3.0)
    assert "word7" in recent
    assert "word8" in recent
    assert "word9" in recent
    # The partial segment text must not appear
    assert "partial" not in recent


def test_recent_text_empty_when_only_partial():
    result = TranscriptionResult()
    result.add_segment(TranscriptSegment("partial", 0.0, 1.0, is_partial=True))
    assert result.recent_text(5.0) == ""


def test_recent_text_empty_on_empty_result():
    result = TranscriptionResult()
    assert result.recent_text(5.0) == ""


# ---------------------------------------------------------------------------
# TranscriptionEngine lifecycle (no ML deps needed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transcribe_chunk_before_load_raises_runtime_error():
    """Calling transcribe_chunk before load() must raise RuntimeError."""
    engine = TranscriptionEngine(model_repo="test/model")
    audio = np.zeros(24000, dtype=np.float32)
    with pytest.raises(RuntimeError, match="load\\(\\)"):
        await engine.transcribe_chunk(audio, chunk_start_time=0.0)


@pytest.mark.asyncio
async def test_load_raises_runtime_error_when_deps_missing(monkeypatch):
    """load() must raise RuntimeError with actionable message when ML deps absent."""
    if _MOSHI_AVAILABLE:
        pytest.skip("moshi_mlx is available — skipping dep-missing test")

    engine = TranscriptionEngine(model_repo="test/model")
    with pytest.raises(RuntimeError, match="pip install"):
        await engine.load()

    # is_loaded must remain False after a failed load
    assert engine.is_loaded is False


@pytest.mark.asyncio
async def test_is_loaded_false_before_load():
    engine = TranscriptionEngine(model_repo="test/model")
    assert engine.is_loaded is False


@pytest.mark.asyncio
async def test_unload_when_not_loaded_is_safe():
    """unload() on a fresh engine must not raise."""
    engine = TranscriptionEngine(model_repo="test/model")
    await engine.unload()
    assert engine.is_loaded is False


@pytest.mark.asyncio
async def test_double_load_is_idempotent(monkeypatch):
    """Calling load() twice must be a no-op on the second call."""
    if not _MOSHI_AVAILABLE:
        pytest.skip("moshi_mlx unavailable")

    engine = TranscriptionEngine(model_repo="kyutai/stt-1b-en_fr")
    # Mock _load_sync to avoid actually loading weights in test
    call_count = {"n": 0}

    def fake_load_sync():
        call_count["n"] += 1
        engine._loaded = True  # simulate what real _load_sync does at the end

    monkeypatch.setattr(engine, "_load_sync", fake_load_sync)
    # Also patch _assert_deps to always pass
    monkeypatch.setattr(engine, "_assert_deps", lambda: None)

    await engine.load()
    await engine.load()  # second call must be a no-op
    assert call_count["n"] == 1
    assert engine.is_loaded is True


@pytest.mark.asyncio
async def test_load_sets_is_loaded(monkeypatch):
    """load() must set is_loaded=True."""
    engine = TranscriptionEngine(model_repo="test/model")
    monkeypatch.setattr(engine, "_assert_deps", lambda: None)
    monkeypatch.setattr(engine, "_load_sync", lambda: None)
    # Manually replicate what load() does after _load_sync
    # We test the engine.is_loaded flag by patching internal state
    engine._inference_state = object()  # dummy non-None
    engine._loaded = False

    await engine.load()
    # After load() with patched _load_sync (which doesn't set _loaded), the
    # engine wrapper code sets _loaded = True
    assert engine.is_loaded is True


@pytest.mark.asyncio
async def test_unload_clears_is_loaded(monkeypatch):
    engine = TranscriptionEngine(model_repo="test/model")
    monkeypatch.setattr(engine, "_assert_deps", lambda: None)
    monkeypatch.setattr(engine, "_load_sync", lambda: None)
    await engine.load()
    assert engine.is_loaded is True
    await engine.unload()
    assert engine.is_loaded is False


@pytest.mark.asyncio
async def test_load_unload_toggle(monkeypatch):
    """load → unload → load cycle should leave engine in loaded state."""
    engine = TranscriptionEngine(model_repo="test/model")
    monkeypatch.setattr(engine, "_assert_deps", lambda: None)
    monkeypatch.setattr(engine, "_load_sync", lambda: None)
    await engine.load()
    await engine.unload()
    await engine.load()
    assert engine.is_loaded is True


@pytest.mark.asyncio
async def test_transcribe_chunk_after_load_returns_list(monkeypatch):
    """transcribe_chunk must return a list (possibly empty) when loaded + deps available."""
    if not _MOSHI_AVAILABLE:
        pytest.skip("moshi_mlx unavailable")

    engine = TranscriptionEngine(model_repo="kyutai/stt-1b-en_fr")
    monkeypatch.setattr(engine, "_assert_deps", lambda: None)

    # Provide a fake inference state that always returns empty list
    class _FakeState:
        def feed(self, audio, chunk_start_time):
            return []

    monkeypatch.setattr(engine, "_load_sync", lambda: None)
    await engine.load()
    engine._inference_state = _FakeState()

    audio = np.zeros(24000, dtype=np.float32)
    result = await engine.transcribe_chunk(audio, chunk_start_time=0.0)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_transcribe_chunk_when_deps_missing_raises_runtime_error():
    """When deps missing, transcribe_chunk after a patched load must raise RuntimeError."""
    if _MOSHI_AVAILABLE:
        pytest.skip("moshi_mlx is available — irrelevant")

    engine = TranscriptionEngine(model_repo="test/model")
    # Force the engine into a "loaded" state without actually loading
    engine._loaded = True
    engine._inference_state = None  # deps weren't loaded so state is None

    audio = np.zeros(24000, dtype=np.float32)
    with pytest.raises(RuntimeError):
        await engine.transcribe_chunk(audio, chunk_start_time=0.0)


# ---------------------------------------------------------------------------
# Real inference test (requires moshi_mlx + downloaded weights, very slow)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.slow
@requires_moshi
async def test_real_inference_produces_segments():
    """End-to-end inference test — requires model weights.

    Run with: pytest -m slow
    This will download ~2 GB of weights on first run.
    """
    engine = TranscriptionEngine(model_repo="kyutai/stt-1b-en_fr", quantization=4)
    await engine.load()
    assert engine.is_loaded

    # Feed 1 second of silence — expect empty or near-empty output
    silence = np.zeros(24000, dtype=np.float32)
    segments = await engine.transcribe_chunk(silence, chunk_start_time=0.0)
    assert isinstance(segments, list)
    # All returned segments must be TranscriptSegment instances
    for seg in segments:
        assert isinstance(seg, TranscriptSegment)
        assert isinstance(seg.text, str)
        assert seg.start_time >= 0.0
        assert seg.end_time >= seg.start_time

    await engine.unload()
    assert not engine.is_loaded
