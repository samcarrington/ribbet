import { useEffect, useState } from "react";
import type { TranscriptSegment } from "../types";
import { getSessionTranscript } from "../api";
import { TranscriptStream } from "./TranscriptStream";

interface Props {
  sessionId: string;
  onBack: () => void;
}

export function SessionReview({ sessionId, onBack }: Props) {
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getSessionTranscript(sessionId)
      .then((data) => setSegments(data.segments))
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Failed to load transcript")
      )
      .finally(() => setLoading(false));
  }, [sessionId]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-4 p-4 border-b border-gray-800">
        <button
          type="button"
          onClick={onBack}
          className="text-sm text-gray-400 hover:text-white"
        >
          ← Back
        </button>
        <h2 className="text-lg font-bold text-white">Session Review</h2>
      </div>
      {loading && (
        <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
          Loading transcript...
        </div>
      )}
      {!loading && error && (
        <div className="flex-1 flex items-center justify-center text-red-400 text-sm">
          Error: {error}
        </div>
      )}
      {!loading && !error && <TranscriptStream segments={segments} />}
    </div>
  );
}
