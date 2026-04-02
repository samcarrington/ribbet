import { useState, useCallback, useEffect, useRef } from "react";
import { startSession, stopSession, createBookmark } from "../api";
import { useSessionSocket } from "./useSessionSocket";

export function useSession() {
  const socket = useSessionSocket();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Track the sessionStatus we last observed so we can detect the transition
  // into "active". We use a ref so the effect doesn't need it as a dependency.
  const prevSessionStatusRef = useRef(socket.sessionStatus);

  // Reset segments when the server confirms the new session is active,
  // rather than optimistically at handleStart time. This avoids a race where
  // trailing WebSocket messages from the prior session arrive after the reset
  // and then get wiped a second time (or where the reset clears messages that
  // already arrived for the new session before the HTTP response returned).
  useEffect(() => {
    const prev = prevSessionStatusRef.current;
    const curr = socket.sessionStatus;
    prevSessionStatusRef.current = curr;

    if (prev !== "active" && curr === "active") {
      socket.resetSegments();
    }
  }, [socket.sessionStatus, socket.resetSegments]);

  const handleStart = useCallback(async () => {
    setLoading(true);
    try {
      const { session_id } = await startSession();
      setSessionId(session_id);
    } catch (e) {
      console.error("Failed to start session:", e);
    } finally {
      setLoading(false);
    }
  }, []);

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
