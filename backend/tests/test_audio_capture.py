"""Tests for audio capture module.

Tests cover:
  - AudioBuffer (platform-independent) — always run
  - SystemAudioCapture.check_availability() — always run
  - SystemAudioCapture.start() with missing deps — always run (CI-safe)
  - Real capture tests are marked @pytest.mark.macos and require:
      • macOS 13+ (Ventura or later)
      • pyobjc-framework-ScreenCaptureKit installed
      • Screen Recording permission granted
      Run with: pytest -m macos
"""

from __future__ import annotations

import threading

import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch

from ribbet.audio.capture import AudioBuffer, AudioCaptureConfig, SystemAudioCapture

# ---------------------------------------------------------------------------
# Availability detection
# ---------------------------------------------------------------------------

_SCK_AVAILABLE = False
try:
    import ScreenCaptureKit  # noqa: F401
    import objc  # noqa: F401
    import CoreMedia  # noqa: F401

    _SCK_AVAILABLE = True
except ImportError:
    pass

requires_sck = pytest.mark.skipif(
    not _SCK_AVAILABLE,
    reason="pyobjc-framework-ScreenCaptureKit not installed — skipping SCK tests",
)


# ---------------------------------------------------------------------------
# AudioBuffer — basic operation
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# AudioBuffer — truncation behaviour
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# AudioBuffer — thread-safety
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# SystemAudioCapture — availability check (CI-safe)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_availability_returns_tuple():
    """check_availability must return a (bool, str) tuple."""
    capture = SystemAudioCapture(AudioCaptureConfig())
    result = await capture.check_availability()
    assert isinstance(result, tuple)
    assert len(result) == 2
    ok, msg = result
    assert isinstance(ok, bool)
    assert isinstance(msg, str)


@pytest.mark.asyncio
async def test_check_availability_false_when_deps_missing():
    """When SCK deps are absent, check_availability returns (False, descriptive msg)."""
    if _SCK_AVAILABLE:
        pytest.skip("ScreenCaptureKit installed — skipping dep-missing scenario")

    capture = SystemAudioCapture(AudioCaptureConfig())
    ok, msg = await capture.check_availability()
    assert ok is False
    assert "ScreenCaptureKit" in msg or "pyobjc" in msg.lower()


@pytest.mark.asyncio
async def test_check_availability_true_when_deps_present():
    """When SCK deps are present, check_availability returns (True, ...)."""
    if not _SCK_AVAILABLE:
        pytest.skip("ScreenCaptureKit not installed")

    capture = SystemAudioCapture(AudioCaptureConfig())
    ok, msg = await capture.check_availability()
    assert ok is True
    assert msg  # non-empty


# ---------------------------------------------------------------------------
# SystemAudioCapture — start() raises when deps missing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_raises_runtime_error_when_deps_missing():
    """start() must raise RuntimeError with install hint when SCK unavailable."""
    if _SCK_AVAILABLE:
        pytest.skip("ScreenCaptureKit installed — skipping")

    capture = SystemAudioCapture(AudioCaptureConfig())
    with pytest.raises(RuntimeError, match="ScreenCaptureKit|pyobjc"):
        await capture.start()

    assert capture.is_running is False


@pytest.mark.asyncio
async def test_start_raises_runtime_error_mocked():
    """start() raises RuntimeError when check_availability returns False (mocked)."""
    capture = SystemAudioCapture(AudioCaptureConfig())

    async def _fake_check():
        return False, "ScreenCaptureKit not available. Install pyobjc-framework-ScreenCaptureKit."

    capture.check_availability = _fake_check  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="ScreenCaptureKit"):
        await capture.start()

    assert capture.is_running is False


# ---------------------------------------------------------------------------
# SystemAudioCapture — start() + stop() with mocked SCK (CI-safe)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_stop_with_mocked_sck():
    """Verify start/stop state transitions using a mocked _start_sck_stream."""
    capture = SystemAudioCapture(AudioCaptureConfig(), on_chunk=lambda _: None)

    # Patch _start_sck_stream so no real ObjC calls happen
    async def _fake_start_sck():
        capture._running = True

    capture._start_sck_stream = _fake_start_sck  # type: ignore[method-assign]

    # Also patch check_availability to return True
    async def _fake_check():
        return True, "mocked"

    capture.check_availability = _fake_check  # type: ignore[method-assign]

    assert capture.is_running is False
    await capture.start()
    assert capture.is_running is True

    await capture.stop()
    assert capture.is_running is False


@pytest.mark.asyncio
async def test_start_twice_is_noop():
    """Calling start() a second time when already running must not raise."""
    capture = SystemAudioCapture(AudioCaptureConfig())

    async def _fake_start_sck():
        capture._running = True

    async def _fake_check():
        return True, "mocked"

    capture._start_sck_stream = _fake_start_sck  # type: ignore[method-assign]
    capture.check_availability = _fake_check  # type: ignore[method-assign]

    call_count = {"n": 0}
    original = capture._start_sck_stream

    async def _counting_start():
        call_count["n"] += 1
        await original()

    capture._start_sck_stream = _counting_start  # type: ignore[method-assign]

    await capture.start()
    await capture.start()  # second call — should be a no-op

    assert call_count["n"] == 1  # _start_sck_stream called only once
    assert capture.is_running is True


@pytest.mark.asyncio
async def test_stop_when_not_running_is_noop():
    """stop() on a never-started capture must not raise."""
    capture = SystemAudioCapture(AudioCaptureConfig())
    await capture.stop()  # must not raise
    assert capture.is_running is False


@pytest.mark.asyncio
async def test_on_chunk_callback_invoked():
    """on_chunk callback must be invoked with float32 array from _start_sck_stream.

    We simulate the callback path by directly calling on_chunk from a fake
    _start_sck_stream, bypassing the ObjC bridge.
    """
    received: list[np.ndarray] = []

    def _on_chunk(chunk: np.ndarray) -> None:
        received.append(chunk)

    capture = SystemAudioCapture(AudioCaptureConfig(), on_chunk=_on_chunk)

    async def _fake_start_sck():
        capture._running = True
        # Simulate audio arriving: call on_chunk directly
        fake_audio = np.ones(1920, dtype=np.float32)
        capture.on_chunk(fake_audio)

    async def _fake_check():
        return True, "mocked"

    capture._start_sck_stream = _fake_start_sck  # type: ignore[method-assign]
    capture.check_availability = _fake_check  # type: ignore[method-assign]

    await capture.start()
    await capture.stop()

    assert len(received) == 1
    assert received[0].dtype == np.float32
    assert len(received[0]) == 1920


# ---------------------------------------------------------------------------
# SystemAudioCapture — real hardware tests (macOS + permission required)
# ---------------------------------------------------------------------------


@pytest.mark.macos
@pytest.mark.asyncio
@requires_sck
async def test_real_capture_starts_and_stops():
    """Live ScreenCaptureKit capture — requires macOS 13+ and Screen Recording perm."""
    chunks: list[np.ndarray] = []

    def _on_chunk(chunk: np.ndarray) -> None:
        chunks.append(chunk)

    config = AudioCaptureConfig(sample_rate=24000, channels=1)
    capture = SystemAudioCapture(config, on_chunk=_on_chunk)

    ok, msg = await capture.check_availability()
    assert ok, f"SCK not available: {msg}"

    await capture.start()
    assert capture.is_running

    # Let it run for a short time to collect some audio
    import asyncio

    await asyncio.sleep(0.5)

    await capture.stop()
    assert not capture.is_running

    # Some chunks should have arrived (silence or system audio)
    assert len(chunks) > 0
    for chunk in chunks:
        assert chunk.dtype == np.float32
        assert chunk.ndim == 1
