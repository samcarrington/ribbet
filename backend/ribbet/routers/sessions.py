"""Session CRUD REST endpoints."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ribbet.config import settings
from ribbet.db import get_db
from ribbet.models import SessionListOut, SessionOut

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", status_code=201)
async def create_session():
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    async with get_db(settings.db_path) as db:
        await db.execute(
            "INSERT INTO sessions (id, started_at, status) VALUES (?, ?, ?)",
            (session_id, now, "active"),
        )
        await db.commit()
    return {"session_id": session_id}


@router.get("", response_model=SessionListOut)
async def list_sessions():
    async with get_db(settings.db_path) as db:
        cursor = await db.execute(
            """SELECT s.id, s.started_at, s.ended_at, s.status,
                      (SELECT COUNT(*) FROM transcript_segments WHERE session_id = s.id) as segment_count
               FROM sessions s ORDER BY s.started_at DESC"""
        )
        rows = await cursor.fetchall()
    sessions = [
        {
            "id": r["id"],
            "started_at": r["started_at"],
            "ended_at": r["ended_at"],
            "status": r["status"],
            "segment_count": r["segment_count"],
        }
        for r in rows
    ]
    return {"sessions": sessions}


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(session_id: str):
    async with get_db(settings.db_path) as db:
        cursor = await db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        seg_cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM transcript_segments WHERE session_id = ?",
            (session_id,),
        )
        seg_row = await seg_cursor.fetchone()
    return {
        "id": row["id"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
        "status": row["status"],
        "segment_count": seg_row["cnt"],
    }


@router.post("/{session_id}/stop")
async def stop_session(session_id: str):
    now = datetime.now(timezone.utc).isoformat()
    async with get_db(settings.db_path) as db:
        cursor = await db.execute("SELECT id, status FROM sessions WHERE id = ?", (session_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        if row["status"] == "stopped":
            raise HTTPException(
                status_code=409,
                detail="Session is already stopped",
            )
        await db.execute(
            "UPDATE sessions SET status = 'stopped', ended_at = ? WHERE id = ?",
            (now, session_id),
        )
        await db.commit()
    return {"status": "stopped"}


@router.get("/{session_id}/transcript")
async def get_transcript(session_id: str):
    async with get_db(settings.db_path) as db:
        cursor = await db.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Session not found")

        seg_cursor = await db.execute(
            """SELECT id, text, start_time, end_time, is_partial
               FROM transcript_segments
               WHERE session_id = ?
               ORDER BY start_time""",
            (session_id,),
        )
        rows = await seg_cursor.fetchall()

    return {
        "session_id": session_id,
        "segments": [
            {
                "id": r["id"],
                "text": r["text"],
                "start_time": r["start_time"],
                "end_time": r["end_time"],
                "is_partial": bool(r["is_partial"]),
            }
            for r in rows
        ],
    }


@router.post("/{session_id}/regenerate-insights")
async def regenerate_insights(session_id: str):
    async with get_db(settings.db_path) as db:
        cursor = await db.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Session not found")

    # Implementation note for the engineer:
    # 1. Load full transcript from DB
    # 2. Run insight extractor on the full text
    # 3. Save new insight snapshot to insight_snapshots table
    # 4. Return the new snapshot
    #
    # For now, return 501 until the insight extractor is fully wired (Task 12):
    raise HTTPException(
        status_code=501,
        detail="Insight regeneration not yet implemented. Wire InsightExtractor here.",
    )
