"""Tests for the transcription engine.

Tests the interface and segment handling.
Actual model inference tests are marked @pytest.mark.slow (requires model download).
"""

import pytest
from ribbet.transcription.engine import TranscriptSegment, TranscriptionResult


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
