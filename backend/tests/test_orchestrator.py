"""Tests for the session orchestrator."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ribbet.session.orchestrator import SessionOrchestrator, SessionState
from ribbet.transcription.engine import TranscriptSegment


# ---------------------------------------------------------------------------
# SessionState unit tests
# ---------------------------------------------------------------------------


def test_session_state_initial():
    state = SessionState(session_id="s1")
    assert state.status == "idle"
    assert state.source_status == "unknown"
    assert state.model_status == "cold"
    assert len(state.segments) == 0


def test_session_state_add_segment():
    state = SessionState(session_id="s1")
    seg = TranscriptSegment("hello", 0.0, 1.0, False)
    state.add_segment(seg)
    assert len(state.segments) == 1
    assert state.segments[0].text == "hello"


def test_session_state_get_snippet():
    state = SessionState(session_id="s1")
    for i in range(10):
        state.add_segment(TranscriptSegment(f"word{i}", float(i), float(i + 1), False))

    snippet = state.get_snippet_around(5.0, window_seconds=2)
    assert "word4" in snippet or "word5" in snippet
    assert "word0" not in snippet


def test_session_state_get_snippet_empty():
    """get_snippet_around on empty state returns empty string."""
    state = SessionState(session_id="s1")
    assert state.get_snippet_around(5.0) == ""


def test_session_state_get_snippet_clamps_at_zero():
    """Negative start time is clamped to 0 — no ValueError from text_window."""
    state = SessionState(session_id="s1")
    state.add_segment(TranscriptSegment("word0", 0.0, 1.0, False))
    # timestamp=0.5, half-window=5 → start would be -4.5 without clamping
    snippet = state.get_snippet_around(0.5, window_seconds=10)
    assert "word0" in snippet


def test_session_state_insight_snapshot_default():
    state = SessionState(session_id="s1")
    assert state.insight_snapshot["topics"] == []
    assert state.insight_snapshot["stale"] is True
    assert state.insight_snapshot["last_updated"] is None


# ---------------------------------------------------------------------------
# SessionOrchestrator unit tests (with mock WS clients)
# ---------------------------------------------------------------------------


@pytest.fixture
def orchestrator():
    """Fresh orchestrator per test — avoids global singleton pollution."""
    return SessionOrchestrator()


@pytest.fixture
def mock_ws():
    ws = MagicMock()
    ws.send_json = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_start_session_returns_state(orchestrator):
    """start_session reaches 'active'; audio/STT probes are mocked for CI."""
    with (
        patch.object(orchestrator, "_check_audio_source", new=AsyncMock()) as mock_audio,
        patch.object(orchestrator, "_warmup_stt", new=AsyncMock()),
    ):
        # Simulate successful audio probe outcome
        async def _set_capturing():
            orchestrator._state.source_status = "capturing"

        mock_audio.side_effect = _set_capturing
        state = await orchestrator.start_session("sess-001")

    assert state.status == "active"
    assert state.session_id == "sess-001"
    assert state.source_status == "capturing"


@pytest.mark.asyncio
async def test_start_session_raises_if_already_active(orchestrator):
    await orchestrator.start_session("sess-001")
    with pytest.raises(RuntimeError, match="already active"):
        await orchestrator.start_session("sess-002")


@pytest.mark.asyncio
async def test_stop_session_sets_stopped(orchestrator):
    await orchestrator.start_session("sess-001")
    await orchestrator.stop_session()
    assert orchestrator.active_session is not None
    assert orchestrator.active_session.status == "stopped"


@pytest.mark.asyncio
async def test_stop_session_noop_when_none(orchestrator):
    """Calling stop when no session is running should not raise."""
    await orchestrator.stop_session()  # should not raise


@pytest.mark.asyncio
async def test_broadcast_reaches_registered_clients(orchestrator, mock_ws):
    orchestrator.register_ws(mock_ws)
    await orchestrator.broadcast({"type": "status", "session": "active"})
    mock_ws.send_json.assert_awaited_once_with({"type": "status", "session": "active"})


@pytest.mark.asyncio
async def test_broadcast_removes_dead_clients(orchestrator, mock_ws):
    """A client that throws on send_json is automatically pruned."""
    mock_ws.send_json.side_effect = Exception("connection closed")
    orchestrator.register_ws(mock_ws)
    await orchestrator.broadcast({"type": "ping"})
    assert mock_ws not in orchestrator._ws_clients


@pytest.mark.asyncio
async def test_unregister_ws(orchestrator, mock_ws):
    orchestrator.register_ws(mock_ws)
    orchestrator.unregister_ws(mock_ws)
    assert mock_ws not in orchestrator._ws_clients


@pytest.mark.asyncio
async def test_unregister_unknown_ws_is_noop(orchestrator, mock_ws):
    """Unregistering a client that was never registered should not raise."""
    orchestrator.unregister_ws(mock_ws)  # should not raise


@pytest.mark.asyncio
async def test_handle_new_segment_broadcasts_and_stores(orchestrator, mock_ws):
    orchestrator.register_ws(mock_ws)
    await orchestrator.start_session("sess-001")
    mock_ws.send_json.reset_mock()

    seg = TranscriptSegment("hello world", 1.0, 2.0, False)
    await orchestrator.handle_new_segment(seg)

    assert len(orchestrator.active_session.segments) == 1
    call_args = mock_ws.send_json.call_args[0][0]
    assert call_args["type"] == "transcript"
    assert call_args["segment"]["text"] == "hello world"
    assert call_args["segment"]["is_partial"] is False


@pytest.mark.asyncio
async def test_handle_new_segment_noop_when_no_session(orchestrator, mock_ws):
    orchestrator.register_ws(mock_ws)
    seg = TranscriptSegment("orphan", 0.0, 1.0, False)
    await orchestrator.handle_new_segment(seg)  # should not raise
    mock_ws.send_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_insights_broadcasts_and_stores(orchestrator, mock_ws):
    orchestrator.register_ws(mock_ws)
    await orchestrator.start_session("sess-001")
    mock_ws.send_json.reset_mock()

    snapshot = {
        "topics": [{"label": "Budget", "prominence": 0.8, "keywords": ["budget"]}],
        "actions": [],
        "decisions": [],
        "stale": False,
        "last_updated": "2026-04-02T10:00:00",
    }
    await orchestrator.update_insights(snapshot)

    assert orchestrator.active_session.insight_snapshot == snapshot
    call_args = mock_ws.send_json.call_args[0][0]
    assert call_args["type"] == "insights"
    assert call_args["snapshot"]["topics"][0]["label"] == "Budget"


@pytest.mark.asyncio
async def test_update_insights_noop_when_no_session(orchestrator):
    await orchestrator.update_insights({"topics": [], "actions": [], "decisions": []})


def test_create_bookmark_during_active_session(orchestrator):
    """create_bookmark is sync — set up state directly to avoid async start."""
    from ribbet.session.orchestrator import SessionState

    orchestrator._state = SessionState(session_id="s1", status="active")
    orchestrator._state.add_segment(TranscriptSegment("decision made", 10.0, 11.0, False))

    bookmark = orchestrator.create_bookmark("Important decision")
    assert bookmark is not None
    assert bookmark["note"] == "Important decision"
    assert bookmark["timestamp"] == 11.0
    assert "decision made" in bookmark["snippet"]
    assert len(orchestrator._state.bookmarks) == 1


def test_create_bookmark_returns_none_when_no_session(orchestrator):
    result = orchestrator.create_bookmark("note")
    assert result is None


def test_create_bookmark_returns_none_when_stopped(orchestrator):
    from ribbet.session.orchestrator import SessionState

    orchestrator._state = SessionState(session_id="s1", status="stopped")
    result = orchestrator.create_bookmark("note")
    assert result is None


def test_create_bookmark_timestamp_zero_when_no_segments(orchestrator):
    from ribbet.session.orchestrator import SessionState

    orchestrator._state = SessionState(session_id="s1", status="active")
    bookmark = orchestrator.create_bookmark("empty session mark")
    assert bookmark is not None
    assert bookmark["timestamp"] == 0.0
    assert bookmark["snippet"] == ""


@pytest.mark.asyncio
async def test_start_broadcasts_status_messages(orchestrator, mock_ws):
    orchestrator.register_ws(mock_ws)
    await orchestrator.start_session("sess-001")

    calls = [c[0][0] for c in mock_ws.send_json.call_args_list]
    types = [c["type"] for c in calls]
    assert types.count("status") >= 2  # "starting" and "active"

    statuses = [c["session"] for c in calls if c["type"] == "status"]
    assert "starting" in statuses
    assert "active" in statuses


@pytest.mark.asyncio
async def test_stop_broadcasts_stopping_then_stopped(orchestrator, mock_ws):
    orchestrator.register_ws(mock_ws)
    await orchestrator.start_session("sess-001")
    mock_ws.send_json.reset_mock()

    await orchestrator.stop_session()

    calls = [c[0][0] for c in mock_ws.send_json.call_args_list]
    statuses = [c["session"] for c in calls if c["type"] == "status"]
    assert "stopping" in statuses
    assert "stopped" in statuses
