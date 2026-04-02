"""Tests for session REST endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from ribbet.main import app


@pytest.fixture(autouse=True)
async def _setup_test_db(tmp_path, monkeypatch):
    """Point the app at a temp database for each test."""
    from ribbet.config import settings

    monkeypatch.setattr(settings, "app_data_dir", tmp_path)
    from ribbet.db import init_db

    await init_db(settings.db_path)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


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
