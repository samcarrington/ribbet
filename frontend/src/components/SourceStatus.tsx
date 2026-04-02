import type { SourceStatus as SourceStatusType, ModelStatus } from "../types";

interface Props {
  source: SourceStatusType;
  model: ModelStatus;
  connected: boolean;
}

const SOURCE_LABELS: Record<SourceStatusType, { label: string; color: string }> = {
  unknown: { label: "No source", color: "text-gray-500" },
  ready: { label: "Source ready", color: "text-yellow-400" },
  capturing: { label: "Capturing", color: "text-green-400" },
  unavailable: { label: "Source unavailable", color: "text-red-400" },
  interrupted: { label: "Source interrupted", color: "text-red-400" },
};

export function SourceStatus({ source, model, connected }: Props) {
  const s = SOURCE_LABELS[source];
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className={`flex items-center gap-1 ${s.color}`}>
        <span className="inline-block w-2 h-2 rounded-full bg-current" />
        {s.label}
      </span>
      <span className="text-gray-400">Model: {model}</span>
      {!connected && <span className="text-red-400">Disconnected</span>}
    </div>
  );
}
