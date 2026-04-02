import { useEffect, useRef } from "react";
import type { TranscriptSegment } from "../types";

interface Props {
  segments: TranscriptSegment[];
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function TranscriptStream({ segments }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const count = segments.length;

  // Scroll to bottom whenever a new segment is appended.
  // count is a derived scalar from segments to satisfy the linter while
  // still triggering on every new segment arrival.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [count]);

  if (segments.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
        Transcript will appear here when a session is active...
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-2">
      {segments.map((seg) => (
        <div
          key={seg.id}
          className={`flex gap-3 ${seg.is_partial ? "opacity-60" : ""}`}
        >
          <span className="text-xs text-gray-500 font-mono min-w-[4rem] pt-0.5">
            {formatTime(seg.start_time)}
          </span>
          <p className="text-sm text-gray-200 leading-relaxed">{seg.text}</p>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
