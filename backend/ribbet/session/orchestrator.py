"""Session lifecycle orchestrator.

Coordinates audio capture, transcription, and insight extraction.
Pushes updates to connected WebSocket clients.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    """

    def __init__(self):
        self._state: SessionState | None = None
        self._ws_clients: list[Any] = []  # WebSocket connections
        self._capture_task: asyncio.Task | None = None
        self._insight_task: asyncio.Task | None = None

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

    async def start_session(self, session_id: str) -> SessionState:
        """Start a new transcription session."""
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

        # In full implementation (Task 12):
        # 1. Check audio source availability → update source_status
        # 2. Load STT model if needed → update model_status
        # 3. Start audio capture loop → _capture_task
        # 4. Start insight extraction loop → _insight_task

        self._state.status = "active"
        self._state.source_status = "capturing"
        self._state.model_status = "ready"

        await self.broadcast(
            {
                "type": "status",
                "session": "active",
                "source": "capturing",
                "model": "ready",
            }
        )

        return self._state

    async def stop_session(self) -> None:
        """Stop the active session."""
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

        # Cancel background tasks
        if self._capture_task and not self._capture_task.done():
            self._capture_task.cancel()
            try:
                await self._capture_task
            except asyncio.CancelledError:
                pass
        if self._insight_task and not self._insight_task.done():
            self._insight_task.cancel()
            try:
                await self._insight_task
            except asyncio.CancelledError:
                pass

        self._state.status = "stopped"
        await self.broadcast(
            {
                "type": "status",
                "session": "stopped",
                "source": "unknown",
                "model": "cold",
            }
        )

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


# Global singleton — one orchestrator per server process
orchestrator = SessionOrchestrator()
