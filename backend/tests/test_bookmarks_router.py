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
async def test_bookmark_snippet_includes_long_segment_starting_before_window(client, session_id):
    """A segment that starts before the window but ends inside it must be included.

    Regression test for the original bug where the query used
    ``start_time >= window_start`` which excluded long segments that begin
    before the window.  The correct overlap condition is
    ``start_time < window_end AND end_time > window_start``.
    """
    import uuid
    from datetime import datetime, timezone
    from ribbet.config import settings
    from ribbet.db import get_db

    # bookmark_snippet_seconds = 30 → window is [ts-15, ts+15]
    # Segment spans 0–50 s; it starts before ts-15 but ends after ts+15,
    # so it fully overlaps the window and MUST be included in the snippet.
    async with get_db(settings.db_path) as db:
        await db.execute(
            """INSERT INTO transcript_segments
               (id, session_id, text, start_time, end_time, is_partial, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                session_id,
                "long segment text",
                0.0,  # starts well before window_start
                50.0,  # ends well after window_end → overlaps whole window
                0,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        await db.commit()

    resp = await client.post(
        f"/sessions/{session_id}/bookmarks",
        json={"note": "Overlap test"},
    )
    assert resp.status_code == 201
    body = resp.json()
    # The long segment's text must appear in the snippet
    assert "long segment text" in body["snippet"], (
        f"Expected long segment in snippet, got: {body['snippet']!r}"
    )


@pytest.mark.asyncio
async def test_list_bookmarks_empty(client, session_id):
    """Empty bookmark list for a session with no bookmarks."""
    resp = await client.get(f"/sessions/{session_id}/bookmarks")
    assert resp.status_code == 200
    assert resp.json()["bookmarks"] == []


@pytest.mark.asyncio
async def test_list_bookmarks_ordered_by_timestamp(client, session_id):
    """Bookmarks are returned ordered by timestamp ascending (non-vacuous).

    We insert transcript segments with strictly increasing end_times before
    each bookmark so that each bookmark receives a distinct timestamp.  The
    ordering assertion is therefore meaningful rather than trivially true over
    equal values.
    """
    import uuid
    from datetime import datetime, timezone
    from ribbet.config import settings
    from ribbet.db import get_db

    # Insert one segment per bookmark, advancing end_time each time, so each
    # CREATE BOOKMARK call sees a different MAX(end_time).
    end_times = [10.0, 25.0, 40.0]
    notes = ["First", "Second", "Third"]
    for end_t, note in zip(end_times, notes):
        async with get_db(settings.db_path) as db:
            await db.execute(
                """INSERT INTO transcript_segments
                   (id, session_id, text, start_time, end_time, is_partial, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    session_id,
                    note,
                    end_t - 5.0,
                    end_t,
                    0,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()
        await client.post(
            f"/sessions/{session_id}/bookmarks",
            json={"note": note},
        )

    resp = await client.get(f"/sessions/{session_id}/bookmarks")
    bookmarks = resp.json()["bookmarks"]
    assert len(bookmarks) == 3
    timestamps = [b["timestamp"] for b in bookmarks]
    # All timestamps must be distinct (non-vacuous ordering test)
    assert len(set(timestamps)) == 3, f"Expected 3 distinct timestamps, got {timestamps}"
    assert timestamps == sorted(timestamps)


@pytest.mark.asyncio
async def test_list_bookmarks_nonexistent_session(client):
    """list_bookmarks for an unknown session returns 200 with an empty list.

    The chosen contract is to return an empty collection rather than 404,
    because the list endpoint is idempotent and a missing session is
    indistinguishable from a session with no bookmarks from a read perspective.
    If the contract changes to 404, update this test accordingly.
    """
    resp = await client.get("/sessions/does-not-exist/bookmarks")
    assert resp.status_code == 200
    assert resp.json()["bookmarks"] == []
