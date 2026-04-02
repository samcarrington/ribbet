import type { TopicCluster } from "../types";

interface Props {
  topics: TopicCluster[];
}

export function TopicClusters({ topics }: Props) {
  if (topics.length === 0) {
    return <p className="text-gray-500 text-xs">No topics detected yet</p>;
  }
  return (
    <div className="space-y-2">
      {topics.map((t) => (
        <div key={t.label} className="p-2 bg-gray-800 rounded">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-white">{t.label}</span>
            <span className="text-xs text-gray-400">
              {Math.round(t.prominence * 100)}%
            </span>
          </div>
          <div className="flex gap-1 mt-1 flex-wrap">
            {t.keywords.map((kw) => (
              <span key={kw} className="text-xs px-1.5 py-0.5 bg-gray-700 rounded text-gray-300">
                {kw}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
