"""System audio capture via macOS ScreenCaptureKit.

The AudioBuffer class is platform-independent and testable.
The SystemAudioCapture class wraps ScreenCaptureKit and requires macOS + permissions.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class AudioCaptureConfig:
    sample_rate: int = 24000
    channels: int = 1
    buffer_max_seconds: float = 300  # 5 min rolling buffer


class AudioBuffer:
    """Thread-safe rolling audio buffer."""

    def __init__(self, sample_rate: int, max_seconds: float):
        self.sample_rate = sample_rate
        self._max_samples = int(max_seconds * sample_rate)
        self._data = np.array([], dtype=np.float32)

    def append(self, chunk: np.ndarray) -> None:
        self._data = np.concatenate([self._data, chunk.astype(np.float32)])
        if len(self._data) > self._max_samples:
            self._data = self._data[-self._max_samples :]

    def read_last(self, seconds: float) -> np.ndarray:
        n = int(seconds * self.sample_rate)
        if len(self._data) == 0:
            return np.array([], dtype=np.float32)
        return self._data[-n:]

    @property
    def duration_seconds(self) -> float:
        return len(self._data) / self.sample_rate


class SystemAudioCapture:
    """Captures system audio via macOS ScreenCaptureKit.

    Usage:
        capture = SystemAudioCapture(config, on_chunk=callback)
        available = await capture.check_availability()
        if available:
            await capture.start()
            # ... later
            await capture.stop()
    """

    def __init__(
        self,
        config: AudioCaptureConfig,
        on_chunk: Callable[[np.ndarray], None] | None = None,
    ):
        self.config = config
        self.on_chunk = on_chunk
        self._stream = None
        self._running = False

    async def check_availability(self) -> tuple[bool, str]:
        """Check if system audio capture is available.

        Returns (is_available, message).
        """
        try:
            import ScreenCaptureKit  # noqa: F401

            return True, "ScreenCaptureKit available"
        except ImportError:
            return False, (
                "ScreenCaptureKit not available. "
                "Install pyobjc-framework-ScreenCaptureKit and ensure macOS 13+."
            )

    async def start(self) -> None:
        """Start capturing system audio. Raises RuntimeError if unavailable."""
        available, msg = await self.check_availability()
        if not available:
            raise RuntimeError(msg)

        # Actual ScreenCaptureKit setup is implemented here.
        # This is a simplified skeleton — full implementation will use
        # SCShareableContent, SCStreamConfiguration, and SCStream.
        logger.info("Starting system audio capture at %d Hz", self.config.sample_rate)
        self._running = True

        # Implementation note for the engineer:
        # The full implementation needs to:
        # 1. Get SCShareableContent.getWithCompletionHandler_()
        # 2. Create SCStreamConfiguration with audio enabled
        # 3. Set sample rate to self.config.sample_rate
        # 4. Create SCStream and add a stream output delegate
        # 5. The delegate's stream_didOutputSampleBuffer_ofType_ method
        #    converts CMSampleBuffer → numpy array and calls self.on_chunk()
        #
        # See Task 5 implementation notes in the plan for the full PyObjC code:
        # 1. Get: SCShareableContent.getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_
        # 2. Configure: capturesAudio=True, excludesCurrentProcessAudio=False,
        #               sampleRate=self.config.sample_rate, channelCount=self.config.channels
        # 3. Create SCStreamOutput delegate subclass that receives CMSampleBuffer,
        #    extracts PCM float data, and calls self.on_chunk(numpy_array)

    async def stop(self) -> None:
        """Stop capturing."""
        self._running = False
        logger.info("Stopped system audio capture")

    @property
    def is_running(self) -> bool:
        return self._running
