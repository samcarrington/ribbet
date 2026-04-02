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
