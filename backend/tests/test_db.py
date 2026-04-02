"""Tests for database initialization and access."""

import pytest
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
