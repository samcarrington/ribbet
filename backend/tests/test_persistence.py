"""Tests for transcript persistence and review."""

import pytest
from httpx import ASGITransport, AsyncClient
from ribbet.main import app
from ribbet.config import settings
from ribbet.db import init_db, get_db


@pytest.fixture(autouse=True)
async def _setup_test_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "app_data_dir", tmp_path)
    await init_db(settings.db_path)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def stopped_session_with_segments(client):
    """Create a session, add segments directly, then stop it."""
    import uuid
    from datetime import datetime, timezone

    resp = await client.post("/sessions")
    sid = resp.json()["session_id"]

    # Insert segments directly into DB
    async with get_db(settings.db_path) as db:
        for i in range(5):
            await db.execute(
                """INSERT INTO transcript_segments
                   (id, session_id, text, start_time, end_time, is_partial, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    sid,
                    f"Segment {i} text content",
                    float(i * 10),
                    float(i * 10 + 9),
                    0,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        await db.commit()

    await client.post(f"/sessions/{sid}/stop")
    return sid


@pytest.mark.asyncio
async def test_get_session_transcript(client, stopped_session_with_segments):
    sid = stopped_session_with_segments
    resp = await client.get(f"/sessions/{sid}/transcript")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["segments"]) == 5
    assert body["segments"][0]["start_time"] == 0.0


@pytest.mark.asyncio
async def test_get_session_transcript_nonexistent(client):
    resp = await client.get("/sessions/fake/transcript")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_session_transcript_returns_ordered_segments(
    client, stopped_session_with_segments
):
    """Segments must be returned in ascending start_time order."""
    sid = stopped_session_with_segments
    resp = await client.get(f"/sessions/{sid}/transcript")
    assert resp.status_code == 200
    segs = resp.json()["segments"]
    times = [s["start_time"] for s in segs]
    assert times == sorted(times)


@pytest.mark.asyncio
async def test_get_session_transcript_segment_fields(client, stopped_session_with_segments):
    """Each segment must have required fields."""
    sid = stopped_session_with_segments
    resp = await client.get(f"/sessions/{sid}/transcript")
    assert resp.status_code == 200
    seg = resp.json()["segments"][0]
    assert "id" in seg
    assert "text" in seg
    assert "start_time" in seg
    assert "end_time" in seg
    assert "is_partial" in seg
    assert seg["is_partial"] is False


@pytest.mark.asyncio
async def test_get_session_transcript_empty_session(client):
    """A session with no segments returns an empty list."""
    resp = await client.post("/sessions")
    sid = resp.json()["session_id"]
    tr = await client.get(f"/sessions/{sid}/transcript")
    assert tr.status_code == 200
    assert tr.json()["segments"] == []


@pytest.mark.asyncio
async def test_get_session_transcript_includes_session_id(client, stopped_session_with_segments):
    """Response body includes the session_id for cross-reference."""
    sid = stopped_session_with_segments
    resp = await client.get(f"/sessions/{sid}/transcript")
    assert resp.json()["session_id"] == sid


@pytest.mark.asyncio
async def test_regenerate_insights_endpoint_exists(client, stopped_session_with_segments):
    sid = stopped_session_with_segments
    resp = await client.post(f"/sessions/{sid}/regenerate-insights")
    # May return 200 or 202 depending on implementation; 501 while not yet wired
    assert resp.status_code in (200, 202, 501)


@pytest.mark.asyncio
async def test_regenerate_insights_nonexistent_session(client):
    resp = await client.post("/sessions/nonexistent/regenerate-insights")
    assert resp.status_code == 404
