"""Session lifecycle orchestrator.

Coordinates audio capture, transcription, and insight extraction.
Pushes updates to connected WebSocket clients.
Persists transcript, insights, and bookmarks to SQLite on stop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ribbet.config import settings
from ribbet.transcription.engine import TranscriptSegment, TranscriptionResult

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    session_id: str
    status: str = "idle"
    source_status: str = "unknown"
    model_status: str = "cold"
    result: TranscriptionResult = field(default_factory=TranscriptionResult)
    insight_snapshot: dict = field(
        default_factory=lambda: {
            "topics": [],
            "actions": [],
            "decisions": [],
            "stale": True,
            "last_updated": None,
        }
    )
    bookmarks: list[dict] = field(default_factory=list)

    @property
    def segments(self) -> list[TranscriptSegment]:
        return self.result.segments

    def add_segment(self, segment: TranscriptSegment) -> None:
        self.result.add_segment(segment)

    def get_snippet_around(self, timestamp: float, window_seconds: float = 30.0) -> str:
        """Get transcript text around a timestamp for bookmark snippets."""
        half = window_seconds / 2
        start = max(0.0, timestamp - half)
        end = timestamp + half
        return self.result.text_window(start, end)


class SessionOrchestrator:
    """Manages a single active session's lifecycle.

    There is at most one active session at a time.
    Pipeline wiring (audio capture → STT → insight extraction) is
    activated when the ML dependencies are available; otherwise the
    orchestrator degrades gracefully so the REST/WS layer still works.
    """

    def __init__(self):
        self._state: SessionState | None = None
        self._ws_clients: list[Any] = []  # WebSocket connections
        self._capture_task: asyncio.Task | None = None
        self._insight_task: asyncio.Task | None = None
        # Lazily-created pipeline components (None until first start_session)
        self._capture = None
        self._stt_engine = None
        self._insight_extractor = None

    # ------------------------------------------------------------------
    # WebSocket client registry
    # ------------------------------------------------------------------

    @property
    def active_session(self) -> SessionState | None:
        return self._state

    def register_ws(self, ws) -> None:
        self._ws_clients.append(ws)

    def unregister_ws(self, ws) -> None:
        if ws in self._ws_clients:
            self._ws_clients.remove(ws)

    async def broadcast(self, message: dict) -> None:
        """Send a JSON message to all connected WebSocket clients."""
        dead = []
        for ws in self._ws_clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.unregister_ws(ws)

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def start_session(self, session_id: str) -> SessionState:
        """Start a new transcription session.

        Pipeline:
          1. Check audio source availability → source_status
          2. Load STT model (if available) → model_status
          3. Launch _capture_loop task (audio → STT → broadcast)
          4. Launch _insight_loop task (sliding window → LLM → broadcast)

        If audio/ML deps are unavailable the session still starts in
        degraded mode so the WS/REST layer remains functional.
        """
        if self._state and self._state.status == "active":
            raise RuntimeError("A session is already active")

        self._state = SessionState(session_id=session_id, status="starting")
        await self.broadcast(
            {
                "type": "status",
                "session": "starting",
                "source": "unknown",
                "model": "cold",
            }
        )

        # ── Step 1: audio availability check ──────────────────────────
        await self._check_audio_source()

        # ── Step 2: STT model warm-up ──────────────────────────────────
        await self._warmup_stt()

        # ── Step 3 & 4: launch pipeline loops (if audio is available) ──
        if self._state.source_status == "capturing":
            self._capture_task = asyncio.create_task(
                self._capture_loop(), name=f"capture-{session_id}"
            )
            self._insight_task = asyncio.create_task(
                self._insight_loop(), name=f"insights-{session_id}"
            )
        # else: degraded mode — no pipeline tasks, but session is "active"

        self._state.status = "active"
        await self.broadcast(
            {
                "type": "status",
                "session": "active",
                "source": self._state.source_status,
                "model": self._state.model_status,
            }
        )

        return self._state

    async def stop_session(self, db_path: Path | None = None) -> None:
        """Stop the active session and persist data to SQLite.

        Args:
            db_path: Path to the SQLite database.  Defaults to
                     ``settings.db_path`` when None.
        """
        if not self._state:
            return

        self._state.status = "stopping"
        await self.broadcast(
            {
                "type": "status",
                "session": "stopping",
                "source": self._state.source_status,
                "model": self._state.model_status,
            }
        )

        # ── Cancel pipeline tasks ──────────────────────────────────────
        for task in (self._capture_task, self._insight_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._capture_task = None
        self._insight_task = None

        # ── Stop hardware capture ──────────────────────────────────────
        if self._capture is not None:
            try:
                await self._capture.stop()
            except Exception as exc:
                logger.warning("Error stopping audio capture: %s", exc)

        # ── Persist to SQLite ──────────────────────────────────────────
        path = db_path or settings.db_path
        try:
            await self._persist_session(path)
        except Exception as exc:
            logger.error("Failed to persist session %s: %s", self._state.session_id, exc)

        self._state.status = "stopped"
        await self.broadcast(
            {
                "type": "status",
                "session": "stopped",
                "source": "unknown",
                "model": "cold",
            }
        )

    # ------------------------------------------------------------------
    # Segment / insight / bookmark handlers
    # ------------------------------------------------------------------

    async def handle_new_segment(self, segment: TranscriptSegment) -> None:
        """Called when the transcription engine produces a new segment."""
        if not self._state:
            return
        self._state.add_segment(segment)
        await self.broadcast(
            {
                "type": "transcript",
                "segment": {
                    "id": segment.id,
                    "text": segment.text,
                    "start_time": segment.start_time,
                    "end_time": segment.end_time,
                    "is_partial": segment.is_partial,
                },
            }
        )

    async def update_insights(self, snapshot: dict) -> None:
        """Called when insight extraction produces new results."""
        if not self._state:
            return
        self._state.insight_snapshot = snapshot
        await self.broadcast({"type": "insights", "snapshot": snapshot})

    def create_bookmark(self, note: str) -> dict | None:
        """Create a bookmark at the current position."""
        if not self._state or self._state.status != "active":
            return None
        if not self._state.segments:
            timestamp = 0.0
        else:
            timestamp = self._state.segments[-1].end_time

        snippet = self._state.get_snippet_around(
            timestamp, window_seconds=settings.bookmark_snippet_seconds
        )
        bookmark = {
            "id": str(uuid.uuid4()),
            "timestamp": timestamp,
            "note": note,
            "snippet": snippet,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._state.bookmarks.append(bookmark)
        return bookmark

    # ------------------------------------------------------------------
    # Private: pipeline wiring helpers
    # ------------------------------------------------------------------

    async def _check_audio_source(self) -> None:
        """Probe audio availability and update source_status."""
        try:
            from ribbet.audio.capture import AudioCaptureConfig, SystemAudioCapture

            config = AudioCaptureConfig(
                sample_rate=settings.stt_quantization,  # reuse sample_rate default (24 kHz)
                channels=1,
            )
            # AudioCaptureConfig.sample_rate defaults to 24000 — quantization field ≠ sample_rate
            # Recreate with proper defaults:
            config = AudioCaptureConfig()
            self._capture = SystemAudioCapture(config)
            available, msg = await self._capture.check_availability()
            if available:
                self._state.source_status = "capturing"
                logger.info("Audio source available: %s", msg)
            else:
                self._state.source_status = "unavailable"
                logger.warning("Audio source unavailable: %s", msg)
                await self.broadcast(
                    {
                        "type": "error",
                        "message": (
                            f"System audio capture is not available: {msg}. "
                            "Grant Screen Recording permission in System Settings → Privacy."
                        ),
                    }
                )
        except Exception as exc:
            self._state.source_status = "unavailable"
            logger.warning("Audio probe failed: %s", exc)

        await self.broadcast(
            {
                "type": "status",
                "session": self._state.status,
                "source": self._state.source_status,
                "model": self._state.model_status,
            }
        )

    async def _warmup_stt(self) -> None:
        """Load STT model and update model_status."""
        if self._state.source_status == "unavailable":
            # No point loading the model if there's no audio
            return

        self._state.model_status = "warming"
        await self.broadcast(
            {
                "type": "status",
                "session": self._state.status,
                "source": self._state.source_status,
                "model": "warming",
            }
        )

        try:
            from ribbet.transcription.engine import TranscriptionEngine

            if self._stt_engine is None:
                self._stt_engine = TranscriptionEngine(
                    model_repo=settings.stt_model_repo,
                    quantization=settings.stt_quantization,
                )
            await self._stt_engine.load()
            self._state.model_status = "ready"
            logger.info("STT model ready")
        except Exception as exc:
            self._state.model_status = "cold"
            logger.warning("STT model failed to load: %s", exc)
            await self.broadcast({"type": "error", "message": f"STT model load failed: {exc}"})

    async def _capture_loop(self) -> None:
        """Main audio capture + transcription loop.

        Reads PCM chunks from SystemAudioCapture, feeds them to the STT
        engine, and calls handle_new_segment() for each new transcript segment.

        This loop requires both _capture and _stt_engine to be ready.
        It degrades gracefully when the actual moshi_mlx inference is not
        yet wired (the engine raises _StubNotImplemented).
        """
        if self._capture is None or self._stt_engine is None:
            logger.warning("Capture loop started without capture/STT — exiting immediately")
            return

        from ribbet.audio.capture import AudioBuffer, AudioCaptureConfig
        from ribbet.transcription.engine import _StubNotImplemented

        config = AudioCaptureConfig()
        buffer = AudioBuffer(
            sample_rate=config.sample_rate,
            max_seconds=config.buffer_max_seconds,
        )

        # Wire chunk callback to the buffer
        def _on_chunk(chunk):
            buffer.append(chunk)

        self._capture.on_chunk = _on_chunk

        try:
            await self._capture.start()
        except RuntimeError as exc:
            logger.error("Could not start audio capture: %s", exc)
            if self._state:
                self._state.source_status = "interrupted"
            await self.broadcast(
                {
                    "type": "status",
                    "session": self._state.status if self._state else "error",
                    "source": "interrupted",
                    "model": self._state.model_status if self._state else "cold",
                }
            )
            return

        # Chunk size: 0.5 s of audio (matches Kyutai's recommended window)
        chunk_duration = 0.5
        session_start = asyncio.get_event_loop().time()
        last_read_pos: float = 0.0  # seconds of audio consumed

        try:
            while True:
                await asyncio.sleep(chunk_duration)

                if not self._state or self._state.status not in ("starting", "active"):
                    break

                audio_chunk = buffer.read_last(chunk_duration)
                if len(audio_chunk) == 0:
                    continue

                chunk_start_time = asyncio.get_event_loop().time() - session_start

                try:
                    segments = await self._stt_engine.transcribe_chunk(
                        audio_chunk, chunk_start_time
                    )
                    for seg in segments:
                        await self.handle_new_segment(seg)
                except _StubNotImplemented:
                    # STT not yet wired — log once, keep looping so capture
                    # stays active and the rest of the pipeline is exercised
                    logger.debug("STT stub: transcription not wired (expected in dev mode)")
                except Exception as exc:
                    logger.error("Transcription error: %s", exc)

        except asyncio.CancelledError:
            logger.info("Capture loop cancelled")
            raise
        finally:
            try:
                await self._capture.stop()
            except Exception:
                pass

    async def _insight_loop(self) -> None:
        """Periodic insight extraction loop.

        Every ``settings.insight_refresh_seconds``, extracts insights from
        the most recent ``settings.insight_window_seconds`` of transcript
        and broadcasts the result.  Failures mark the snapshot as stale but
        never interrupt the transcription fast-path.
        """
        try:
            from ribbet.insights.extractor import InsightExtractor

            if self._insight_extractor is None:
                self._insight_extractor = InsightExtractor()

            try:
                await self._insight_extractor.load()
            except Exception as exc:
                logger.warning("Insight extractor failed to load: %s", exc)
                # Mark stale and return — insights are optional
                return

            while True:
                await asyncio.sleep(settings.insight_refresh_seconds)

                if not self._state or self._state.status not in ("starting", "active"):
                    break

                window_text = self._state.result.recent_text(settings.insight_window_seconds)
                if not window_text.strip():
                    continue

                try:
                    raw = await self._insight_extractor.extract(window_text)
                    snapshot = {
                        **raw,
                        "stale": False,
                        "last_updated": datetime.now(timezone.utc).isoformat(),
                    }
                    # Normalise action/decision items to include stable IDs
                    for item in snapshot.get("actions", []):
                        item.setdefault("id", str(uuid.uuid4()))
                        item.setdefault("timestamp", 0.0)
                    for item in snapshot.get("decisions", []):
                        item.setdefault("id", str(uuid.uuid4()))
                        item.setdefault("timestamp", 0.0)
                    await self.update_insights(snapshot)
                except Exception as exc:
                    logger.error("Insight extraction failed: %s", exc)
                    # Mark existing snapshot as stale but don't crash
                    stale_snapshot = dict(self._state.insight_snapshot)
                    stale_snapshot["stale"] = True
                    await self.update_insights(stale_snapshot)

        except asyncio.CancelledError:
            logger.info("Insight loop cancelled")
            raise

    # ------------------------------------------------------------------
    # Private: persistence
    # ------------------------------------------------------------------

    async def _persist_session(self, db_path: Path) -> None:
        """Write in-memory segments, insights, and bookmarks to SQLite.

        The session row itself is updated to status='stopped' / ended_at
        by the REST layer (sessions router); here we only write the
        child rows that were accumulated in memory during the session.
        """
        from ribbet.db import get_db

        state = self._state
        if state is None:
            return

        now = datetime.now(timezone.utc).isoformat()

        async with get_db(db_path) as db:
            # ── Upsert transcript segments ─────────────────────────────
            for seg in state.segments:
                # INSERT OR IGNORE so re-runs don't duplicate confirmed segs
                await db.execute(
                    """INSERT OR IGNORE INTO transcript_segments
                       (id, session_id, text, start_time, end_time, is_partial, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        seg.id,
                        state.session_id,
                        seg.text,
                        seg.start_time,
                        seg.end_time,
                        int(seg.is_partial),
                        now,
                    ),
                )

            # ── Save final insight snapshot (if non-empty) ─────────────
            snap = state.insight_snapshot
            has_content = any(snap.get(k) for k in ("topics", "actions", "decisions"))
            if has_content:
                await db.execute(
                    """INSERT INTO insight_snapshots
                       (id, session_id, snapshot_json, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()),
                        state.session_id,
                        json.dumps(snap),
                        now,
                    ),
                )

            # ── Persist bookmarks (INSERT OR IGNORE avoids duplicates) ─
            for bm in state.bookmarks:
                await db.execute(
                    """INSERT OR IGNORE INTO bookmarks
                       (id, session_id, timestamp, note, snippet, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        bm["id"],
                        state.session_id,
                        bm["timestamp"],
                        bm["note"],
                        bm["snippet"],
                        bm["created_at"],
                    ),
                )

            await db.commit()

        logger.info(
            "Persisted session %s: %d segments, %d bookmarks",
            state.session_id,
            len(state.segments),
            len(state.bookmarks),
        )


# Global singleton — one orchestrator per server process
orchestrator = SessionOrchestrator()
