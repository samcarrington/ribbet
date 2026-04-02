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
