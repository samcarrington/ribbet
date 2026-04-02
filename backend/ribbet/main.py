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
