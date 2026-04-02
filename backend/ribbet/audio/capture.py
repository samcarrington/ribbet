"""System audio capture via macOS ScreenCaptureKit.

The AudioBuffer class is platform-independent and testable.
The SystemAudioCapture class wraps ScreenCaptureKit and requires macOS + permissions.

Runtime prerequisites:
  pip install pyobjc-framework-ScreenCaptureKit
  macOS 13+ (Ventura or later)
  Screen Recording permission granted to the running process in System Settings →
  Privacy & Security → Screen Recording.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public data classes
# ---------------------------------------------------------------------------


@dataclass
class AudioCaptureConfig:
    sample_rate: int = 24000
    channels: int = 1
    buffer_max_seconds: float = 300  # 5 min rolling buffer


# ---------------------------------------------------------------------------
# AudioBuffer
# ---------------------------------------------------------------------------


class AudioBuffer:
    """Thread-safe rolling audio buffer.

    All public methods acquire an internal lock so they are safe to call
    from multiple threads (e.g. an audio-capture callback thread and the
    main/async thread that reads audio for transcription).
    """

    def __init__(self, sample_rate: int, max_seconds: float):
        self.sample_rate = sample_rate
        self._max_samples = int(max_seconds * sample_rate)
        self._data = np.array([], dtype=np.float32)
        self._lock = threading.Lock()

    def append(self, chunk: np.ndarray) -> None:
        """Append *chunk* to the buffer, evicting the oldest samples if needed."""
        with self._lock:
            self._data = np.concatenate([self._data, chunk.astype(np.float32)])
            if len(self._data) > self._max_samples:
                self._data = self._data[-self._max_samples :]

    def read_last(self, seconds: float) -> np.ndarray:
        """Return up to *seconds* worth of the most recent audio samples.

        If fewer samples are available than requested, all available samples
        are returned (i.e. the result may be shorter than ``seconds``).
        The returned array is a copy; subsequent ``append`` calls will not
        affect it.
        """
        n = int(seconds * self.sample_rate)
        with self._lock:
            if len(self._data) == 0:
                return np.array([], dtype=np.float32)
            return self._data[-n:].copy()

    @property
    def duration_seconds(self) -> float:
        with self._lock:
            return len(self._data) / self.sample_rate


# ---------------------------------------------------------------------------
# ScreenCaptureKit bridge (lazy import — requires pyobjc + macOS 13+)
# ---------------------------------------------------------------------------


def _build_sck_delegate_class(on_chunk: Callable[[np.ndarray], None], sample_rate: int):
    """Dynamically build the ObjC SCStreamOutput delegate class.

    Defined inside a function so the import only happens when ScreenCaptureKit
    is actually available at runtime; the rest of the module stays importable
    in non-macOS / non-pyobjc environments.

    Returns an instance of the delegate class.
    """
    import objc  # pyobjc-core
    import CoreMedia  # pyobjc-framework-CoreMedia
    from ScreenCaptureKit import SCStreamOutput  # pyobjc-framework-ScreenCaptureKit

    # SCStreamOutput is an ObjC protocol; we implement it as a Python class.
    class _AudioStreamDelegate(objc.Protocol(SCStreamOutput)):  # type: ignore[misc]
        """Receives CMSampleBuffer callbacks from SCStream and converts to numpy."""

        @objc.python_method
        def _on_chunk(self, chunk: np.ndarray) -> None:
            """Trampoline so we can hold a Python callable without ObjC cycles."""
            try:
                on_chunk(chunk)
            except Exception:
                logger.exception("on_chunk callback raised")

        def stream_didOutputSampleBuffer_ofType_(self, stream, sample_buffer, output_type):  # noqa: N802
            """SCStreamOutput delegate method — called on a private SCKit thread."""
            try:
                # Extract CMSampleBuffer → raw PCM bytes → numpy float32
                format_desc = CoreMedia.CMSampleBufferGetFormatDescription(sample_buffer)
                asbd = CoreMedia.CMAudioFormatDescriptionGetStreamBasicDescription(format_desc)
                # asbd is an AudioStreamBasicDescription struct
                sr = int(asbd.mSampleRate)  # capture may differ from requested
                num_frames = CoreMedia.CMSampleBufferGetNumSamples(sample_buffer)

                # Get audio buffer list
                status, audio_buf_list, buf_size = (
                    CoreMedia.CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(
                        sample_buffer,
                        None,
                        None,
                        0,
                        None,
                        None,
                        CoreMedia.kCMSampleBufferFlag_AudioBufferList_Assure16ByteAlignment,
                        None,
                    )
                )
                if status != 0:
                    logger.warning(
                        "CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer failed: %d", status
                    )
                    return

                # audio_buf_list.mBuffers is a sequence of AudioBuffer structs
                # For interleaved mono/stereo float32 the data lives in mBuffers[0]
                buf = audio_buf_list.mBuffers[0]
                data_bytes = bytes(buf.mData[: buf.mDataByteSize])
                pcm = np.frombuffer(data_bytes, dtype=np.float32).copy()

                # Collapse stereo → mono by averaging channels if needed
                num_channels = int(asbd.mChannelsPerFrame)
                if num_channels > 1:
                    pcm = pcm.reshape(-1, num_channels).mean(axis=1)

                # Resample if capture rate differs from configured rate
                if sr != sample_rate and len(pcm) > 0:
                    target_len = int(len(pcm) * sample_rate / sr)
                    if target_len > 0:
                        pcm = np.interp(
                            np.linspace(0, len(pcm) - 1, target_len),
                            np.arange(len(pcm)),
                            pcm,
                        ).astype(np.float32)

                if len(pcm) > 0:
                    self._on_chunk(pcm)

            except Exception:
                logger.exception("Error in SCStream audio callback")

    return _AudioStreamDelegate.new()


# ---------------------------------------------------------------------------
# SystemAudioCapture
# ---------------------------------------------------------------------------


class SystemAudioCapture:
    """Captures system audio via macOS ScreenCaptureKit.

    Usage::

        capture = SystemAudioCapture(config, on_chunk=callback)
        available, msg = await capture.check_availability()
        if available:
            await capture.start()
            # ... later
            await capture.stop()

    The *on_chunk* callback is invoked on a private ScreenCaptureKit thread
    with a float32 mono numpy array at ``config.sample_rate`` Hz.

    Raises:
        RuntimeError: if start() is called when ScreenCaptureKit is unavailable,
            permissions are denied, or the stream cannot be created.
    """

    def __init__(
        self,
        config: AudioCaptureConfig,
        on_chunk: Callable[[np.ndarray], None] | None = None,
    ):
        self.config = config
        self.on_chunk = on_chunk
        self._stream = None
        self._delegate = None
        self._running = False

    # ------------------------------------------------------------------
    # Availability check
    # ------------------------------------------------------------------

    async def check_availability(self) -> tuple[bool, str]:
        """Check whether system audio capture prerequisites are met.

        Returns:
            (is_available, human_readable_message)
        """
        missing: list[str] = []
        for mod in ("ScreenCaptureKit", "objc", "CoreMedia"):
            try:
                __import__(mod)
            except ImportError:
                missing.append(mod)

        if missing:
            return False, (
                f"Missing PyObjC modules: {', '.join(missing)}. "
                "Install with: pip install pyobjc-framework-ScreenCaptureKit "
                "and ensure macOS 13+ (Ventura or later)."
            )
        return True, "ScreenCaptureKit available"

    # ------------------------------------------------------------------
    # start / stop
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start capturing system audio.

        Raises:
            RuntimeError: if prerequisites are missing or permissions are denied.
        """
        available, msg = await self.check_availability()
        if not available:
            raise RuntimeError(msg)

        if self._running:
            logger.debug("SystemAudioCapture.start() called while already running — no-op")
            return

        logger.info("Starting system audio capture at %d Hz", self.config.sample_rate)

        try:
            await self._start_sck_stream()
        except Exception as exc:
            self._running = False
            self._stream = None
            self._delegate = None
            raise RuntimeError(
                f"Failed to start ScreenCaptureKit stream: {exc}. "
                "Check that Screen Recording permission is granted in "
                "System Settings → Privacy & Security → Screen Recording."
            ) from exc

    async def _start_sck_stream(self) -> None:
        """Internal: wire up SCShareableContent → SCStreamConfiguration → SCStream."""
        import asyncio
        import CoreMedia
        import ScreenCaptureKit as SCK

        loop = asyncio.get_running_loop()
        content_future: asyncio.Future = loop.create_future()

        def _content_handler(content, error):
            if error is not None:
                loop.call_soon_threadsafe(
                    content_future.set_exception,
                    RuntimeError(f"SCShareableContent error: {error}"),
                )
            else:
                loop.call_soon_threadsafe(content_future.set_result, content)

        # Request shareable content (async ObjC callback)
        SCK.SCShareableContent.getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(
            True,  # excludeDesktopWindows
            False,  # onScreenWindowsOnly
            _content_handler,
        )

        content = await asyncio.wait_for(content_future, timeout=10.0)

        # Build audio-only stream configuration
        config = SCK.SCStreamConfiguration.alloc().init()
        config.setCapturesAudio_(True)
        config.setExcludesCurrentProcessAudio_(False)
        config.setSampleRate_(self.config.sample_rate)
        config.setChannelCount_(1)

        # Disable video capture (audio-only stream)
        config.setWidth_(2)
        config.setHeight_(2)
        config.setMinimumFrameInterval_(
            CoreMedia.CMTimeMake(1, 1)  # 1 fps — effectively disabled
        )

        # Use the first display as the stream source (audio is system-wide regardless)
        displays = content.displays()
        if not displays:
            raise RuntimeError("No displays found — cannot create SCStream")
        display = displays[0]
        content_filter = SCK.SCContentFilter.alloc().initWithDisplay_excludingWindows_(display, [])

        # Build delegate and stream
        if self.on_chunk is not None:
            self._delegate = _build_sck_delegate_class(self.on_chunk, self.config.sample_rate)
        else:
            # No-op delegate when no callback is provided
            self._delegate = _build_sck_delegate_class(lambda _: None, self.config.sample_rate)

        stream = SCK.SCStream.alloc().initWithFilter_configuration_delegate_(
            content_filter, config, None
        )

        # Add our audio output handler
        error_ptr = None
        ok = stream.addStreamOutput_type_sampleHandlerQueue_error_(
            self._delegate,
            SCK.SCStreamOutputTypeAudio,
            None,  # use default dispatch queue
            error_ptr,
        )
        if not ok:
            raise RuntimeError("addStreamOutput failed for audio output")

        start_future: asyncio.Future = loop.create_future()

        def _start_handler(error):
            if error is not None:
                loop.call_soon_threadsafe(
                    start_future.set_exception,
                    RuntimeError(f"SCStream startCapture error: {error}"),
                )
            else:
                loop.call_soon_threadsafe(start_future.set_result, None)

        stream.startCaptureWithCompletionHandler_(_start_handler)
        await asyncio.wait_for(start_future, timeout=10.0)

        self._stream = stream
        self._running = True
        logger.info("SCStream audio capture started")

    async def stop(self) -> None:
        """Stop capturing and release the SCStream."""
        if not self._running:
            return

        self._running = False

        if self._stream is not None:
            import asyncio

            loop = asyncio.get_running_loop()
            stop_future: asyncio.Future = loop.create_future()

            def _stop_handler(error):
                loop.call_soon_threadsafe(stop_future.set_result, None)

            try:
                self._stream.stopCaptureWithCompletionHandler_(_stop_handler)
                await asyncio.wait_for(stop_future, timeout=5.0)
            except Exception:
                logger.exception("Error stopping SCStream")
            finally:
                self._stream = None
                self._delegate = None

        logger.info("Stopped system audio capture")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running
