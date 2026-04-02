# Local Meeting Transcription App Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a single-user local macOS webapp that captures system audio, generates live English transcription via Kyutai STT 1B, extracts live meeting insights (topics, actions, decisions), supports bookmarks, and persists transcripts — all running locally on Apple Silicon with no cloud dependency.

**Architecture:** Three-layer local system: (1) React frontend served on localhost for session control and live display, (2) Python FastAPI backend as session orchestrator with WebSocket streaming, (3) audio capture + ML pipeline using macOS ScreenCaptureKit for system audio and Kyutai STT 1B via `moshi_mlx` for Apple Silicon-optimized streaming transcription. Insight extraction runs as a decoupled async pipeline consuming transcript windows via a local LLM (mlx-lm with a small model like Qwen2.5-3B). SQLite for persistence.

**Tech Stack:**
- **Backend:** Python 3.12, FastAPI, uvicorn, WebSockets
- **Frontend:** React 19 + TypeScript, Vite, Tailwind CSS
- **STT Model:** Kyutai STT 1B EN/FR (`moshi_mlx` — MLX-optimized for Apple Silicon)
- **Audio Capture:** ScreenCaptureKit via `pyobjc-framework-ScreenCaptureKit`
- **Insight Extraction:** `mlx-lm` with a quantized small LLM (Qwen2.5-3B-Instruct-4bit)
- **Persistence:** SQLite via `aiosqlite`
- **Testing:** pytest + pytest-asyncio (backend), Vitest (frontend)

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────┐
│  Browser (localhost:5173)                             │
│  ┌──────────────┐ ┌───────────────────────────────┐  │
│  │ Control Bar   │ │  Insight Column  │ Transcript │  │
│  │ Start/Stop    │ │  Topics          │ Stream     │  │
│  │ Source Status  │ │  Actions         │ (live)     │  │
│  │ Bookmark Btn  │ │  Decisions       │            │  │
│  └──────────────┘ └───────────────────────────────┘  │
│         ▲ WebSocket (JSON messages)                   │
└─────────┼────────────────────────────────────────────┘
          │
┌─────────┼────────────────────────────────────────────┐
│  FastAPI Backend (localhost:8000)                      │
│  ┌──────┴──────┐                                      │
│  │ Session      │ ← REST: create/stop/list sessions   │
│  │ Orchestrator │ ← WS: live transcript + insight push│
│  └──────┬──────┘                                      │
│         │                                             │
│  ┌──────┴──────────────────────────────────────────┐  │
│  │ Audio Pipeline         │ Insight Pipeline        │  │
│  │ ScreenCaptureKit       │ Transcript window →     │  │
│  │ → PCM chunks           │ mlx-lm prompt →         │  │
│  │ → Kyutai STT 1B (MLX)  │ topics/actions/decisions│  │
│  │ → transcript segments  │                         │  │
│  └─────────────────────────────────────────────────┘  │
│                                                       │
│  SQLite: sessions, segments, bookmarks, insights      │
└───────────────────────────────────────────────────────┘
```

## Key Design Decisions

1. **Kyutai STT 1B via `moshi_mlx`** — The spec calls for Kyutai STT 1B EN/FR. The `moshi_mlx` package provides Apple Silicon-optimized inference. The model has a 0.5s text delay and native streaming support, well within the 2s latency target. We use the MLX path (not PyTorch/CUDA) because this is an Apple Silicon-only app.

2. **ScreenCaptureKit for system audio** — macOS 13+ provides `SCStreamConfiguration` for system audio capture without third-party virtual audio devices. We use `pyobjc-framework-ScreenCaptureKit` to access this from Python. This requires a one-time Screen Recording permission grant.

3. **Small local LLM for insight extraction** — Topics, actions, and decisions are extracted by prompting a small quantized LLM (`mlx-lm` with Qwen2.5-3B-Instruct-4bit) on sliding transcript windows. This runs on a separate thread/process so it never blocks the transcription fast path (REQ-023).

4. **SQLite for persistence** — Simple, local, zero-config. Async access via `aiosqlite`. Stores sessions, transcript segments with timestamps, bookmarks, and insight snapshots.

5. **Monorepo with `backend/` and `frontend/` dirs** — Simple flat structure. No workspace tooling overhead.

6. **WebSocket for live streaming** — Single WS connection per session carries transcript updates, insight updates, and status changes. REST endpoints for session CRUD and bookmark creation.

## Project Structure (Final State)

```
ribbet/
├── backend/
│   ├── pyproject.toml
│   ├── ribbet/
│   │   ├── __init__.py
│   │   ├── main.py                  # FastAPI app entry
│   │   ├── config.py                # App configuration
│   │   ├── db.py                    # SQLite schema + connection
│   │   ├── models.py                # Pydantic models
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── sessions.py          # REST: session CRUD
│   │   │   └── bookmarks.py         # REST: bookmark CRUD
│   │   ├── ws/
│   │   │   ├── __init__.py
│   │   │   └── session_stream.py    # WebSocket handler
│   │   ├── audio/
│   │   │   ├── __init__.py
│   │   │   └── capture.py           # ScreenCaptureKit wrapper
│   │   ├── transcription/
│   │   │   ├── __init__.py
│   │   │   └── engine.py            # Kyutai STT 1B wrapper
│   │   ├── insights/
│   │   │   ├── __init__.py
│   │   │   ├── extractor.py         # LLM-based insight extraction
│   │   │   └── prompts.py           # Prompt templates
│   │   └── session/
│   │       ├── __init__.py
│   │       └── orchestrator.py      # Session lifecycle + pipeline coordination
│   └── tests/
│       ├── conftest.py
│       ├── test_db.py
│       ├── test_models.py
│       ├── test_sessions_router.py
│       ├── test_bookmarks_router.py
│       ├── test_transcription_engine.py
│       ├── test_insight_extractor.py
│       └── test_orchestrator.py
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── hooks/
│       │   ├── useSessionSocket.ts   # WebSocket connection hook
│       │   └── useSession.ts         # Session state management
│       ├── components/
│       │   ├── ControlBar.tsx
│       │   ├── TranscriptStream.tsx
│       │   ├── InsightPanel.tsx
│       │   ├── TopicClusters.tsx
│       │   ├── ActionItems.tsx
│       │   ├── Decisions.tsx
│       │   ├── BookmarkButton.tsx
│       │   ├── BookmarkDialog.tsx
│       │   ├── SourceStatus.tsx
│       │   ├── SessionList.tsx
│       │   └── SessionReview.tsx
│       ├── types.ts
│       └── api.ts                    # REST client helpers
├── docs/
│   └── plans/
│       └── 2026-04-02-local-meeting-transcription-app.md
└── README.md
```

## Requirements Traceability

| Task | Requirements Covered |
|------|---------------------|
| 1-2  | REQ-001, REQ-002, REQ-003 (project skeleton, local app) |
| 3    | REQ-004, REQ-005, REQ-006, REQ-028, REQ-029, REQ-034 (DB, session lifecycle, persistence) |
| 4    | REQ-004, REQ-005, REQ-006 (session REST API) |
| 5    | REQ-007, REQ-008, REQ-009, REQ-010 (audio capture) |
| 6    | REQ-011, REQ-012, REQ-013, REQ-015 (live transcription) |
| 7    | REQ-006, REQ-008, REQ-014 (session orchestrator + WS) |
| 8    | REQ-003, REQ-014 (frontend shell + transcript display) |
| 9    | REQ-016, REQ-017, REQ-018, REQ-019, REQ-020, REQ-021, REQ-022, REQ-023 (insights) |
| 10   | REQ-024, REQ-025, REQ-026, REQ-027 (bookmarks) |
| 11   | REQ-028, REQ-029, REQ-030, REQ-031 (persistence + review) |
| 12   | All (integration test, manual validation) |

---

## TODOs

---

### Task 1: Initialize Backend Project

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/ribbet/__init__.py`
- Create: `backend/ribbet/main.py`
- Create: `backend/ribbet/config.py`
- Create: `backend/tests/conftest.py`

**Step 1: Create `backend/pyproject.toml`**

```toml
[project]
name = "ribbet"
version = "0.1.0"
description = "Local meeting transcription app for macOS"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "websockets>=13.0",
    "aiosqlite>=0.20.0",
    "pydantic>=2.9.0",
]

[project.optional-dependencies]
ml = [
    "moshi_mlx",
    "rustymimi",
    "mlx-lm",
    "pyobjc-framework-ScreenCaptureKit",
    "numpy",
    "soundfile",
]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.27.0",
    "ruff>=0.6.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"
line-length = 100
```

**Step 2: Create `backend/ribbet/__init__.py`**

```python
"""Ribbet — local meeting transcription app."""
```

**Step 3: Create `backend/ribbet/config.py`**

```python
"""Application configuration."""

from pathlib import Path
from pydantic import BaseModel


class Settings(BaseModel):
    """App-wide settings."""

    app_data_dir: Path = Path.home() / ".ribbet"
    db_filename: str = "ribbet.db"
    host: str = "127.0.0.1"
    port: int = 8000
    stt_model_repo: str = "kyutai/stt-1b-en_fr"
    stt_quantization: int = 4
    insight_model: str = "mlx-community/Qwen2.5-3B-Instruct-4bit"
    insight_window_seconds: int = 120
    insight_refresh_seconds: int = 30
    bookmark_snippet_seconds: int = 30

    @property
    def db_path(self) -> Path:
        return self.app_data_dir / self.db_filename


settings = Settings()
```

**Step 4: Create `backend/ribbet/main.py`**

```python
"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ribbet.config import settings

app = FastAPI(title="Ribbet", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://localhost:5173", f"http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "data_dir": str(settings.app_data_dir)}
```

**Step 5: Create `backend/tests/conftest.py`**

```python
"""Shared test fixtures."""

import pytest
from httpx import ASGITransport, AsyncClient

from ribbet.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

**Step 6: Write the smoke test**

Create `backend/tests/test_health.py`:

```python
"""Smoke test for the health endpoint."""

import pytest


@pytest.mark.asyncio
async def test_health_returns_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "data_dir" in body
```

**Step 7: Install dependencies and run the test**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/test_health.py -v
```

Expected: PASS — `test_health_returns_ok` passes.

**Step 8: Verify the server starts**

```bash
uvicorn ribbet.main:app --host 127.0.0.1 --port 8000
# In another terminal:
curl http://127.0.0.1:8000/health
```

Expected: `{"status":"ok","data_dir":".../.ribbet"}`

**Step 9: Commit**

```bash
git add backend/
git commit -m "feat: initialize backend project with FastAPI skeleton and health endpoint"
```

---

### Task 2: Initialize Frontend Project

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/types.ts`
- Create: `frontend/src/api.ts`

**Step 1: Scaffold the Vite + React + TypeScript project**

```bash
cd frontend
npm create vite@latest . -- --template react-ts
```

If the directory already exists, answer "yes" to proceed. This generates boilerplate.

**Step 2: Install Tailwind CSS**

```bash
npm install -D tailwindcss @tailwindcss/vite
```

**Step 3: Add Tailwind to `vite.config.ts`**

Replace `frontend/vite.config.ts` with:

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true,
      },
    },
  },
});
```

**Step 4: Add Tailwind import to CSS**

Replace `frontend/src/index.css` with:

```css
@import "tailwindcss";
```

**Step 5: Create `frontend/src/types.ts`**

```typescript
/** Shared types for the Ribbet frontend. */

export type SessionStatus = "idle" | "starting" | "active" | "stopping" | "stopped" | "error";
export type SourceStatus = "unknown" | "ready" | "capturing" | "unavailable" | "interrupted";
export type ModelStatus = "cold" | "warming" | "ready" | "slow";

export interface TranscriptSegment {
  id: string;
  text: string;
  start_time: number;
  end_time: number;
  is_partial: boolean;
}

export interface TopicCluster {
  label: string;
  prominence: number;
  keywords: string[];
}

export interface ActionItem {
  id: string;
  text: string;
  timestamp: number;
}

export interface Decision {
  id: string;
  text: string;
  timestamp: number;
}

export interface Bookmark {
  id: string;
  timestamp: number;
  note: string;
  snippet: string;
  created_at: string;
}

export interface SessionSummary {
  id: string;
  started_at: string;
  ended_at: string | null;
  status: SessionStatus;
  segment_count: number;
}

export interface InsightSnapshot {
  topics: TopicCluster[];
  actions: ActionItem[];
  decisions: Decision[];
  stale: boolean;
  last_updated: string | null;
}

/** WebSocket message types from server → client */
export type WsMessage =
  | { type: "transcript"; segment: TranscriptSegment }
  | { type: "insights"; snapshot: InsightSnapshot }
  | { type: "status"; session: SessionStatus; source: SourceStatus; model: ModelStatus }
  | { type: "error"; message: string };
```

**Step 6: Create `frontend/src/api.ts`**

```typescript
/** REST API helpers. */

const BASE = "/api";

export async function startSession(): Promise<{ session_id: string }> {
  const res = await fetch(`${BASE}/sessions`, { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function stopSession(sessionId: string): Promise<void> {
  const res = await fetch(`${BASE}/sessions/${sessionId}/stop`, { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
}

export async function listSessions(): Promise<{ sessions: import("./types").SessionSummary[] }> {
  const res = await fetch(`${BASE}/sessions`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function createBookmark(
  sessionId: string,
  note: string
): Promise<import("./types").Bookmark> {
  const res = await fetch(`${BASE}/sessions/${sessionId}/bookmarks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
```

**Step 7: Replace `frontend/src/App.tsx` with a placeholder**

```tsx
function App() {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex items-center justify-center">
      <h1 className="text-3xl font-bold">Ribbet</h1>
    </div>
  );
}

export default App;
```

**Step 8: Install test dependencies**

```bash
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

Add to `vite.config.ts` (inside `defineConfig`):

```typescript
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/test-setup.ts",
  },
```

Create `frontend/src/test-setup.ts`:

```typescript
import "@testing-library/jest-dom";
```

**Step 9: Write smoke test**

Create `frontend/src/App.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import App from "./App";

test("renders app title", () => {
  render(<App />);
  expect(screen.getByText("Ribbet")).toBeInTheDocument();
});
```

**Step 10: Run the test**

```bash
npx vitest run
```

Expected: PASS.

**Step 11: Commit**

```bash
git add frontend/
git commit -m "feat: initialize frontend with React, Vite, TypeScript, and Tailwind"
```

---

### Task 3: Database Schema and Data Access Layer

**Files:**
- Create: `backend/ribbet/db.py`
- Create: `backend/ribbet/models.py`
- Create: `backend/tests/test_db.py`
- Create: `backend/tests/test_models.py`

**Step 1: Write the failing test for DB initialization**

Create `backend/tests/test_db.py`:

```python
"""Tests for database initialization and access."""

import pytest
from pathlib import Path
from ribbet.db import init_db, get_db


@pytest.fixture
async def db_path(tmp_path):
    path = tmp_path / "test.db"
    await init_db(path)
    return path


@pytest.mark.asyncio
async def test_init_db_creates_tables(db_path):
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]
    assert "sessions" in tables
    assert "transcript_segments" in tables
    assert "bookmarks" in tables
    assert "insight_snapshots" in tables


@pytest.mark.asyncio
async def test_init_db_is_idempotent(db_path):
    # calling init_db again should not raise
    await init_db(db_path)
```

**Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/test_db.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'ribbet.db'` or import error.

**Step 3: Implement `backend/ribbet/db.py`**

```python
"""SQLite database initialization and access."""

from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS transcript_segments (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    text TEXT NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    is_partial INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS bookmarks (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    timestamp REAL NOT NULL,
    note TEXT NOT NULL,
    snippet TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS insight_snapshots (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_segments_session ON transcript_segments(session_id, start_time);
CREATE INDEX IF NOT EXISTS idx_bookmarks_session ON bookmarks(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_insights_session ON insight_snapshots(session_id, created_at);
"""


async def init_db(db_path: Path) -> None:
    """Create the database and tables if they don't exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.executescript(SCHEMA)
        await db.commit()


@asynccontextmanager
async def get_db(db_path: Path):
    """Yield an async database connection."""
    async with aiosqlite.connect(str(db_path)) as db:
        db.row_factory = aiosqlite.Row
        yield db
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_db.py -v
```

Expected: PASS.

**Step 5: Write the failing test for Pydantic models**

Create `backend/tests/test_models.py`:

```python
"""Tests for Pydantic data models."""

import pytest
from ribbet.models import (
    SessionCreate,
    SessionOut,
    TranscriptSegmentOut,
    BookmarkCreate,
    BookmarkOut,
    InsightSnapshot,
    TopicCluster,
    ActionItem,
    Decision,
)


def test_session_out_serializes():
    s = SessionOut(
        id="s1",
        started_at="2026-04-02T10:00:00",
        ended_at=None,
        status="active",
        segment_count=0,
    )
    d = s.model_dump()
    assert d["id"] == "s1"
    assert d["ended_at"] is None


def test_transcript_segment_out():
    seg = TranscriptSegmentOut(
        id="seg1",
        text="Hello world",
        start_time=1.0,
        end_time=2.5,
        is_partial=False,
    )
    assert seg.text == "Hello world"
    assert seg.is_partial is False


def test_bookmark_create_requires_note():
    b = BookmarkCreate(note="Important point")
    assert b.note == "Important point"


def test_insight_snapshot_structure():
    snap = InsightSnapshot(
        topics=[TopicCluster(label="Budget", prominence=0.8, keywords=["budget", "cost"])],
        actions=[ActionItem(id="a1", text="Review budget", timestamp=60.0)],
        decisions=[Decision(id="d1", text="Approved Q3 plan", timestamp=120.0)],
        stale=False,
        last_updated="2026-04-02T10:05:00",
    )
    assert len(snap.topics) == 1
    assert snap.topics[0].label == "Budget"
```

**Step 6: Run test to verify it fails**

```bash
pytest tests/test_models.py -v
```

Expected: FAIL — import error.

**Step 7: Implement `backend/ribbet/models.py`**

```python
"""Pydantic models for API request/response and internal data."""

from pydantic import BaseModel


class SessionCreate(BaseModel):
    """No fields needed — server generates everything."""
    pass


class SessionOut(BaseModel):
    id: str
    started_at: str
    ended_at: str | None
    status: str
    segment_count: int


class TranscriptSegmentOut(BaseModel):
    id: str
    text: str
    start_time: float
    end_time: float
    is_partial: bool


class BookmarkCreate(BaseModel):
    note: str


class BookmarkOut(BaseModel):
    id: str
    timestamp: float
    note: str
    snippet: str
    created_at: str


class TopicCluster(BaseModel):
    label: str
    prominence: float
    keywords: list[str]


class ActionItem(BaseModel):
    id: str
    text: str
    timestamp: float


class Decision(BaseModel):
    id: str
    text: str
    timestamp: float


class InsightSnapshot(BaseModel):
    topics: list[TopicCluster]
    actions: list[ActionItem]
    decisions: list[Decision]
    stale: bool
    last_updated: str | None
```

**Step 8: Run tests to verify they pass**

```bash
pytest tests/test_db.py tests/test_models.py -v
```

Expected: All PASS.

**Step 9: Commit**

```bash
git add backend/ribbet/db.py backend/ribbet/models.py backend/tests/test_db.py backend/tests/test_models.py
git commit -m "feat: add SQLite schema, DB access layer, and Pydantic models"
```

---

### Task 4: Session REST API (CRUD)

**Files:**
- Create: `backend/ribbet/routers/__init__.py`
- Create: `backend/ribbet/routers/sessions.py`
- Create: `backend/tests/test_sessions_router.py`
- Modify: `backend/ribbet/main.py` (register router, add DB lifecycle)

**Step 1: Write the failing tests**

Create `backend/tests/test_sessions_router.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_sessions_router.py -v
```

Expected: FAIL.

**Step 3: Create `backend/ribbet/routers/__init__.py`**

```python
```

**Step 4: Implement `backend/ribbet/routers/sessions.py`**

```python
"""Session CRUD REST endpoints."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ribbet.config import settings
from ribbet.db import get_db

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", status_code=201)
async def create_session():
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    async with get_db(settings.db_path) as db:
        await db.execute(
            "INSERT INTO sessions (id, started_at, status) VALUES (?, ?, ?)",
            (session_id, now, "active"),
        )
        await db.commit()
    return {"session_id": session_id}


@router.get("")
async def list_sessions():
    async with get_db(settings.db_path) as db:
        cursor = await db.execute(
            """SELECT s.id, s.started_at, s.ended_at, s.status,
                      (SELECT COUNT(*) FROM transcript_segments WHERE session_id = s.id) as segment_count
               FROM sessions s ORDER BY s.started_at DESC"""
        )
        rows = await cursor.fetchall()
    sessions = [
        {
            "id": r["id"],
            "started_at": r["started_at"],
            "ended_at": r["ended_at"],
            "status": r["status"],
            "segment_count": r["segment_count"],
        }
        for r in rows
    ]
    return {"sessions": sessions}


@router.get("/{session_id}")
async def get_session(session_id: str):
    async with get_db(settings.db_path) as db:
        cursor = await db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        seg_cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM transcript_segments WHERE session_id = ?",
            (session_id,),
        )
        seg_row = await seg_cursor.fetchone()
    return {
        "id": row["id"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
        "status": row["status"],
        "segment_count": seg_row["cnt"],
    }


@router.post("/{session_id}/stop")
async def stop_session(session_id: str):
    now = datetime.now(timezone.utc).isoformat()
    async with get_db(settings.db_path) as db:
        cursor = await db.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Session not found")
        await db.execute(
            "UPDATE sessions SET status = 'stopped', ended_at = ? WHERE id = ?",
            (now, session_id),
        )
        await db.commit()
    return {"status": "stopped"}
```

**Step 5: Update `backend/ribbet/main.py` to register the router and init DB on startup**

```python
"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ribbet.config import settings
from ribbet.db import init_db
from ribbet.routers import sessions


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(settings.db_path)
    yield


app = FastAPI(title="Ribbet", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)


@app.get("/health")
async def health():
    return {"status": "ok", "data_dir": str(settings.app_data_dir)}
```

**Step 6: Run all tests**

```bash
pytest tests/ -v
```

Expected: All PASS (health + db + models + sessions).

**Step 7: Commit**

```bash
git add backend/
git commit -m "feat: add session CRUD REST endpoints with SQLite persistence"
```

---

### Task 5: Audio Capture Module (ScreenCaptureKit)

**Files:**
- Create: `backend/ribbet/audio/__init__.py`
- Create: `backend/ribbet/audio/capture.py`
- Create: `backend/tests/test_audio_capture.py`

**Step 1: Write the unit tests (testable parts only)**

The actual ScreenCaptureKit calls require macOS permissions and can't run in CI. We test the interface and buffering logic, and mark integration tests.

Create `backend/tests/test_audio_capture.py`:

```python
"""Tests for audio capture module.

NOTE: Tests that actually capture system audio are marked @pytest.mark.macos
and require Screen Recording permission. Run with: pytest -m macos
"""

import pytest
import asyncio
import numpy as np
from unittest.mock import AsyncMock

from ribbet.audio.capture import AudioBuffer, AudioCaptureConfig


def test_audio_buffer_append_and_read():
    buf = AudioBuffer(sample_rate=24000, max_seconds=10)
    chunk = np.zeros(4800, dtype=np.float32)  # 0.2s at 24kHz
    buf.append(chunk)
    assert buf.duration_seconds == pytest.approx(0.2, abs=0.01)


def test_audio_buffer_read_last_n_seconds():
    buf = AudioBuffer(sample_rate=24000, max_seconds=10)
    # Add 1 second of audio
    for _ in range(5):
        buf.append(np.ones(4800, dtype=np.float32))
    chunk = buf.read_last(0.5)
    assert len(chunk) == 12000  # 0.5s * 24000
    assert chunk.dtype == np.float32


def test_audio_buffer_evicts_old_data():
    buf = AudioBuffer(sample_rate=24000, max_seconds=2)
    # Add 3 seconds of audio
    for _ in range(15):
        buf.append(np.ones(4800, dtype=np.float32))
    assert buf.duration_seconds <= 2.1  # allows small float margin


def test_audio_capture_config_defaults():
    config = AudioCaptureConfig()
    assert config.sample_rate == 24000
    assert config.channels == 1


def test_audio_buffer_read_from_empty():
    buf = AudioBuffer(sample_rate=24000, max_seconds=10)
    chunk = buf.read_last(1.0)
    assert len(chunk) == 0
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_audio_capture.py -v
```

Expected: FAIL — import error.

**Step 3: Create `backend/ribbet/audio/__init__.py`**

```python
```

**Step 4: Implement `backend/ribbet/audio/capture.py`**

```python
"""System audio capture via macOS ScreenCaptureKit.

The AudioBuffer class is platform-independent and testable.
The SystemAudioCapture class wraps ScreenCaptureKit and requires macOS + permissions.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class AudioCaptureConfig:
    sample_rate: int = 24000
    channels: int = 1
    buffer_max_seconds: float = 300  # 5 min rolling buffer


class AudioBuffer:
    """Thread-safe rolling audio buffer."""

    def __init__(self, sample_rate: int, max_seconds: float):
        self.sample_rate = sample_rate
        self._max_samples = int(max_seconds * sample_rate)
        self._data = np.array([], dtype=np.float32)

    def append(self, chunk: np.ndarray) -> None:
        self._data = np.concatenate([self._data, chunk.astype(np.float32)])
        if len(self._data) > self._max_samples:
            self._data = self._data[-self._max_samples:]

    def read_last(self, seconds: float) -> np.ndarray:
        n = int(seconds * self.sample_rate)
        if len(self._data) == 0:
            return np.array([], dtype=np.float32)
        return self._data[-n:]

    @property
    def duration_seconds(self) -> float:
        return len(self._data) / self.sample_rate


class SystemAudioCapture:
    """Captures system audio via macOS ScreenCaptureKit.

    Usage:
        capture = SystemAudioCapture(config, on_chunk=callback)
        available = await capture.check_availability()
        if available:
            await capture.start()
            # ... later
            await capture.stop()
    """

    def __init__(
        self,
        config: AudioCaptureConfig,
        on_chunk: Callable[[np.ndarray], None] | None = None,
    ):
        self.config = config
        self.on_chunk = on_chunk
        self._stream = None
        self._running = False

    async def check_availability(self) -> tuple[bool, str]:
        """Check if system audio capture is available.

        Returns (is_available, message).
        """
        try:
            import ScreenCaptureKit  # noqa: F401
            return True, "ScreenCaptureKit available"
        except ImportError:
            return False, (
                "ScreenCaptureKit not available. "
                "Install pyobjc-framework-ScreenCaptureKit and ensure macOS 13+."
            )

    async def start(self) -> None:
        """Start capturing system audio. Raises RuntimeError if unavailable."""
        available, msg = await self.check_availability()
        if not available:
            raise RuntimeError(msg)

        # Actual ScreenCaptureKit setup is implemented here.
        # This is a simplified skeleton — full implementation will use
        # SCShareableContent, SCStreamConfiguration, and SCStream.
        logger.info("Starting system audio capture at %d Hz", self.config.sample_rate)
        self._running = True

        # Implementation note for the engineer:
        # The full implementation needs to:
        # 1. Get SCShareableContent.getWithCompletionHandler_()
        # 2. Create SCStreamConfiguration with audio enabled
        # 3. Set sample rate to self.config.sample_rate
        # 4. Create SCStream and add a stream output delegate
        # 5. The delegate's stream_didOutputSampleBuffer_ofType_ method
        #    converts CMSampleBuffer → numpy array and calls self.on_chunk()
        #
        # See Task 5 implementation notes below for the full PyObjC code.

    async def stop(self) -> None:
        """Stop capturing."""
        self._running = False
        logger.info("Stopped system audio capture")

    @property
    def is_running(self) -> bool:
        return self._running
```

**Step 5: Run tests to verify they pass**

```bash
pytest tests/test_audio_capture.py -v
```

Expected: All PASS.

**Step 6: Commit**

```bash
git add backend/ribbet/audio/ backend/tests/test_audio_capture.py
git commit -m "feat: add audio buffer and ScreenCaptureKit capture skeleton"
```

**Implementation Note for ScreenCaptureKit:**

The full `SystemAudioCapture.start()` implementation requires completing the PyObjC bridge code. The engineer should:

1. Study `pyobjc-framework-ScreenCaptureKit` API
2. Get shareable content: `SCShareableContent.getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_`
3. Configure audio-only stream: set `capturesAudio = True`, `excludesCurrentProcessAudio = False`, `sampleRate = 24000`, `channelCount = 1`
4. Create an `SCStreamOutput` delegate subclass that receives `CMSampleBuffer`, extracts PCM float data, and calls `self.on_chunk(numpy_array)`
5. Test manually with Screen Recording permission granted

This is inherently platform-specific and must be validated manually (see Task 12).

---

### Task 6: Transcription Engine (Kyutai STT 1B)

**Files:**
- Create: `backend/ribbet/transcription/__init__.py`
- Create: `backend/ribbet/transcription/engine.py`
- Create: `backend/tests/test_transcription_engine.py`

**Step 1: Write unit tests for the transcription engine interface**

Create `backend/tests/test_transcription_engine.py`:

```python
"""Tests for the transcription engine.

Tests the interface and segment handling.
Actual model inference tests are marked @pytest.mark.slow (requires model download).
"""

import pytest
from ribbet.transcription.engine import TranscriptSegment, TranscriptionResult


def test_transcript_segment_creation():
    seg = TranscriptSegment(
        text="Hello, how are you?",
        start_time=1.0,
        end_time=3.5,
        is_partial=False,
    )
    assert seg.text == "Hello, how are you?"
    assert seg.end_time - seg.start_time == pytest.approx(2.5)


def test_transcript_segment_partial():
    seg = TranscriptSegment(
        text="Hello",
        start_time=1.0,
        end_time=1.5,
        is_partial=True,
    )
    assert seg.is_partial is True


def test_transcription_result_accumulation():
    result = TranscriptionResult()
    result.add_segment(TranscriptSegment("Hello", 0.0, 1.0, False))
    result.add_segment(TranscriptSegment("world", 1.0, 2.0, False))
    assert result.full_text == "Hello world"
    assert len(result.segments) == 2


def test_transcription_result_window():
    result = TranscriptionResult()
    for i in range(10):
        result.add_segment(
            TranscriptSegment(f"word{i}", float(i), float(i + 1), False)
        )
    window = result.text_window(start=5.0, end=8.0)
    assert "word5" in window
    assert "word7" in window
    assert "word9" not in window
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_transcription_engine.py -v
```

Expected: FAIL — import error.

**Step 3: Create `backend/ribbet/transcription/__init__.py`**

```python
```

**Step 4: Implement `backend/ribbet/transcription/engine.py`**

```python
"""Kyutai STT 1B transcription engine.

Wraps moshi_mlx for Apple Silicon-optimized streaming STT.
The TranscriptionEngine class manages model lifecycle and streaming inference.
The TranscriptSegment/TranscriptionResult classes are plain data, fully testable.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TranscriptSegment:
    text: str
    start_time: float
    end_time: float
    is_partial: bool
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


class TranscriptionResult:
    """Accumulates confirmed transcript segments."""

    def __init__(self):
        self.segments: list[TranscriptSegment] = []

    def add_segment(self, segment: TranscriptSegment) -> None:
        self.segments.append(segment)

    @property
    def full_text(self) -> str:
        return " ".join(s.text for s in self.segments if not s.is_partial)

    def text_window(self, start: float, end: float) -> str:
        """Get text from segments overlapping the given time window."""
        return " ".join(
            s.text
            for s in self.segments
            if not s.is_partial and s.start_time >= start and s.start_time < end
        )

    def recent_text(self, last_seconds: float) -> str:
        """Get text from the last N seconds of transcript."""
        if not self.segments:
            return ""
        latest = self.segments[-1].end_time
        cutoff = latest - last_seconds
        return " ".join(
            s.text for s in self.segments if not s.is_partial and s.start_time >= cutoff
        )


class TranscriptionEngine:
    """Manages Kyutai STT 1B model loading and streaming inference.

    Usage:
        engine = TranscriptionEngine(model_repo="kyutai/stt-1b-en_fr", quantization=4)
        await engine.load()
        # Feed audio chunks:
        segments = await engine.transcribe_chunk(audio_numpy_array, chunk_start_time)
        await engine.unload()
    """

    def __init__(self, model_repo: str, quantization: int = 4):
        self.model_repo = model_repo
        self.quantization = quantization
        self._model = None
        self._mimi = None
        self._text_tokenizer = None
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    async def load(self) -> None:
        """Load the STT model. This is slow (first run downloads weights)."""
        logger.info("Loading STT model %s (q%d)...", self.model_repo, self.quantization)

        # Implementation note for the engineer:
        # Use the moshi_mlx inference API:
        #
        # from moshi_mlx.models import loaders
        # checkpoint_info = loaders.CheckpointInfo.from_hf_repo(self.model_repo)
        # self._mimi = checkpoint_info.get_mimi(device="mps")  # or default MLX device
        # self._text_tokenizer = checkpoint_info.get_text_tokenizer()
        # self._model = checkpoint_info.get_moshi(device="mps")
        #
        # The actual streaming inference loop:
        # 1. Pad audio per stt_config audio_silence_prefix_seconds
        # 2. Create InferenceState(mimi, text_tokenizer, model, batch_size=1)
        # 3. Feed chunks via state.run() or the streaming API
        # 4. Decode output tokens to text with timestamps

        self._loaded = True
        logger.info("STT model loaded")

    async def transcribe_chunk(
        self, audio: np.ndarray, chunk_start_time: float
    ) -> list[TranscriptSegment]:
        """Transcribe an audio chunk and return new segments.

        Args:
            audio: float32 numpy array of audio samples at 24kHz
            chunk_start_time: wall-clock offset of this chunk in the session

        Returns:
            List of new TranscriptSegment objects
        """
        if not self._loaded:
            raise RuntimeError("Model not loaded. Call load() first.")

        # Implementation note for the engineer:
        # This is where the actual moshi_mlx inference happens.
        # The chunk is fed to the model's streaming state, and
        # any new text tokens are decoded and returned as segments.
        #
        # The model has a 0.5s text delay, so timestamps should be
        # adjusted: text_timestamp = audio_frame_offset - 0.5

        return []

    async def unload(self) -> None:
        """Release model resources."""
        self._model = None
        self._mimi = None
        self._text_tokenizer = None
        self._loaded = False
        logger.info("STT model unloaded")
```

**Step 5: Run tests to verify they pass**

```bash
pytest tests/test_transcription_engine.py -v
```

Expected: All PASS.

**Step 6: Commit**

```bash
git add backend/ribbet/transcription/ backend/tests/test_transcription_engine.py
git commit -m "feat: add transcription engine interface and segment data structures"
```

---

### Task 7: Session Orchestrator and WebSocket Handler

**Files:**
- Create: `backend/ribbet/session/__init__.py`
- Create: `backend/ribbet/session/orchestrator.py`
- Create: `backend/ribbet/ws/__init__.py`
- Create: `backend/ribbet/ws/session_stream.py`
- Create: `backend/tests/test_orchestrator.py`
- Modify: `backend/ribbet/main.py` (register WS route)

**Step 1: Write the failing orchestrator tests**

Create `backend/tests/test_orchestrator.py`:

```python
"""Tests for the session orchestrator."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from ribbet.session.orchestrator import SessionOrchestrator, SessionState


def test_session_state_initial():
    state = SessionState(session_id="s1")
    assert state.status == "idle"
    assert state.source_status == "unknown"
    assert state.model_status == "cold"
    assert len(state.segments) == 0


def test_session_state_add_segment():
    from ribbet.transcription.engine import TranscriptSegment

    state = SessionState(session_id="s1")
    seg = TranscriptSegment("hello", 0.0, 1.0, False)
    state.add_segment(seg)
    assert len(state.segments) == 1
    assert state.segments[0].text == "hello"


def test_session_state_get_snippet():
    from ribbet.transcription.engine import TranscriptSegment

    state = SessionState(session_id="s1")
    for i in range(10):
        state.add_segment(TranscriptSegment(f"word{i}", float(i), float(i + 1), False))

    snippet = state.get_snippet_around(5.0, window_seconds=2)
    assert "word4" in snippet or "word5" in snippet
    assert "word0" not in snippet
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_orchestrator.py -v
```

Expected: FAIL — import error.

**Step 3: Create `backend/ribbet/session/__init__.py`**

```python
```

**Step 4: Implement `backend/ribbet/session/orchestrator.py`**

```python
"""Session lifecycle orchestrator.

Coordinates audio capture, transcription, and insight extraction.
Pushes updates to connected WebSocket clients.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ribbet.config import settings
from ribbet.transcription.engine import TranscriptSegment, TranscriptionResult

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    session_id: str
    status: str = "idle"
    source_status: str = "unknown"
    model_status: str = "cold"
    result: TranscriptionResult = field(default_factory=TranscriptionResult)
    insight_snapshot: dict = field(default_factory=lambda: {
        "topics": [], "actions": [], "decisions": [],
        "stale": True, "last_updated": None,
    })
    bookmarks: list[dict] = field(default_factory=list)

    @property
    def segments(self) -> list[TranscriptSegment]:
        return self.result.segments

    def add_segment(self, segment: TranscriptSegment) -> None:
        self.result.add_segment(segment)

    def get_snippet_around(self, timestamp: float, window_seconds: float = 30.0) -> str:
        """Get transcript text around a timestamp for bookmark snippets."""
        half = window_seconds / 2
        start = max(0, timestamp - half)
        end = timestamp + half
        return self.result.text_window(start, end)


class SessionOrchestrator:
    """Manages a single active session's lifecycle.

    There is at most one active session at a time.
    """

    def __init__(self):
        self._state: SessionState | None = None
        self._ws_clients: list[Any] = []  # WebSocket connections
        self._capture_task: asyncio.Task | None = None
        self._insight_task: asyncio.Task | None = None

    @property
    def active_session(self) -> SessionState | None:
        return self._state

    def register_ws(self, ws) -> None:
        self._ws_clients.append(ws)

    def unregister_ws(self, ws) -> None:
        if ws in self._ws_clients:
            self._ws_clients.remove(ws)

    async def broadcast(self, message: dict) -> None:
        """Send a JSON message to all connected WebSocket clients."""
        dead = []
        for ws in self._ws_clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.unregister_ws(ws)

    async def start_session(self, session_id: str) -> SessionState:
        """Start a new transcription session."""
        if self._state and self._state.status == "active":
            raise RuntimeError("A session is already active")

        self._state = SessionState(session_id=session_id, status="starting")
        await self.broadcast({
            "type": "status",
            "session": "starting",
            "source": "unknown",
            "model": "cold",
        })

        # In full implementation:
        # 1. Check audio source availability → update source_status
        # 2. Load STT model if needed → update model_status
        # 3. Start audio capture loop → _capture_task
        # 4. Start insight extraction loop → _insight_task

        self._state.status = "active"
        self._state.source_status = "capturing"
        self._state.model_status = "ready"

        await self.broadcast({
            "type": "status",
            "session": "active",
            "source": "capturing",
            "model": "ready",
        })

        return self._state

    async def stop_session(self) -> None:
        """Stop the active session."""
        if not self._state:
            return

        self._state.status = "stopping"
        await self.broadcast({
            "type": "status",
            "session": "stopping",
            "source": self._state.source_status,
            "model": self._state.model_status,
        })

        # Cancel background tasks
        if self._capture_task:
            self._capture_task.cancel()
        if self._insight_task:
            self._insight_task.cancel()

        self._state.status = "stopped"
        await self.broadcast({
            "type": "status",
            "session": "stopped",
            "source": "unknown",
            "model": "cold",
        })

    async def handle_new_segment(self, segment: TranscriptSegment) -> None:
        """Called when the transcription engine produces a new segment."""
        if not self._state:
            return
        self._state.add_segment(segment)
        await self.broadcast({
            "type": "transcript",
            "segment": {
                "id": segment.id,
                "text": segment.text,
                "start_time": segment.start_time,
                "end_time": segment.end_time,
                "is_partial": segment.is_partial,
            },
        })

    async def update_insights(self, snapshot: dict) -> None:
        """Called when insight extraction produces new results."""
        if not self._state:
            return
        self._state.insight_snapshot = snapshot
        await self.broadcast({"type": "insights", "snapshot": snapshot})

    def create_bookmark(self, note: str) -> dict | None:
        """Create a bookmark at the current position."""
        if not self._state or self._state.status != "active":
            return None
        if not self._state.segments:
            timestamp = 0.0
        else:
            timestamp = self._state.segments[-1].end_time

        snippet = self._state.get_snippet_around(
            timestamp, window_seconds=settings.bookmark_snippet_seconds
        )
        bookmark = {
            "id": str(uuid.uuid4()),
            "timestamp": timestamp,
            "note": note,
            "snippet": snippet,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._state.bookmarks.append(bookmark)
        return bookmark


# Global singleton — one orchestrator per server process
orchestrator = SessionOrchestrator()
```

**Step 5: Create `backend/ribbet/ws/__init__.py`**

```python
```

**Step 6: Implement `backend/ribbet/ws/session_stream.py`**

```python
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
        await websocket.send_json({
            "type": "status",
            "session": state.status,
            "source": state.source_status,
            "model": state.model_status,
        })
        # Send existing segments
        for seg in state.segments:
            await websocket.send_json({
                "type": "transcript",
                "segment": {
                    "id": seg.id,
                    "text": seg.text,
                    "start_time": seg.start_time,
                    "end_time": seg.end_time,
                    "is_partial": seg.is_partial,
                },
            })
        # Send current insights
        await websocket.send_json({
            "type": "insights",
            "snapshot": state.insight_snapshot,
        })
    else:
        await websocket.send_json({
            "type": "status",
            "session": "idle",
            "source": "unknown",
            "model": "cold",
        })

    try:
        while True:
            # Keep connection alive; client sends keepalive pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        orchestrator.unregister_ws(websocket)
```

**Step 7: Register the WS router in `main.py`**

Add to `backend/ribbet/main.py`:

```python
from ribbet.ws import session_stream

# ... after app.include_router(sessions.router):
app.include_router(session_stream.router)
```

**Step 8: Run all tests**

```bash
pytest tests/ -v
```

Expected: All PASS.

**Step 9: Commit**

```bash
git add backend/ribbet/session/ backend/ribbet/ws/ backend/tests/test_orchestrator.py backend/ribbet/main.py
git commit -m "feat: add session orchestrator, WebSocket handler, and live broadcast"
```

---

### Task 8: Frontend — Live Session UI

**Files:**
- Create: `frontend/src/hooks/useSessionSocket.ts`
- Create: `frontend/src/hooks/useSession.ts`
- Create: `frontend/src/components/ControlBar.tsx`
- Create: `frontend/src/components/TranscriptStream.tsx`
- Create: `frontend/src/components/InsightPanel.tsx`
- Create: `frontend/src/components/TopicClusters.tsx`
- Create: `frontend/src/components/ActionItems.tsx`
- Create: `frontend/src/components/Decisions.tsx`
- Create: `frontend/src/components/BookmarkButton.tsx`
- Create: `frontend/src/components/BookmarkDialog.tsx`
- Create: `frontend/src/components/SourceStatus.tsx`
- Modify: `frontend/src/App.tsx`

This task builds the full live session UI. Each component is small. The engineer should implement them in order and test visually after each one.

**Step 1: Implement `useSessionSocket` hook**

Create `frontend/src/hooks/useSessionSocket.ts`:

```typescript
import { useEffect, useRef, useCallback, useState } from "react";
import type { WsMessage, TranscriptSegment, InsightSnapshot, SessionStatus, SourceStatus, ModelStatus } from "../types";

interface SessionSocketState {
  segments: TranscriptSegment[];
  insights: InsightSnapshot;
  sessionStatus: SessionStatus;
  sourceStatus: SourceStatus;
  modelStatus: ModelStatus;
  error: string | null;
  connected: boolean;
}

const EMPTY_INSIGHTS: InsightSnapshot = {
  topics: [],
  actions: [],
  decisions: [],
  stale: true,
  last_updated: null,
};

export function useSessionSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const [state, setState] = useState<SessionSocketState>({
    segments: [],
    insights: EMPTY_INSIGHTS,
    sessionStatus: "idle",
    sourceStatus: "unknown",
    modelStatus: "cold",
    error: null,
    connected: false,
  });

  const connect = useCallback(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/session`);

    ws.onopen = () => setState((s) => ({ ...s, connected: true, error: null }));

    ws.onmessage = (event) => {
      const msg: WsMessage = JSON.parse(event.data);
      setState((prev) => {
        switch (msg.type) {
          case "transcript": {
            const exists = prev.segments.find((s) => s.id === msg.segment.id);
            if (exists) {
              return {
                ...prev,
                segments: prev.segments.map((s) =>
                  s.id === msg.segment.id ? msg.segment : s
                ),
              };
            }
            return { ...prev, segments: [...prev.segments, msg.segment] };
          }
          case "insights":
            return { ...prev, insights: msg.snapshot };
          case "status":
            return {
              ...prev,
              sessionStatus: msg.session,
              sourceStatus: msg.source,
              modelStatus: msg.model,
            };
          case "error":
            return { ...prev, error: msg.message };
          default:
            return prev;
        }
      });
    };

    ws.onclose = () => setState((s) => ({ ...s, connected: false }));
    ws.onerror = () => setState((s) => ({ ...s, error: "WebSocket error" }));

    wsRef.current = ws;
  }, []);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
  }, []);

  const resetSegments = useCallback(() => {
    setState((s) => ({ ...s, segments: [], insights: EMPTY_INSIGHTS }));
  }, []);

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return { ...state, reconnect: connect, resetSegments };
}
```

**Step 2: Implement `useSession` hook**

Create `frontend/src/hooks/useSession.ts`:

```typescript
import { useState, useCallback } from "react";
import { startSession, stopSession, createBookmark } from "../api";
import { useSessionSocket } from "./useSessionSocket";

export function useSession() {
  const socket = useSessionSocket();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleStart = useCallback(async () => {
    setLoading(true);
    try {
      socket.resetSegments();
      const { session_id } = await startSession();
      setSessionId(session_id);
    } catch (e) {
      console.error("Failed to start session:", e);
    } finally {
      setLoading(false);
    }
  }, [socket]);

  const handleStop = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      await stopSession(sessionId);
    } catch (e) {
      console.error("Failed to stop session:", e);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  const handleBookmark = useCallback(
    async (note: string) => {
      if (!sessionId) return;
      return createBookmark(sessionId, note);
    },
    [sessionId]
  );

  return {
    ...socket,
    sessionId,
    loading,
    start: handleStart,
    stop: handleStop,
    bookmark: handleBookmark,
  };
}
```

**Step 3: Implement UI components**

Create each component file. The engineer should create these in order:

`frontend/src/components/SourceStatus.tsx`:

```tsx
import type { SourceStatus as SourceStatusType, ModelStatus } from "../types";

interface Props {
  source: SourceStatusType;
  model: ModelStatus;
  connected: boolean;
}

const SOURCE_LABELS: Record<SourceStatusType, { label: string; color: string }> = {
  unknown: { label: "No source", color: "text-gray-500" },
  ready: { label: "Source ready", color: "text-yellow-400" },
  capturing: { label: "Capturing", color: "text-green-400" },
  unavailable: { label: "Source unavailable", color: "text-red-400" },
  interrupted: { label: "Source interrupted", color: "text-red-400" },
};

export function SourceStatus({ source, model, connected }: Props) {
  const s = SOURCE_LABELS[source];
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className={`flex items-center gap-1 ${s.color}`}>
        <span className="inline-block w-2 h-2 rounded-full bg-current" />
        {s.label}
      </span>
      <span className="text-gray-400">Model: {model}</span>
      {!connected && <span className="text-red-400">Disconnected</span>}
    </div>
  );
}
```

`frontend/src/components/ControlBar.tsx`:

```tsx
import type { SessionStatus } from "../types";
import { SourceStatus } from "./SourceStatus";
import type { SourceStatus as SourceStatusType, ModelStatus } from "../types";

interface Props {
  sessionStatus: SessionStatus;
  sourceStatus: SourceStatusType;
  modelStatus: ModelStatus;
  connected: boolean;
  loading: boolean;
  onStart: () => void;
  onStop: () => void;
  onBookmark: () => void;
}

export function ControlBar({
  sessionStatus,
  sourceStatus,
  modelStatus,
  connected,
  loading,
  onStart,
  onStop,
  onBookmark,
}: Props) {
  const isActive = sessionStatus === "active";
  const canStart = sessionStatus === "idle" || sessionStatus === "stopped";

  return (
    <div className="flex items-center justify-between px-6 py-3 bg-gray-900 border-b border-gray-800">
      <div className="flex items-center gap-4">
        <h1 className="text-lg font-bold text-white">Ribbet</h1>
        <SourceStatus source={sourceStatus} model={modelStatus} connected={connected} />
      </div>
      <div className="flex items-center gap-2">
        {isActive && (
          <button
            onClick={onBookmark}
            className="px-3 py-1.5 text-sm bg-amber-600 hover:bg-amber-500 text-white rounded"
          >
            Bookmark
          </button>
        )}
        {canStart ? (
          <button
            onClick={onStart}
            disabled={loading}
            className="px-4 py-1.5 text-sm bg-green-600 hover:bg-green-500 text-white rounded disabled:opacity-50"
          >
            {loading ? "Starting..." : "Start Session"}
          </button>
        ) : (
          <button
            onClick={onStop}
            disabled={loading || !isActive}
            className="px-4 py-1.5 text-sm bg-red-600 hover:bg-red-500 text-white rounded disabled:opacity-50"
          >
            {loading ? "Stopping..." : "Stop Session"}
          </button>
        )}
      </div>
    </div>
  );
}
```

`frontend/src/components/TranscriptStream.tsx`:

```tsx
import { useEffect, useRef } from "react";
import type { TranscriptSegment } from "../types";

interface Props {
  segments: TranscriptSegment[];
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function TranscriptStream({ segments }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [segments.length]);

  if (segments.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
        Transcript will appear here when a session is active...
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-2">
      {segments.map((seg) => (
        <div
          key={seg.id}
          className={`flex gap-3 ${seg.is_partial ? "opacity-60" : ""}`}
        >
          <span className="text-xs text-gray-500 font-mono min-w-[4rem] pt-0.5">
            {formatTime(seg.start_time)}
          </span>
          <p className="text-sm text-gray-200 leading-relaxed">{seg.text}</p>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
```

`frontend/src/components/TopicClusters.tsx`:

```tsx
import type { TopicCluster } from "../types";

interface Props {
  topics: TopicCluster[];
}

export function TopicClusters({ topics }: Props) {
  if (topics.length === 0) {
    return <p className="text-gray-500 text-xs">No topics detected yet</p>;
  }
  return (
    <div className="space-y-2">
      {topics.map((t, i) => (
        <div key={i} className="p-2 bg-gray-800 rounded">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-white">{t.label}</span>
            <span className="text-xs text-gray-400">
              {Math.round(t.prominence * 100)}%
            </span>
          </div>
          <div className="flex gap-1 mt-1 flex-wrap">
            {t.keywords.map((kw) => (
              <span key={kw} className="text-xs px-1.5 py-0.5 bg-gray-700 rounded text-gray-300">
                {kw}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
```

`frontend/src/components/ActionItems.tsx`:

```tsx
import type { ActionItem } from "../types";

interface Props {
  actions: ActionItem[];
}

export function ActionItems({ actions }: Props) {
  if (actions.length === 0) {
    return <p className="text-gray-500 text-xs">No action items detected yet</p>;
  }
  return (
    <ul className="space-y-1">
      {actions.map((a) => (
        <li key={a.id} className="text-sm text-gray-200 flex items-start gap-2">
          <span className="text-amber-400 mt-0.5">*</span>
          <span>{a.text}</span>
        </li>
      ))}
    </ul>
  );
}
```

`frontend/src/components/Decisions.tsx`:

```tsx
import type { Decision } from "../types";

interface Props {
  decisions: Decision[];
}

export function Decisions({ decisions }: Props) {
  if (decisions.length === 0) {
    return <p className="text-gray-500 text-xs">No decisions detected yet</p>;
  }
  return (
    <ul className="space-y-1">
      {decisions.map((d) => (
        <li key={d.id} className="text-sm text-gray-200 flex items-start gap-2">
          <span className="text-green-400 mt-0.5">!</span>
          <span>{d.text}</span>
        </li>
      ))}
    </ul>
  );
}
```

`frontend/src/components/InsightPanel.tsx`:

```tsx
import type { InsightSnapshot } from "../types";
import { TopicClusters } from "./TopicClusters";
import { ActionItems } from "./ActionItems";
import { Decisions } from "./Decisions";

interface Props {
  insights: InsightSnapshot;
}

export function InsightPanel({ insights }: Props) {
  return (
    <div className="flex flex-col gap-4 p-4 overflow-y-auto">
      {insights.stale && insights.last_updated && (
        <div className="text-xs text-amber-400 bg-amber-900/30 px-2 py-1 rounded">
          Insights may be stale
        </div>
      )}
      <section>
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Topics
        </h2>
        <TopicClusters topics={insights.topics} />
      </section>
      <section>
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Action Items
        </h2>
        <ActionItems actions={insights.actions} />
      </section>
      <section>
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Decisions
        </h2>
        <Decisions decisions={insights.decisions} />
      </section>
    </div>
  );
}
```

`frontend/src/components/BookmarkDialog.tsx`:

```tsx
import { useState } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  onSubmit: (note: string) => void;
}

export function BookmarkDialog({ open, onClose, onSubmit }: Props) {
  const [note, setNote] = useState("");

  if (!open) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (note.trim()) {
      onSubmit(note.trim());
      setNote("");
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <form
        onSubmit={handleSubmit}
        className="bg-gray-900 border border-gray-700 rounded-lg p-6 w-96 space-y-4"
      >
        <h2 className="text-lg font-bold text-white">Create Bookmark</h2>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="What's noteworthy right now?"
          className="w-full bg-gray-800 text-gray-200 border border-gray-700 rounded p-2 text-sm resize-none h-24"
          autoFocus
        />
        <div className="flex gap-2 justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-sm text-gray-400 hover:text-white"
          >
            Cancel
          </button>
          <button
            type="submit"
            className="px-3 py-1.5 text-sm bg-amber-600 hover:bg-amber-500 text-white rounded"
          >
            Save
          </button>
        </div>
      </form>
    </div>
  );
}
```

**Step 4: Wire up `App.tsx`**

```tsx
import { useState } from "react";
import { useSession } from "./hooks/useSession";
import { ControlBar } from "./components/ControlBar";
import { TranscriptStream } from "./components/TranscriptStream";
import { InsightPanel } from "./components/InsightPanel";
import { BookmarkDialog } from "./components/BookmarkDialog";

function App() {
  const session = useSession();
  const [bookmarkOpen, setBookmarkOpen] = useState(false);

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col">
      <ControlBar
        sessionStatus={session.sessionStatus}
        sourceStatus={session.sourceStatus}
        modelStatus={session.modelStatus}
        connected={session.connected}
        loading={session.loading}
        onStart={session.start}
        onStop={session.stop}
        onBookmark={() => setBookmarkOpen(true)}
      />
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Insights */}
        <div className="w-80 border-r border-gray-800 flex-shrink-0">
          <InsightPanel insights={session.insights} />
        </div>
        {/* Right: Transcript */}
        <div className="flex-1 flex flex-col">
          <TranscriptStream segments={session.segments} />
        </div>
      </div>
      <BookmarkDialog
        open={bookmarkOpen}
        onClose={() => setBookmarkOpen(false)}
        onSubmit={(note) => session.bookmark(note)}
      />
    </div>
  );
}

export default App;
```

**Step 5: Run frontend tests and dev server**

```bash
cd frontend
npx vitest run
npm run dev
```

Expected: Tests pass. Dev server shows the Ribbet UI at `http://localhost:5173`.

**Step 6: Commit**

```bash
git add frontend/
git commit -m "feat: add live session UI with transcript stream, insights panel, and bookmarks"
```

---

### Task 9: Insight Extraction Pipeline

**Files:**
- Create: `backend/ribbet/insights/__init__.py`
- Create: `backend/ribbet/insights/prompts.py`
- Create: `backend/ribbet/insights/extractor.py`
- Create: `backend/tests/test_insight_extractor.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_insight_extractor.py`:

```python
"""Tests for the insight extraction module."""

import pytest
import json
from ribbet.insights.prompts import build_insight_prompt, parse_insight_response
from ribbet.insights.extractor import InsightExtractor


def test_build_insight_prompt_includes_transcript():
    prompt = build_insight_prompt("We need to finish the budget report by Friday.")
    assert "budget report" in prompt
    assert "topics" in prompt.lower() or "topic" in prompt.lower()


def test_parse_insight_response_valid_json():
    raw = json.dumps({
        "topics": [{"label": "Budget", "prominence": 0.9, "keywords": ["budget", "report"]}],
        "actions": [{"text": "Finish budget report by Friday", "timestamp_hint": "recent"}],
        "decisions": [],
    })
    result = parse_insight_response(raw)
    assert len(result["topics"]) == 1
    assert result["topics"][0]["label"] == "Budget"
    assert len(result["actions"]) == 1


def test_parse_insight_response_malformed_returns_empty():
    result = parse_insight_response("this is not json at all")
    assert result["topics"] == []
    assert result["actions"] == []
    assert result["decisions"] == []


def test_parse_insight_response_extracts_json_from_markdown():
    raw = """Here are the insights:
```json
{
    "topics": [{"label": "Q3 Plan", "prominence": 0.7, "keywords": ["Q3", "plan"]}],
    "actions": [],
    "decisions": [{"text": "Approved Q3 plan", "timestamp_hint": "recent"}]
}
```
"""
    result = parse_insight_response(raw)
    assert len(result["topics"]) == 1
    assert len(result["decisions"]) == 1
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_insight_extractor.py -v
```

Expected: FAIL — import error.

**Step 3: Create `backend/ribbet/insights/__init__.py`**

```python
```

**Step 4: Implement `backend/ribbet/insights/prompts.py`**

```python
"""Prompt templates and response parsing for insight extraction."""

from __future__ import annotations

import json
import re


INSIGHT_SYSTEM_PROMPT = """You are a meeting analyst. Given a transcript excerpt, extract:

1. **Topics**: Main discussion topics with prominence (0.0-1.0) and keywords.
2. **Action Items**: Tasks that someone needs to do.
3. **Decisions**: Conclusions or agreements reached.

Respond ONLY with valid JSON in this exact format:
{
  "topics": [{"label": "Topic Name", "prominence": 0.8, "keywords": ["kw1", "kw2"]}],
  "actions": [{"text": "Description of action item", "timestamp_hint": "recent"}],
  "decisions": [{"text": "Description of decision", "timestamp_hint": "recent"}]
}

Rules:
- Be concise. Each item should be one sentence.
- Only include items clearly stated or implied in the transcript.
- If nothing is found for a category, use an empty array.
- Do NOT invent or hallucinate content.
"""


def build_insight_prompt(transcript_window: str) -> str:
    """Build the user prompt for insight extraction."""
    return f"""Analyze this meeting transcript excerpt and extract topics, action items, and decisions.

TRANSCRIPT:
{transcript_window}

Respond with JSON only."""


def parse_insight_response(raw: str) -> dict:
    """Parse the LLM response into structured insight data.

    Handles raw JSON, JSON wrapped in markdown code blocks, and malformed responses.
    """
    empty = {"topics": [], "actions": [], "decisions": []}

    # Try to extract JSON from markdown code blocks
    code_block_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    json_str = code_block_match.group(1).strip() if code_block_match else raw.strip()

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        return empty

    # Validate structure
    result = {
        "topics": parsed.get("topics", []),
        "actions": parsed.get("actions", []),
        "decisions": parsed.get("decisions", []),
    }

    # Validate each topic has required fields
    result["topics"] = [
        t for t in result["topics"]
        if isinstance(t, dict) and "label" in t
    ]
    for t in result["topics"]:
        t.setdefault("prominence", 0.5)
        t.setdefault("keywords", [])

    return result
```

**Step 5: Implement `backend/ribbet/insights/extractor.py`**

```python
"""LLM-based insight extraction using mlx-lm.

Runs on a background asyncio task, consuming transcript windows
and producing insight snapshots. Never blocks the transcription path.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from ribbet.config import settings
from ribbet.insights.prompts import (
    INSIGHT_SYSTEM_PROMPT,
    build_insight_prompt,
    parse_insight_response,
)

logger = logging.getLogger(__name__)


class InsightExtractor:
    """Extracts meeting insights from transcript text using a local LLM.

    Usage:
        extractor = InsightExtractor(model_name="mlx-community/Qwen2.5-3B-Instruct-4bit")
        await extractor.load()
        snapshot = await extractor.extract(transcript_window_text)
        await extractor.unload()
    """

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.insight_model
        self._model = None
        self._tokenizer = None
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    async def load(self) -> None:
        """Load the insight LLM. Runs in executor to avoid blocking."""
        logger.info("Loading insight model %s...", self.model_name)

        # Implementation note for the engineer:
        # from mlx_lm import load, generate
        # self._model, self._tokenizer = load(self.model_name)

        self._loaded = True
        logger.info("Insight model loaded")

    async def extract(self, transcript_window: str) -> dict:
        """Extract insights from a transcript window.

        Returns a dict with topics, actions, decisions keys.
        """
        if not self._loaded:
            raise RuntimeError("Model not loaded")

        if not transcript_window.strip():
            return {"topics": [], "actions": [], "decisions": []}

        prompt = build_insight_prompt(transcript_window)

        # Implementation note for the engineer:
        # Use mlx_lm.generate() with the system prompt + user prompt.
        # Run in asyncio.to_thread() to avoid blocking the event loop.
        #
        # messages = [
        #     {"role": "system", "content": INSIGHT_SYSTEM_PROMPT},
        #     {"role": "user", "content": prompt},
        # ]
        # formatted = self._tokenizer.apply_chat_template(messages, tokenize=False)
        # response = await asyncio.to_thread(
        #     generate, self._model, self._tokenizer, prompt=formatted, max_tokens=1024
        # )
        # return parse_insight_response(response)

        return {"topics": [], "actions": [], "decisions": []}

    async def unload(self) -> None:
        self._model = None
        self._tokenizer = None
        self._loaded = False
```

**Step 6: Run tests**

```bash
pytest tests/test_insight_extractor.py -v
```

Expected: All PASS.

**Step 7: Commit**

```bash
git add backend/ribbet/insights/ backend/tests/test_insight_extractor.py
git commit -m "feat: add insight extraction pipeline with prompt templates and LLM interface"
```

---

### Task 10: Bookmark REST Endpoint

**Files:**
- Create: `backend/ribbet/routers/bookmarks.py`
- Create: `backend/tests/test_bookmarks_router.py`
- Modify: `backend/ribbet/main.py` (register bookmark router)

**Step 1: Write the failing tests**

Create `backend/tests/test_bookmarks_router.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_bookmarks_router.py -v
```

Expected: FAIL.

**Step 3: Implement `backend/ribbet/routers/bookmarks.py`**

```python
"""Bookmark REST endpoints."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ribbet.config import settings
from ribbet.db import get_db
from ribbet.models import BookmarkCreate

router = APIRouter(tags=["bookmarks"])


@router.post("/sessions/{session_id}/bookmarks", status_code=201)
async def create_bookmark(session_id: str, body: BookmarkCreate):
    async with get_db(settings.db_path) as db:
        cursor = await db.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Session not found")

        bookmark_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Get latest transcript timestamp for the bookmark
        seg_cursor = await db.execute(
            "SELECT MAX(end_time) as ts FROM transcript_segments WHERE session_id = ?",
            (session_id,),
        )
        seg_row = await seg_cursor.fetchone()
        timestamp = seg_row["ts"] if seg_row and seg_row["ts"] is not None else 0.0

        # Build snippet from nearby transcript segments
        window_start = max(0, timestamp - settings.bookmark_snippet_seconds / 2)
        window_end = timestamp + settings.bookmark_snippet_seconds / 2
        snippet_cursor = await db.execute(
            """SELECT text FROM transcript_segments
               WHERE session_id = ? AND start_time >= ? AND start_time < ?
               ORDER BY start_time""",
            (session_id, window_start, window_end),
        )
        snippet_rows = await snippet_cursor.fetchall()
        snippet = " ".join(r["text"] for r in snippet_rows) if snippet_rows else ""

        await db.execute(
            """INSERT INTO bookmarks (id, session_id, timestamp, note, snippet, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (bookmark_id, session_id, timestamp, body.note, snippet, now),
        )
        await db.commit()

    return {
        "id": bookmark_id,
        "timestamp": timestamp,
        "note": body.note,
        "snippet": snippet,
        "created_at": now,
    }


@router.get("/sessions/{session_id}/bookmarks")
async def list_bookmarks(session_id: str):
    async with get_db(settings.db_path) as db:
        cursor = await db.execute(
            """SELECT id, timestamp, note, snippet, created_at
               FROM bookmarks WHERE session_id = ? ORDER BY timestamp""",
            (session_id,),
        )
        rows = await cursor.fetchall()
    return {
        "bookmarks": [
            {
                "id": r["id"],
                "timestamp": r["timestamp"],
                "note": r["note"],
                "snippet": r["snippet"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    }
```

**Step 4: Register bookmark router in `main.py`**

Add to `backend/ribbet/main.py`:

```python
from ribbet.routers import bookmarks

# ... after other router includes:
app.include_router(bookmarks.router)
```

**Step 5: Run tests**

```bash
pytest tests/ -v
```

Expected: All PASS.

**Step 6: Commit**

```bash
git add backend/ribbet/routers/bookmarks.py backend/tests/test_bookmarks_router.py backend/ribbet/main.py
git commit -m "feat: add bookmark creation and listing REST endpoints"
```

---

### Task 11: Transcript Persistence, Review, and Insight Regeneration

**Files:**
- Modify: `backend/ribbet/routers/sessions.py` (add transcript retrieval + insight regeneration endpoints)
- Create: `backend/tests/test_persistence.py`
- Create: `frontend/src/components/SessionList.tsx`
- Create: `frontend/src/components/SessionReview.tsx`

**Step 1: Write failing backend tests**

Create `backend/tests/test_persistence.py`:

```python
"""Tests for transcript persistence and review."""

import pytest
from httpx import ASGITransport, AsyncClient
from ribbet.main import app
from ribbet.config import settings
from ribbet.db import init_db, get_db


@pytest.fixture(autouse=True)
async def _setup_test_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "app_data_dir", tmp_path)
    await init_db(settings.db_path)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def stopped_session_with_segments(client):
    """Create a session, add segments directly, then stop it."""
    import uuid
    from datetime import datetime, timezone

    resp = await client.post("/sessions")
    sid = resp.json()["session_id"]

    # Insert segments directly into DB
    async with get_db(settings.db_path) as db:
        for i in range(5):
            await db.execute(
                """INSERT INTO transcript_segments
                   (id, session_id, text, start_time, end_time, is_partial, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    sid,
                    f"Segment {i} text content",
                    float(i * 10),
                    float(i * 10 + 9),
                    0,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        await db.commit()

    await client.post(f"/sessions/{sid}/stop")
    return sid


@pytest.mark.asyncio
async def test_get_session_transcript(client, stopped_session_with_segments):
    sid = stopped_session_with_segments
    resp = await client.get(f"/sessions/{sid}/transcript")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["segments"]) == 5
    assert body["segments"][0]["start_time"] == 0.0


@pytest.mark.asyncio
async def test_get_session_transcript_nonexistent(client):
    resp = await client.get("/sessions/fake/transcript")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_regenerate_insights_endpoint_exists(client, stopped_session_with_segments):
    sid = stopped_session_with_segments
    resp = await client.post(f"/sessions/{sid}/regenerate-insights")
    # May return 200 or 202 depending on implementation
    assert resp.status_code in (200, 202, 501)
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_persistence.py -v
```

Expected: FAIL — endpoints don't exist yet.

**Step 3: Add transcript and regeneration endpoints to sessions router**

Add to `backend/ribbet/routers/sessions.py`:

```python
@router.get("/{session_id}/transcript")
async def get_transcript(session_id: str):
    async with get_db(settings.db_path) as db:
        cursor = await db.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Session not found")

        seg_cursor = await db.execute(
            """SELECT id, text, start_time, end_time, is_partial
               FROM transcript_segments
               WHERE session_id = ?
               ORDER BY start_time""",
            (session_id,),
        )
        rows = await seg_cursor.fetchall()

    return {
        "session_id": session_id,
        "segments": [
            {
                "id": r["id"],
                "text": r["text"],
                "start_time": r["start_time"],
                "end_time": r["end_time"],
                "is_partial": bool(r["is_partial"]),
            }
            for r in rows
        ],
    }


@router.post("/{session_id}/regenerate-insights")
async def regenerate_insights(session_id: str):
    async with get_db(settings.db_path) as db:
        cursor = await db.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Session not found")

    # Implementation note for the engineer:
    # 1. Load full transcript from DB
    # 2. Run insight extractor on the full text
    # 3. Save new insight snapshot to insight_snapshots table
    # 4. Return the new snapshot
    #
    # For now, return 501 until the insight extractor is fully wired:
    raise HTTPException(
        status_code=501,
        detail="Insight regeneration not yet implemented. Wire InsightExtractor here.",
    )
```

**Step 4: Implement frontend review components**

Create `frontend/src/components/SessionList.tsx`:

```tsx
import { useEffect, useState } from "react";
import { listSessions } from "../api";
import type { SessionSummary } from "../types";

interface Props {
  onSelect: (sessionId: string) => void;
}

export function SessionList({ onSelect }: Props) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);

  useEffect(() => {
    listSessions().then((data) => setSessions(data.sessions));
  }, []);

  return (
    <div className="p-4 space-y-2">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
        Past Sessions
      </h2>
      {sessions.length === 0 && (
        <p className="text-gray-500 text-sm">No sessions yet</p>
      )}
      {sessions.map((s) => (
        <button
          key={s.id}
          onClick={() => onSelect(s.id)}
          className="w-full text-left p-3 bg-gray-800 hover:bg-gray-750 rounded space-y-1"
        >
          <div className="text-sm text-white">{new Date(s.started_at).toLocaleString()}</div>
          <div className="text-xs text-gray-400">
            {s.segment_count} segments &middot; {s.status}
          </div>
        </button>
      ))}
    </div>
  );
}
```

Create `frontend/src/components/SessionReview.tsx`:

```tsx
import { useEffect, useState } from "react";
import type { TranscriptSegment } from "../types";
import { TranscriptStream } from "./TranscriptStream";

interface Props {
  sessionId: string;
  onBack: () => void;
}

export function SessionReview({ sessionId, onBack }: Props) {
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/sessions/${sessionId}/transcript`)
      .then((r) => r.json())
      .then((data) => {
        setSegments(data.segments);
        setLoading(false);
      });
  }, [sessionId]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-4 p-4 border-b border-gray-800">
        <button onClick={onBack} className="text-sm text-gray-400 hover:text-white">
          Back
        </button>
        <h2 className="text-lg font-bold text-white">Session Review</h2>
      </div>
      {loading ? (
        <div className="flex-1 flex items-center justify-center text-gray-500">Loading...</div>
      ) : (
        <TranscriptStream segments={segments} />
      )}
    </div>
  );
}
```

**Step 5: Run all tests**

```bash
# Backend
cd backend && pytest tests/ -v

# Frontend
cd frontend && npx vitest run
```

Expected: All PASS.

**Step 6: Commit**

```bash
git add backend/ frontend/
git commit -m "feat: add transcript persistence, review endpoints, and session review UI"
```

---

### Task 12: Integration Wiring, Manual Validation, and Documentation

**Files:**
- Modify: `backend/ribbet/session/orchestrator.py` (wire real audio capture + STT + insights)
- Create: `README.md`

This is the final integration task. It connects the audio capture, transcription engine, and insight extractor into the session orchestrator's actual run loops.

**Step 1: Wire the capture → transcription → insight pipeline in the orchestrator**

Update `SessionOrchestrator.start_session()` to:

1. Check audio source via `SystemAudioCapture.check_availability()`
2. If unavailable → set `source_status = "unavailable"`, raise error with actionable message (REQ-009, REQ-010)
3. Load STT model via `TranscriptionEngine.load()` → update `model_status` through warmup
4. Start audio capture → feed chunks to STT engine → produce segments → broadcast via WS
5. Start insight extraction loop (every `insight_refresh_seconds`) → consume `result.recent_text()` → broadcast insight snapshots
6. On capture interruption → set `source_status = "interrupted"`, keep session alive (REQ failure handling)
7. On insight lag/failure → mark insights as stale, keep transcribing (REQ-023)

**Step 2: Wire `stop_session()` to persist transcript to DB**

When stopping:

1. Cancel capture and insight tasks
2. Write all `state.segments` to `transcript_segments` table
3. Write final insight snapshot to `insight_snapshots` table
4. Write bookmarks to `bookmarks` table
5. Update session status to "stopped" with `ended_at`

**Step 3: Install ML dependencies**

```bash
cd backend
pip install -e ".[ml]"
```

This installs `moshi_mlx`, `rustymimi`, `mlx-lm`, `pyobjc-framework-ScreenCaptureKit`.

Note: `moshi_mlx` and `mlx-lm` will download model weights on first run (~4GB for STT, ~2GB for insight LLM).

**Step 4: Manual validation checklist**

Run through each scenario manually on an Apple Silicon Mac:

- [ ] **Audio setup**: Grant Screen Recording permission. Verify `SystemAudioCapture.check_availability()` returns `True`.
- [ ] **Model loading**: Run `python -c "from ribbet.transcription.engine import TranscriptionEngine; ..."`. Verify weights download and model loads.
- [ ] **Live session**: Start both servers (`uvicorn` + `npm run dev`). Open `http://localhost:5173`. Start a session. Play audio through system speakers. Verify transcript appears within 2 seconds.
- [ ] **Insight extraction**: During a live session, verify topics/actions/decisions appear in the insight panel within 30-60 seconds.
- [ ] **Bookmarks**: During a live session, create a bookmark. Verify it stores note and transcript snippet.
- [ ] **Session stop + persistence**: Stop the session. Verify transcript is saved to SQLite. Verify session appears in session list.
- [ ] **Session review**: Click a past session. Verify full transcript loads.
- [ ] **Source unavailable**: Disconnect audio source before starting. Verify start is prevented with actionable message.
- [ ] **Insight lag**: Simulate slow insight extraction. Verify transcript continues updating. Verify "insights may be stale" indicator shows.

**Step 5: Create `README.md`**

```markdown
# Ribbet — Local Meeting Transcription

A single-user macOS webapp for live meeting transcription from system audio.
Runs entirely on your machine. No cloud dependency.

## Requirements

- macOS 13+ on Apple Silicon (M1/M2/M3/M4)
- Python 3.12+
- Node.js 20+
- Screen Recording permission (for system audio capture)

## Setup

### Backend

    cd backend
    python -m venv .venv
    source .venv/bin/activate
    pip install -e ".[dev,ml]"

### Frontend

    cd frontend
    npm install

## Running

### Start the backend

    cd backend
    source .venv/bin/activate
    uvicorn ribbet.main:app --host 127.0.0.1 --port 8000

### Start the frontend

    cd frontend
    npm run dev

Open http://localhost:5173

## Testing

    cd backend && pytest tests/ -v
    cd frontend && npx vitest run

## First Run

On the first run, model weights will be downloaded automatically:
- Kyutai STT 1B (~4GB)
- Qwen2.5-3B-Instruct-4bit (~2GB)

You will also need to grant Screen Recording permission when prompted.

## Architecture

See `docs/plans/2026-04-02-local-meeting-transcription-app.md` for the full
implementation plan and architecture overview.
```

**Step 6: Commit**

```bash
git add .
git commit -m "feat: wire integration pipeline, add README and manual validation checklist"
```

---

## Verification

- [ ] All backend tests pass: `cd backend && pytest tests/ -v`
- [ ] All frontend tests pass: `cd frontend && npx vitest run`
- [ ] Backend starts without errors: `uvicorn ribbet.main:app`
- [ ] Frontend starts and connects to backend: `npm run dev`
- [ ] Health endpoint responds: `curl http://127.0.0.1:8000/health`
- [ ] Session can be created and listed via REST
- [ ] WebSocket connection established from frontend
- [ ] Live transcript appears with <2s latency during manual test
- [ ] Insights update during a live session
- [ ] Bookmarks can be created with note + snippet
- [ ] Stopped session transcript persists in SQLite
- [ ] Past sessions can be reviewed in the UI
- [ ] Source unavailability prevents session start with clear message
- [ ] Insight lag does not block transcript updates
- [ ] No regressions in any test suite
