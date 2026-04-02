import type { SessionStatus, SourceStatus as SourceStatusType, ModelStatus } from "../types";
import { SourceStatus } from "./SourceStatus";

interface Props {
  sessionStatus: SessionStatus;
  sourceStatus: SourceStatusType;
  modelStatus: ModelStatus;
  connected: boolean;
  loading: boolean;
  onStart: () => void;
  onStop: () => void;
  onBookmark: () => void;
}

export function ControlBar({
  sessionStatus,
  sourceStatus,
  modelStatus,
  connected,
  loading,
  onStart,
  onStop,
  onBookmark,
}: Props) {
  const isActive = sessionStatus === "active";
  const canStart = sessionStatus === "idle" || sessionStatus === "stopped";

  return (
    <div className="flex items-center justify-between px-6 py-3 bg-gray-900 border-b border-gray-800">
      <div className="flex items-center gap-4">
        <h1 className="text-lg font-bold text-white">Ribbet</h1>
        <SourceStatus source={sourceStatus} model={modelStatus} connected={connected} />
      </div>
      <div className="flex items-center gap-2">
        {isActive && (
          <button
            type="button"
            onClick={onBookmark}
            className="px-3 py-1.5 text-sm bg-amber-600 hover:bg-amber-500 text-white rounded"
          >
            Bookmark
          </button>
        )}
        {canStart ? (
          <button
            type="button"
            onClick={onStart}
            disabled={loading}
            className="px-4 py-1.5 text-sm bg-green-600 hover:bg-green-500 text-white rounded disabled:opacity-50"
          >
            {loading ? "Starting..." : "Start Session"}
          </button>
        ) : (
          <button
            type="button"
            onClick={onStop}
            disabled={loading || !isActive}
            className="px-4 py-1.5 text-sm bg-red-600 hover:bg-red-500 text-white rounded disabled:opacity-50"
          >
            {loading ? "Stopping..." : "Stop Session"}
          </button>
        )}
      </div>
    </div>
  );
}
