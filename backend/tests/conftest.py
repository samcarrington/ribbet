"""Shared test fixtures."""

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


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
