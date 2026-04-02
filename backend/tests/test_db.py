"""Tests for database initialization and access."""

import pytest
import aiosqlite
from pathlib import Path
from ribbet.db import init_db, get_db


@pytest.fixture
async def db_path(tmp_path):
    path = tmp_path / "test.db"
    await init_db(path)
    return path


@pytest.mark.asyncio
async def test_init_db_creates_tables(db_path):
    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in await cursor.fetchall()]
    assert "sessions" in tables
    assert "transcript_segments" in tables
    assert "bookmarks" in tables
    assert "insight_snapshots" in tables


@pytest.mark.asyncio
async def test_init_db_is_idempotent(db_path):
    # calling init_db again should not raise
    await init_db(db_path)


@pytest.mark.asyncio
async def test_foreign_keys_enforced_on_get_db(db_path):
    """Inserting a child row referencing a non-existent session must raise IntegrityError."""
    import uuid
    from datetime import datetime, timezone

    async with get_db(db_path) as db:
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                "INSERT INTO transcript_segments "
                "(id, session_id, text, start_time, end_time, is_partial, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    "nonexistent-session-id",  # parent does not exist
                    "Hello",
                    0.0,
                    1.0,
                    0,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()


@pytest.mark.asyncio
async def test_foreign_keys_enforced_for_bookmarks(db_path):
    """Inserting a bookmark with a missing session_id must raise IntegrityError."""
    import uuid
    from datetime import datetime, timezone

    async with get_db(db_path) as db:
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                "INSERT INTO bookmarks "
                "(id, session_id, timestamp, note, snippet, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    "nonexistent-session-id",
                    42.0,
                    "Test note",
                    "Test snippet",
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()


@pytest.mark.asyncio
async def test_foreign_keys_enforced_for_insight_snapshots(db_path):
    """Inserting an insight_snapshot with a missing session_id must raise IntegrityError."""
    import uuid
    import json
    from datetime import datetime, timezone

    async with get_db(db_path) as db:
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                "INSERT INTO insight_snapshots "
                "(id, session_id, snapshot_json, created_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    "nonexistent-session-id",
                    json.dumps({}),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()


@pytest.mark.asyncio
async def test_valid_child_insert_succeeds(db_path):
    """A child row with a valid parent session_id must insert without error."""
    import uuid
    from datetime import datetime, timezone

    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO sessions (id, started_at, status) VALUES (?, ?, ?)",
            (session_id, now, "active"),
        )
        await db.execute(
            "INSERT INTO transcript_segments "
            "(id, session_id, text, start_time, end_time, is_partial, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), session_id, "Valid segment", 0.0, 1.0, 0, now),
        )
        await db.commit()

    # Verify the segment was actually stored
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT count(*) FROM transcript_segments WHERE session_id = ?", (session_id,)
        )
        row = await cursor.fetchone()
    assert row[0] == 1
