"""Tests for the transcription engine.

Tests the interface and segment handling.
Actual model inference tests are marked @pytest.mark.slow (requires model download).
"""

import pytest
import numpy as np
from ribbet.transcription.engine import (
    TranscriptSegment,
    TranscriptionResult,
    TranscriptionEngine,
    _StubNotImplemented,
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
# TranscriptionEngine lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transcribe_chunk_before_load_raises_runtime_error():
    """Calling transcribe_chunk before load() must raise RuntimeError."""
    engine = TranscriptionEngine(model_repo="test/model")
    audio = np.zeros(24000, dtype=np.float32)
    with pytest.raises(RuntimeError, match="load\\(\\)"):
        await engine.transcribe_chunk(audio, chunk_start_time=0.0)


@pytest.mark.asyncio
async def test_load_sets_is_loaded():
    engine = TranscriptionEngine(model_repo="test/model")
    assert engine.is_loaded is False
    await engine.load()
    assert engine.is_loaded is True


@pytest.mark.asyncio
async def test_unload_clears_is_loaded():
    engine = TranscriptionEngine(model_repo="test/model")
    await engine.load()
    assert engine.is_loaded is True
    await engine.unload()
    assert engine.is_loaded is False


@pytest.mark.asyncio
async def test_load_unload_toggle():
    """load → unload → load cycle should leave engine in loaded state."""
    engine = TranscriptionEngine(model_repo="test/model")
    await engine.load()
    await engine.unload()
    await engine.load()
    assert engine.is_loaded is True


@pytest.mark.asyncio
async def test_transcribe_chunk_after_load_raises_not_implemented():
    """After load(), transcribe_chunk must raise NotImplementedError (stub signal)."""
    engine = TranscriptionEngine(model_repo="test/model")
    await engine.load()
    audio = np.zeros(24000, dtype=np.float32)
    with pytest.raises(NotImplementedError):
        await engine.transcribe_chunk(audio, chunk_start_time=0.0)


@pytest.mark.asyncio
async def test_double_load_is_idempotent():
    """Calling load() twice must not raise and must leave engine loaded."""
    engine = TranscriptionEngine(model_repo="test/model")
    await engine.load()
    await engine.load()  # second call should be a no-op
    assert engine.is_loaded is True
