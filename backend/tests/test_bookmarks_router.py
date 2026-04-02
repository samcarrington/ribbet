"""Tests for bookmark REST endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from ribbet.main import app


@pytest.fixture(autouse=True)
async def _setup_test_db(tmp_path, monkeypatch):
    from ribbet.config import settings

    monkeypatch.setattr(settings, "app_data_dir", tmp_path)
    from ribbet.db import init_db

    await init_db(settings.db_path)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def session_id(client):
    resp = await client.post("/sessions")
    return resp.json()["session_id"]


@pytest.mark.asyncio
async def test_create_bookmark(client, session_id):
    resp = await client.post(
        f"/sessions/{session_id}/bookmarks",
        json={"note": "Important discussion about Q3"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["note"] == "Important discussion about Q3"
    assert "id" in body
    assert "timestamp" in body
    assert "snippet" in body
    assert "created_at" in body


@pytest.mark.asyncio
async def test_list_bookmarks(client, session_id):
    await client.post(
        f"/sessions/{session_id}/bookmarks",
        json={"note": "Bookmark 1"},
    )
    await client.post(
        f"/sessions/{session_id}/bookmarks",
        json={"note": "Bookmark 2"},
    )
    resp = await client.get(f"/sessions/{session_id}/bookmarks")
    assert resp.status_code == 200
    bookmarks = resp.json()["bookmarks"]
    assert len(bookmarks) == 2


@pytest.mark.asyncio
async def test_create_bookmark_nonexistent_session(client):
    resp = await client.post(
        "/sessions/nonexistent/bookmarks",
        json={"note": "test"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_bookmark_timestamp_zero_when_no_segments(client, session_id):
    """Bookmark timestamp is 0.0 when session has no transcript segments."""
    resp = await client.post(
        f"/sessions/{session_id}/bookmarks",
        json={"note": "Early bookmark"},
    )
    assert resp.status_code == 201
    assert resp.json()["timestamp"] == 0.0


@pytest.mark.asyncio
async def test_bookmark_snippet_from_transcript(client, session_id):
    """Snippet is built from nearby transcript segments."""
    import uuid
    from datetime import datetime, timezone
    from ribbet.config import settings
    from ribbet.db import get_db

    # Insert segments into DB directly
    async with get_db(settings.db_path) as db:
        for i in range(3):
            await db.execute(
                """INSERT INTO transcript_segments
                   (id, session_id, text, start_time, end_time, is_partial, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    session_id,
                    f"word{i}",
                    float(i * 5),
                    float(i * 5 + 4),
                    0,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        await db.commit()

    resp = await client.post(
        f"/sessions/{session_id}/bookmarks",
        json={"note": "With snippet"},
    )
    assert resp.status_code == 201
    body = resp.json()
    # snippet should contain some of the inserted text
    assert len(body["snippet"]) > 0


@pytest.mark.asyncio
async def test_list_bookmarks_empty(client, session_id):
    """Empty bookmark list for a session with no bookmarks."""
    resp = await client.get(f"/sessions/{session_id}/bookmarks")
    assert resp.status_code == 200
    assert resp.json()["bookmarks"] == []


@pytest.mark.asyncio
async def test_list_bookmarks_ordered_by_timestamp(client, session_id):
    """Bookmarks are returned ordered by timestamp ascending."""
    for note in ["Third", "First", "Second"]:
        await client.post(
            f"/sessions/{session_id}/bookmarks",
            json={"note": note},
        )
    resp = await client.get(f"/sessions/{session_id}/bookmarks")
    bookmarks = resp.json()["bookmarks"]
    assert len(bookmarks) == 3
    timestamps = [b["timestamp"] for b in bookmarks]
    assert timestamps == sorted(timestamps)
