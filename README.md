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
