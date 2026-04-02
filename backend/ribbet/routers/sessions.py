"""Session CRUD REST endpoints."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ribbet.config import settings
from ribbet.db import get_db

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


@router.get("")
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


@router.get("/{session_id}")
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
        cursor = await db.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Session not found")
        await db.execute(
            "UPDATE sessions SET status = 'stopped', ended_at = ? WHERE id = ?",
            (now, session_id),
        )
        await db.commit()
    return {"status": "stopped"}
