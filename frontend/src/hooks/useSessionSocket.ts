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
  // Monotonically-incrementing generation counter. Each call to connect()
  // captures the generation at creation time. Handlers check that their
  // captured generation still matches the current one before mutating state,
  // so stale onclose/onerror callbacks from superseded sockets are ignored.
  const generationRef = useRef(0);

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
    // Close any existing socket first (cleanup without triggering stale handlers)
    if (wsRef.current) {
      const old = wsRef.current;
      // Nullify ref before closing so the old onclose cannot observe wsRef
      wsRef.current = null;
      old.close();
    }

    // Advance generation so any lingering handlers on the old socket are inert
    const generation = ++generationRef.current;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/session`);

    ws.onopen = () => {
      if (generationRef.current !== generation) return;
      setState((s) => ({ ...s, connected: true, error: null }));
    };

    ws.onmessage = (event) => {
      if (generationRef.current !== generation) return;
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

    ws.onclose = () => {
      if (generationRef.current !== generation) return;
      setState((s) => ({ ...s, connected: false }));
    };

    ws.onerror = () => {
      if (generationRef.current !== generation) return;
      setState((s) => ({ ...s, error: "WebSocket error" }));
    };

    wsRef.current = ws;
  }, []);

  const disconnect = useCallback(() => {
    // Advance generation to silence any in-flight handlers
    generationRef.current++;
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
