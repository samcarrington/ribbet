"""Tests for audio capture module.

NOTE: Tests that actually capture system audio are marked @pytest.mark.macos
and require Screen Recording permission. Run with: pytest -m macos
"""

import threading

import pytest
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


# --- Truncation behaviour -------------------------------------------------


def test_audio_buffer_read_last_truncates_when_less_data_available():
    """read_last returns all available samples when fewer than requested."""
    buf = AudioBuffer(sample_rate=24000, max_seconds=10)
    buf.append(np.ones(4800, dtype=np.float32))  # 0.2 s
    result = buf.read_last(5.0)  # ask for 5 s
    assert len(result) == 4800  # only 0.2 s available


def test_audio_buffer_read_last_returns_copy():
    """Mutating the returned array must not affect the internal buffer."""
    buf = AudioBuffer(sample_rate=24000, max_seconds=10)
    buf.append(np.ones(4800, dtype=np.float32))
    result = buf.read_last(1.0)
    result[:] = 0.0  # mutate the copy
    # Internal buffer must still contain ones
    assert buf.read_last(1.0).sum() == pytest.approx(4800.0)


# --- Thread-safety --------------------------------------------------------


def test_audio_buffer_thread_safe_concurrent_appends():
    """Concurrent appends from many threads must not corrupt the buffer."""
    buf = AudioBuffer(sample_rate=24000, max_seconds=30)
    chunk = np.ones(240, dtype=np.float32)  # 10 ms

    errors: list[Exception] = []

    def worker():
        try:
            for _ in range(50):
                buf.append(chunk)
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Exceptions in threads: {errors}"
    # 10 threads × 50 appends × 240 samples = 120 000 samples → capped at 720 000
    assert buf.duration_seconds > 0


def test_audio_buffer_thread_safe_concurrent_reads_and_writes():
    """Concurrent reads and writes must not raise or return corrupt data."""
    buf = AudioBuffer(sample_rate=24000, max_seconds=10)

    errors: list[Exception] = []
    stop_event = threading.Event()

    def writer():
        try:
            while not stop_event.is_set():
                buf.append(np.ones(240, dtype=np.float32))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    def reader():
        try:
            while not stop_event.is_set():
                chunk = buf.read_last(0.1)
                # Basic sanity: dtype must be float32
                assert chunk.dtype == np.float32
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=writer)] + [
        threading.Thread(target=reader) for _ in range(4)
    ]
    for t in threads:
        t.start()

    # Let it run briefly then stop
    stop_event.wait(timeout=0.3)
    stop_event.set()
    for t in threads:
        t.join()

    assert not errors, f"Exceptions in threads: {errors}"
