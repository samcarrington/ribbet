"""WebSocket handler for live session streaming."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ribbet.session.orchestrator import orchestrator

router = APIRouter()


@router.websocket("/ws/session")
async def session_websocket(websocket: WebSocket):
    await websocket.accept()
    orchestrator.register_ws(websocket)

    # Send current state on connect
    state = orchestrator.active_session
    if state:
        await websocket.send_json(
            {
                "type": "status",
                "session": state.status,
                "source": state.source_status,
                "model": state.model_status,
            }
        )
        # Replay existing segments so a reconnecting client catches up
        for seg in state.segments:
            await websocket.send_json(
                {
                    "type": "transcript",
                    "segment": {
                        "id": seg.id,
                        "text": seg.text,
                        "start_time": seg.start_time,
                        "end_time": seg.end_time,
                        "is_partial": seg.is_partial,
                    },
                }
            )
        # Send current insight snapshot
        await websocket.send_json(
            {
                "type": "insights",
                "snapshot": state.insight_snapshot,
            }
        )
    else:
        await websocket.send_json(
            {
                "type": "status",
                "session": "idle",
                "source": "unknown",
                "model": "cold",
            }
        )

    try:
        while True:
            # Keep the connection alive; client may send keepalive pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        orchestrator.unregister_ws(websocket)
