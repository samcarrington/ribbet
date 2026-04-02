import { useEffect, useState } from "react";
import { listSessions } from "../api";
import type { SessionSummary } from "../types";

interface Props {
  onSelect: (sessionId: string) => void;
}

export function SessionList({ onSelect }: Props) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listSessions()
      .then((data) => setSessions(data.sessions))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="p-4 text-gray-500 text-sm">Loading sessions...</div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-red-400 text-sm">Error: {error}</div>
    );
  }

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
          type="button"
          onClick={() => onSelect(s.id)}
          className="w-full text-left p-3 bg-gray-800 hover:bg-gray-700 rounded space-y-1"
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
