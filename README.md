# Ribbet — Local Meeting Transcription App

A macOS desktop application for real-time meeting transcription and insight extraction, running entirely on-device using Apple Silicon ML acceleration.

## Features

- **Real-time transcription** via [Moshi STT](https://github.com/kyutai-labs/moshi) (streaming, ~100 ms latency on M-series)
- **Automatic insight extraction** — topics, action items, and decisions surfaced every 30 s using a local Qwen 2.5 3B model
- **Bookmarks** — drop a timestamped note mid-meeting; snippet context is saved automatically
- **Session review** — browse past sessions, full transcripts, and regenerate insights on demand
- **Fully local** — no audio, transcript, or insight data ever leaves the device

## Architecture

```
macOS system audio (ScreenCaptureKit)
        │
        ▼
AudioBuffer (ring buffer, 24 kHz PCM)
        │
        ▼
TranscriptionEngine  ←─ Moshi STT (mlx-lm / moshi_mlx)
        │
        ▼
SessionOrchestrator ──► WebSocket broadcast → React frontend
        │
        ├──► InsightExtractor (Qwen 2.5, every 30 s)
        │
        └──► SQLite (aiosqlite) on session stop
```

**Backend:** FastAPI + aiosqlite + asyncio  
**Frontend:** React 18 + TypeScript + Vite  
**ML runtime:** MLX (Apple Silicon) — optional, graceful degradation without it

## Prerequisites

| Requirement | Notes |
|---|---|
| macOS 13 Ventura or later | ScreenCaptureKit audio capture |
| Apple Silicon Mac (M1+) | MLX ML acceleration |
| Python 3.12 | Backend runtime |
| Node 20+ | Frontend build |
| Screen Recording permission | System Settings → Privacy & Security |

## Installation

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate

# Core dependencies only (no ML)
pip install -e .

# With ML inference (STT + insights)
pip install -e ".[ml]"
```

### Frontend

```bash
cd frontend
npm install
```

## Running

```bash
# Terminal 1 — backend
cd backend
source .venv/bin/activate
uvicorn ribbet.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — frontend dev server
cd frontend
npm run dev
```

Open **http://localhost:5173** in your browser.

## Development

### Backend tests

```bash
cd backend
source .venv/bin/activate
pytest tests/ -v
```

### Frontend tests

```bash
cd frontend
npx vitest run
```

### Linting

```bash
# Backend
ruff check ribbet/ tests/
mypy ribbet/

# Frontend
npm run lint
```

## Data storage

Session data is stored at `~/.ribbet/ribbet.db` (SQLite). The database is created automatically on first run.

## Degraded mode

If ML dependencies (`moshi_mlx`, `mlx-lm`) or ScreenCaptureKit are not available, the app starts in **degraded mode**:

- Sessions can still be created, stopped, and reviewed via the REST API
- Transcription is skipped (no STT segments generated)
- Insight extraction is skipped
- Bookmarks and manual transcript imports still work
- WebSocket status messages report `source: "unavailable"` / `model: "cold"`

Grant **Screen Recording** permission in System Settings → Privacy & Security → Screen Recording, then restart the backend to re-enable capture.

## API reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/sessions` | Start a new session |
| `GET` | `/sessions` | List all sessions |
| `GET` | `/sessions/{id}` | Session detail |
| `POST` | `/sessions/{id}/stop` | Stop active session |
| `GET` | `/sessions/{id}/transcript` | Full transcript |
| `POST` | `/sessions/{id}/bookmarks` | Create bookmark |
| `GET` | `/sessions/{id}/bookmarks` | List bookmarks |
| `POST` | `/sessions/{id}/regenerate-insights` | Re-run insight extraction |
| `WS` | `/sessions/{id}/stream` | Real-time WebSocket stream |
| `GET` | `/health` | Health check |

## License

MIT

---

## Manual Validation Checklist — Task 12 (Local Transcription)

Run this checklist before shipping to confirm all nine Task 12 scenarios work end-to-end.
Prerequisites: backend running (`uvicorn ribbet.main:app`), frontend running (`npm run dev`).

### 1. Audio Setup
- [ ] macOS Screen Recording permission is **granted** for the terminal / app process
- [ ] `GET /health` returns `200 OK`
- [ ] Backend log shows `"Audio source available"` on `POST /sessions`
- [ ] WebSocket `status` event delivers `source: "capturing"`

### 2. Model Loading
- [ ] `POST /sessions` triggers STT warm-up; log shows `"STT model ready"`
- [ ] WebSocket delivers `model: "warming"` followed by `model: "ready"`
- [ ] If ML deps absent: log shows `"STT model failed to load"` but session still reaches `status: "active"` (degraded mode)

### 3. Live Session
- [ ] While a session is active, speak or play audio into the system source
- [ ] WebSocket delivers `type: "transcript"` segments within ~1 s
- [ ] `GET /sessions/{id}/transcript` returns accumulating segments during the session

### 4. Insight Extraction
- [ ] After ≥ 30 s of speech, WebSocket delivers `type: "insights"` with `stale: false`
- [ ] Insight snapshot contains at least one of `topics`, `actions`, or `decisions`
- [ ] `last_updated` timestamp advances on each refresh cycle

### 5. Bookmarks
- [ ] `POST /sessions/{id}/bookmarks` with `{"note": "test"}` returns `201` with `id`, `timestamp`, `snippet`
- [ ] `GET /sessions/{id}/bookmarks` lists the created bookmark
- [ ] `snippet` contains transcript text from ±30 s window around bookmark timestamp

### 6. Stop + Persist
- [ ] `POST /sessions/{id}/stop` returns `{"status": "stopped"}`
- [ ] WebSocket delivers `session: "stopped"`
- [ ] Backend log shows `"Persisted session … N segments, M bookmarks"`
- [ ] `GET /sessions/{id}/transcript` returns all segments that were broadcast live

### 7. Session Review
- [ ] `GET /sessions` lists the stopped session with correct `segment_count`
- [ ] `GET /sessions/{id}` returns `status: "stopped"` with `ended_at` set
- [ ] `POST /sessions/{id}/regenerate-insights` returns a fresh snapshot (not stale)
- [ ] Regenerated snapshot is persisted: re-calling the endpoint returns updated `last_updated`

### 8. Source Unavailable
- [ ] **Revoke** Screen Recording permission (or run without it)
- [ ] `POST /sessions` still succeeds and reaches `status: "active"`
- [ ] WebSocket delivers `type: "error"` with Screen Recording guidance message
- [ ] `source_status` is `"unavailable"`; no pipeline tasks are started
- [ ] Session can still be stopped cleanly via `POST /sessions/{id}/stop`

### 9. Insight Lag (stale snapshot)
- [ ] With a running session, temporarily disable the Qwen model (set `INSIGHT_MODEL_REPO` to an invalid path)
- [ ] After the next insight cycle, WebSocket delivers `type: "insights"` with `stale: true`
- [ ] Previous insight content is preserved in the stale broadcast (not cleared)
- [ ] Restore the model; subsequent cycle delivers `stale: false` snapshot
