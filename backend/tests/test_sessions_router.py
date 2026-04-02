"""Tests for session REST endpoints."""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_create_session(client):
    resp = await client.post("/sessions")
    assert resp.status_code == 201
    body = resp.json()
    assert "session_id" in body
    assert len(body["session_id"]) > 0


@pytest.mark.asyncio
async def test_list_sessions_empty(client):
    resp = await client.get("/sessions")
    assert resp.status_code == 200
    assert resp.json()["sessions"] == []


@pytest.mark.asyncio
async def test_list_sessions_after_create(client):
    await client.post("/sessions")
    resp = await client.get("/sessions")
    sessions = resp.json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["status"] == "active"


@pytest.mark.asyncio
async def test_stop_session(client):
    create_resp = await client.post("/sessions")
    sid = create_resp.json()["session_id"]
    stop_resp = await client.post(f"/sessions/{sid}/stop")
    assert stop_resp.status_code == 200
    # Verify it's stopped
    list_resp = await client.get("/sessions")
    sessions = list_resp.json()["sessions"]
    assert sessions[0]["status"] == "stopped"
    assert sessions[0]["ended_at"] is not None


@pytest.mark.asyncio
async def test_stop_nonexistent_session(client):
    resp = await client.post("/sessions/nonexistent/stop")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_session_detail(client):
    create_resp = await client.post("/sessions")
    sid = create_resp.json()["session_id"]
    resp = await client.get(f"/sessions/{sid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == sid
    assert body["segment_count"] == 0


@pytest.mark.asyncio
async def test_stop_already_stopped_session_returns_409(client):
    """Stopping an already-stopped session must not overwrite ended_at and returns 409."""
    create_resp = await client.post("/sessions")
    sid = create_resp.json()["session_id"]

    # First stop — should succeed
    first_stop = await client.post(f"/sessions/{sid}/stop")
    assert first_stop.status_code == 200

    # Capture ended_at after first stop
    detail_after_first = await client.get(f"/sessions/{sid}")
    ended_at_first = detail_after_first.json()["ended_at"]
    assert ended_at_first is not None

    # Second stop — must return 409, not re-update ended_at
    second_stop = await client.post(f"/sessions/{sid}/stop")
    assert second_stop.status_code == 409

    # ended_at must be unchanged
    detail_after_second = await client.get(f"/sessions/{sid}")
    assert detail_after_second.json()["ended_at"] == ended_at_first


@pytest.mark.asyncio
async def test_list_sessions_response_shape(client):
    """Verify list endpoint returns expected response_model fields."""
    await client.post("/sessions")
    resp = await client.get("/sessions")
    assert resp.status_code == 200
    session = resp.json()["sessions"][0]
    for field in ("id", "started_at", "ended_at", "status", "segment_count"):
        assert field in session, f"Missing field: {field}"


@pytest.mark.asyncio
async def test_get_session_response_shape(client):
    """Verify single session GET returns expected response_model fields."""
    create_resp = await client.post("/sessions")
    sid = create_resp.json()["session_id"]
    resp = await client.get(f"/sessions/{sid}")
    assert resp.status_code == 200
    body = resp.json()
    for field in ("id", "started_at", "ended_at", "status", "segment_count"):
        assert field in body, f"Missing field: {field}"


@pytest.mark.asyncio
async def test_create_session_orchestrator_failure_leaves_no_orphan(client):
    """When orchestrator.start_session raises, the DB row must NOT remain active.

    The row should be updated to status='error' with a non-null ended_at so
    there is no orphan active session in the database.
    """
    from ribbet.session.orchestrator import orchestrator

    with patch.object(
        orchestrator,
        "start_session",
        new=AsyncMock(side_effect=RuntimeError("pipeline boom")),
    ):
        resp = await client.post("/sessions")

    # Endpoint must return 500
    assert resp.status_code == 500

    # The list of sessions should contain the row, but NOT in active status
    list_resp = await client.get("/sessions")
    sessions = list_resp.json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["status"] == "error", (
        f"Expected status='error', got {sessions[0]['status']!r} — orphan active row!"
    )
    assert sessions[0]["ended_at"] is not None, "ended_at must be set on errored session"
