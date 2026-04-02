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
