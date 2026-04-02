"""Integration tests for Task 12: end-to-end pipeline wiring.

These tests exercise the full request→orchestrator→DB path using a real
(in-memory temp) SQLite database and a real SessionOrchestrator instance.
Audio capture and STT are mocked so the tests run without hardware.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from ribbet.db import get_db, init_db
from ribbet.session.orchestrator import SessionOrchestrator, SessionState
from ribbet.transcription.engine import TranscriptSegment


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_path(tmp_path) -> Path:
    """Isolated temp database."""
    path = tmp_path / "test_integration.db"
    await init_db(path)
    return path


async def _insert_session(db_path: Path, session_id: str) -> None:
    """Insert a minimal session row to satisfy FK constraints."""
    now = datetime.now(timezone.utc).isoformat()
    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO sessions (id, started_at, status) VALUES (?, ?, ?)",
            (session_id, now, "active"),
        )
        await db.commit()


@pytest.fixture
def fresh_orchestrator() -> SessionOrchestrator:
    """A real SessionOrchestrator instance (not the global singleton)."""
    return SessionOrchestrator()


# ---------------------------------------------------------------------------
# Orchestrator stop → persist integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_session_persists_segments(fresh_orchestrator, db_path):
    """stop_session() must write in-memory segments to SQLite."""
    # Set up state directly (skip real audio probe)
    session_id = str(uuid.uuid4())
    await _insert_session(db_path, session_id)
    fresh_orchestrator._state = SessionState(session_id=session_id, status="active")
    segs = [
        TranscriptSegment(f"sentence {i}", float(i * 5), float(i * 5 + 4), False) for i in range(3)
    ]
    for seg in segs:
        fresh_orchestrator._state.add_segment(seg)

    await fresh_orchestrator.stop_session(db_path=db_path)

    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT text FROM transcript_segments WHERE session_id = ? ORDER BY start_time",
            (session_id,),
        )
        rows = await cursor.fetchall()

    assert len(rows) == 3
    assert rows[0]["text"] == "sentence 0"
    assert rows[2]["text"] == "sentence 2"


@pytest.mark.asyncio
async def test_stop_session_persists_bookmarks(fresh_orchestrator, db_path):
    """stop_session() must write in-memory bookmarks to SQLite."""
    session_id = str(uuid.uuid4())
    await _insert_session(db_path, session_id)
    fresh_orchestrator._state = SessionState(session_id=session_id, status="active")
    # Add a segment so bookmark gets a real timestamp/snippet
    fresh_orchestrator._state.add_segment(TranscriptSegment("decision reached", 10.0, 11.0, False))
    bookmark = fresh_orchestrator.create_bookmark("Key decision")
    assert bookmark is not None

    await fresh_orchestrator.stop_session(db_path=db_path)

    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT note, snippet FROM bookmarks WHERE session_id = ?",
            (session_id,),
        )
        rows = await cursor.fetchall()

    assert len(rows) == 1
    assert rows[0]["note"] == "Key decision"
    assert "decision reached" in rows[0]["snippet"]


@pytest.mark.asyncio
async def test_stop_session_persists_insight_snapshot(fresh_orchestrator, db_path):
    """stop_session() must persist a non-empty insight snapshot."""
    session_id = str(uuid.uuid4())
    await _insert_session(db_path, session_id)
    fresh_orchestrator._state = SessionState(session_id=session_id, status="active")
    fresh_orchestrator._state.insight_snapshot = {
        "topics": [{"label": "Budget", "prominence": 0.9, "keywords": ["budget"]}],
        "actions": [],
        "decisions": [],
        "stale": False,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }

    await fresh_orchestrator.stop_session(db_path=db_path)

    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT snapshot_json FROM insight_snapshots WHERE session_id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()

    assert row is not None
    snap = json.loads(row["snapshot_json"])
    assert snap["topics"][0]["label"] == "Budget"


@pytest.mark.asyncio
async def test_stop_session_skips_empty_insight_snapshot(fresh_orchestrator, db_path):
    """An all-empty insight snapshot must NOT be written to the DB."""
    session_id = str(uuid.uuid4())
    await _insert_session(db_path, session_id)
    fresh_orchestrator._state = SessionState(session_id=session_id, status="active")
    # Default snapshot has empty topics/actions/decisions

    await fresh_orchestrator.stop_session(db_path=db_path)

    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM insight_snapshots WHERE session_id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()

    assert row["cnt"] == 0


@pytest.mark.asyncio
async def test_stop_session_idempotent_segments(fresh_orchestrator, db_path):
    """Calling _persist_session twice must not duplicate segments (INSERT OR IGNORE)."""
    session_id = str(uuid.uuid4())
    await _insert_session(db_path, session_id)
    fresh_orchestrator._state = SessionState(session_id=session_id, status="active")
    fresh_orchestrator._state.add_segment(TranscriptSegment("hello", 0.0, 1.0, False))

    await fresh_orchestrator._persist_session(db_path)
    await fresh_orchestrator._persist_session(db_path)

    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM transcript_segments WHERE session_id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()

    assert row["cnt"] == 1


# ---------------------------------------------------------------------------
# start_session: degraded-mode (audio unavailable)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_session_degraded_when_audio_unavailable(fresh_orchestrator):
    """If audio is unavailable, session starts in degraded mode (no pipeline tasks)."""
    with patch.object(
        fresh_orchestrator,
        "_check_audio_source",
        new=AsyncMock(),
    ) as mock_audio:

        async def _set_unavailable():
            fresh_orchestrator._state.source_status = "unavailable"

        mock_audio.side_effect = _set_unavailable

        with patch.object(fresh_orchestrator, "_warmup_stt", new=AsyncMock()):
            state = await fresh_orchestrator.start_session("s-degraded")

    assert state.status == "active"
    assert state.source_status == "unavailable"
    # No pipeline tasks created in degraded mode
    assert fresh_orchestrator._capture_task is None
    assert fresh_orchestrator._insight_task is None


@pytest.mark.asyncio
async def test_start_session_launches_pipeline_when_audio_available(fresh_orchestrator):
    """When audio is available, capture and insight tasks are created."""
    with patch.object(fresh_orchestrator, "_check_audio_source", new=AsyncMock()) as mock_audio:

        async def _set_capturing():
            fresh_orchestrator._state.source_status = "capturing"

        mock_audio.side_effect = _set_capturing

        with patch.object(fresh_orchestrator, "_warmup_stt", new=AsyncMock()):
            # Also mock the loops so they don't spin indefinitely
            with (
                patch.object(fresh_orchestrator, "_capture_loop", new=AsyncMock()),
                patch.object(fresh_orchestrator, "_insight_loop", new=AsyncMock()),
            ):
                state = await fresh_orchestrator.start_session("s-pipeline")
                # Brief yield to let tasks start
                import asyncio

                await asyncio.sleep(0)

    assert state.status == "active"
    assert fresh_orchestrator._capture_task is not None
    assert fresh_orchestrator._insight_task is not None

    # Cleanup
    await fresh_orchestrator.stop_session()


# ---------------------------------------------------------------------------
# regenerate-insights HTTP endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_regenerate_insights_returns_200_with_snapshot(tmp_path):
    """POST /sessions/{id}/regenerate-insights returns 200 with snapshot fields."""
    from ribbet.config import settings
    from ribbet.main import app

    settings.app_data_dir = tmp_path
    await init_db(settings.db_path)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a session with segments in the DB directly
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        async with get_db(settings.db_path) as db:
            await db.execute(
                "INSERT INTO sessions (id, started_at, status) VALUES (?, ?, ?)",
                (session_id, now, "stopped"),
            )
            for i in range(3):
                await db.execute(
                    """INSERT INTO transcript_segments
                       (id, session_id, text, start_time, end_time, is_partial, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (str(uuid.uuid4()), session_id, f"text {i}", float(i), float(i + 1), 0, now),
                )
            await db.commit()

        resp = await client.post(f"/sessions/{session_id}/regenerate-insights")

    assert resp.status_code == 200
    body = resp.json()
    assert "topics" in body
    assert "actions" in body
    assert "decisions" in body
    assert body["stale"] is False
    assert body["last_updated"] is not None


@pytest.mark.asyncio
async def test_regenerate_insights_404_for_unknown_session(tmp_path):
    """POST regenerate-insights on unknown session → 404."""
    from ribbet.config import settings
    from ribbet.main import app

    settings.app_data_dir = tmp_path
    await init_db(settings.db_path)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/sessions/does-not-exist/regenerate-insights")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_regenerate_insights_persists_snapshot_to_db(tmp_path):
    """regenerate-insights must write the new snapshot to insight_snapshots."""
    from ribbet.config import settings
    from ribbet.main import app

    settings.app_data_dir = tmp_path
    await init_db(settings.db_path)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        async with get_db(settings.db_path) as db:
            await db.execute(
                "INSERT INTO sessions (id, started_at, status) VALUES (?, ?, ?)",
                (session_id, now, "stopped"),
            )
            await db.commit()

        await client.post(f"/sessions/{session_id}/regenerate-insights")

    async with get_db(settings.db_path) as db:
        cursor = await db.execute(
            "SELECT snapshot_json FROM insight_snapshots WHERE session_id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()

    assert row is not None
    snap = json.loads(row["snapshot_json"])
    assert "topics" in snap


# ---------------------------------------------------------------------------
# Insight loop stale-snapshot fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insight_loop_marks_snapshot_stale_on_failure(fresh_orchestrator):
    """If the extractor raises during _insight_loop, snapshot.stale must become True."""
    session_id = str(uuid.uuid4())
    fresh_orchestrator._state = SessionState(session_id=session_id, status="active")
    # Plant a non-stale snapshot with content
    fresh_orchestrator._state.insight_snapshot = {
        "topics": [{"label": "Alpha", "prominence": 0.7, "keywords": []}],
        "actions": [],
        "decisions": [],
        "stale": False,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    fresh_orchestrator._state.add_segment(TranscriptSegment("some text", 0.0, 5.0, False))

    # Pre-wire the extractor on the orchestrator so the loop skips load()
    mock_extractor = MagicMock()
    mock_extractor.load = AsyncMock()
    mock_extractor.extract = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
    fresh_orchestrator._insight_extractor = mock_extractor

    # Patch sleep to tick once then cancel, and patch InsightExtractor so the
    # loop uses our pre-wired instance (it checks `if self._insight_extractor is None`)
    import asyncio

    call_count = 0

    async def _sleep_once(seconds):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise asyncio.CancelledError()

    with patch("ribbet.session.orchestrator.asyncio.sleep", side_effect=_sleep_once):
        # Patch the InsightExtractor import inside the function so the conditional
        # `if self._insight_extractor is None` skips re-creating it
        with patch(
            "ribbet.insights.extractor.InsightExtractor",
            return_value=mock_extractor,
        ):
            try:
                await fresh_orchestrator._insight_loop()
            except asyncio.CancelledError:
                pass

    assert fresh_orchestrator._state.insight_snapshot["stale"] is True
