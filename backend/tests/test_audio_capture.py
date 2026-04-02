"""Tests for audio capture module.

NOTE: Tests that actually capture system audio are marked @pytest.mark.macos
and require Screen Recording permission. Run with: pytest -m macos
"""

import pytest
import asyncio
import numpy as np
from unittest.mock import AsyncMock

from ribbet.audio.capture import AudioBuffer, AudioCaptureConfig


def test_audio_buffer_append_and_read():
    buf = AudioBuffer(sample_rate=24000, max_seconds=10)
    chunk = np.zeros(4800, dtype=np.float32)  # 0.2s at 24kHz
    buf.append(chunk)
    assert buf.duration_seconds == pytest.approx(0.2, abs=0.01)


def test_audio_buffer_read_last_n_seconds():
    buf = AudioBuffer(sample_rate=24000, max_seconds=10)
    # Add 1 second of audio
    for _ in range(5):
        buf.append(np.ones(4800, dtype=np.float32))
    chunk = buf.read_last(0.5)
    assert len(chunk) == 12000  # 0.5s * 24000
    assert chunk.dtype == np.float32


def test_audio_buffer_evicts_old_data():
    buf = AudioBuffer(sample_rate=24000, max_seconds=2)
    # Add 3 seconds of audio
    for _ in range(15):
        buf.append(np.ones(4800, dtype=np.float32))
    assert buf.duration_seconds <= 2.1  # allows small float margin


def test_audio_capture_config_defaults():
    config = AudioCaptureConfig()
    assert config.sample_rate == 24000
    assert config.channels == 1


def test_audio_buffer_read_from_empty():
    buf = AudioBuffer(sample_rate=24000, max_seconds=10)
    chunk = buf.read_last(1.0)
    assert len(chunk) == 0
