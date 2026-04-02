"""Tests for WebSocket session stream handler — ws/session_stream.py.

Focuses on Task 7 quality fix: unregister_ws must be called on both
WebSocketDisconnect *and* arbitrary exceptions (finally-block cleanup).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocketDisconnect

from ribbet.ws.session_stream import session_websocket


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ws(receive_side_effect):
    """Return a mock WebSocket whose receive_text raises the given exception."""
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_text = AsyncMock(side_effect=receive_side_effect)
    return ws


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unregister_on_websocket_disconnect():
    """unregister_ws is called when the client disconnects normally."""
    ws = _make_ws(WebSocketDisconnect(code=1000))

    with patch("ribbet.ws.session_stream.orchestrator") as mock_orch:
        mock_orch.active_session = None
        await session_websocket(ws)

    mock_orch.unregister_ws.assert_called_once_with(ws)


@pytest.mark.asyncio
async def test_unregister_on_unexpected_exception():
    """unregister_ws is called even when receive_text raises a non-disconnect error."""
    ws = _make_ws(RuntimeError("unexpected network failure"))

    with patch("ribbet.ws.session_stream.orchestrator") as mock_orch:
        mock_orch.active_session = None
        with pytest.raises(RuntimeError, match="unexpected network failure"):
            await session_websocket(ws)

    mock_orch.unregister_ws.assert_called_once_with(ws)


@pytest.mark.asyncio
async def test_register_called_on_connect():
    """register_ws is called immediately after accept."""
    ws = _make_ws(WebSocketDisconnect(code=1000))

    with patch("ribbet.ws.session_stream.orchestrator") as mock_orch:
        mock_orch.active_session = None
        await session_websocket(ws)

    mock_orch.register_ws.assert_called_once_with(ws)


@pytest.mark.asyncio
async def test_initial_idle_status_sent_when_no_session():
    """When there is no active session, a status=idle message is sent on connect."""
    ws = _make_ws(WebSocketDisconnect(code=1000))

    with patch("ribbet.ws.session_stream.orchestrator") as mock_orch:
        mock_orch.active_session = None
        await session_websocket(ws)

    sent = ws.send_json.call_args_list
    assert len(sent) == 1
    msg = sent[0][0][0]
    assert msg["type"] == "status"
    assert msg["session"] == "idle"


@pytest.mark.asyncio
async def test_state_replay_sent_when_active_session():
    """With an active session, status + segments + insights are replayed."""
    ws = _make_ws(WebSocketDisconnect(code=1000))

    seg = MagicMock()
    seg.id = "seg-1"
    seg.text = "hello"
    seg.start_time = 0.0
    seg.end_time = 1.0
    seg.is_partial = False

    state = MagicMock()
    state.status = "active"
    state.source_status = "capturing"
    state.model_status = "ready"
    state.segments = [seg]
    state.insight_snapshot = {"topics": [], "actions": [], "decisions": [], "stale": True}

    with patch("ribbet.ws.session_stream.orchestrator") as mock_orch:
        mock_orch.active_session = state
        await session_websocket(ws)

    messages = [call[0][0] for call in ws.send_json.call_args_list]
    types = [m["type"] for m in messages]
    assert "status" in types
    assert "transcript" in types
    assert "insights" in types
