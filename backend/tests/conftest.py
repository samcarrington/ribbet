"""Shared test fixtures."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from ribbet.main import app


@pytest.fixture(autouse=True)
async def _setup_test_db(tmp_path, monkeypatch):
    """Point the app at a temp database for each test, ensuring full DB isolation."""
    from ribbet.config import settings

    monkeypatch.setattr(settings, "app_data_dir", tmp_path)
    from ribbet.db import init_db

    await init_db(settings.db_path)


@pytest.fixture(autouse=True)
async def _reset_orchestrator():
    """Reset the global orchestrator singleton between tests.

    HTTP-layer tests (router, persistence) only need the DB side — they should
    not exercise the real audio/STT pipeline. Mock start/stop so the singleton
    stays clean and tests remain isolated.
    """
    from ribbet.session.orchestrator import orchestrator

    # Reset any lingering state from prior tests
    orchestrator._state = None
    orchestrator._capture_task = None
    orchestrator._insight_task = None
    orchestrator._capture = None
    orchestrator._stt_engine = None
    orchestrator._insight_extractor = None
    orchestrator._ws_clients = []

    # Stub out the real pipeline so HTTP-layer tests don't touch hardware
    with (
        patch.object(orchestrator, "start_session", new=AsyncMock()) as mock_start,
        patch.object(orchestrator, "stop_session", new=AsyncMock()),
    ):
        # Make start_session return a plausible state so callers don't crash
        from ribbet.session.orchestrator import SessionState

        async def _fake_start(session_id: str):
            orchestrator._state = SessionState(session_id=session_id, status="active")
            return orchestrator._state

        mock_start.side_effect = _fake_start

        yield

    # Ensure clean state after each test regardless of pass/fail
    orchestrator._state = None


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
