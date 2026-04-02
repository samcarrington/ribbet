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
