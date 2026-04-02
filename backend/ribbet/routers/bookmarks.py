"""Bookmark REST endpoints."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ribbet.config import settings
from ribbet.db import get_db
from ribbet.models import BookmarkCreate

router = APIRouter(tags=["bookmarks"])


@router.post("/sessions/{session_id}/bookmarks", status_code=201)
async def create_bookmark(session_id: str, body: BookmarkCreate):
    async with get_db(settings.db_path) as db:
        cursor = await db.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Session not found")

        bookmark_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Get latest transcript timestamp for the bookmark
        seg_cursor = await db.execute(
            "SELECT MAX(end_time) as ts FROM transcript_segments WHERE session_id = ?",
            (session_id,),
        )
        seg_row = await seg_cursor.fetchone()
        timestamp = seg_row["ts"] if seg_row and seg_row["ts"] is not None else 0.0

        # Build snippet from nearby transcript segments
        window_start = max(0, timestamp - settings.bookmark_snippet_seconds / 2)
        window_end = timestamp + settings.bookmark_snippet_seconds / 2
        snippet_cursor = await db.execute(
            """SELECT text FROM transcript_segments
               WHERE session_id = ? AND start_time >= ? AND start_time < ?
               ORDER BY start_time""",
            (session_id, window_start, window_end),
        )
        snippet_rows = await snippet_cursor.fetchall()
        snippet = " ".join(r["text"] for r in snippet_rows) if snippet_rows else ""

        await db.execute(
            """INSERT INTO bookmarks (id, session_id, timestamp, note, snippet, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (bookmark_id, session_id, timestamp, body.note, snippet, now),
        )
        await db.commit()

    return {
        "id": bookmark_id,
        "timestamp": timestamp,
        "note": body.note,
        "snippet": snippet,
        "created_at": now,
    }


@router.get("/sessions/{session_id}/bookmarks")
async def list_bookmarks(session_id: str):
    async with get_db(settings.db_path) as db:
        cursor = await db.execute(
            """SELECT id, timestamp, note, snippet, created_at
               FROM bookmarks WHERE session_id = ? ORDER BY timestamp""",
            (session_id,),
        )
        rows = await cursor.fetchall()
    return {
        "bookmarks": [
            {
                "id": r["id"],
                "timestamp": r["timestamp"],
                "note": r["note"],
                "snippet": r["snippet"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    }
