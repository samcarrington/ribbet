import { useEffect, useRef, useCallback, useState } from "react";
import type {
  WsMessage,
  TranscriptSegment,
  InsightSnapshot,
  SessionStatus,
  SourceStatus,
  ModelStatus,
} from "../types";

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
