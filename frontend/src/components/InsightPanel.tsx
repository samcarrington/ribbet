import type { InsightSnapshot } from "../types";
import { TopicClusters } from "./TopicClusters";
import { ActionItems } from "./ActionItems";
import { Decisions } from "./Decisions";

interface Props {
  insights: InsightSnapshot;
}

export function InsightPanel({ insights }: Props) {
  return (
    <div className="flex flex-col gap-4 p-4 overflow-y-auto">
      {insights.stale && insights.last_updated && (
        <div className="text-xs text-amber-400 bg-amber-900/30 px-2 py-1 rounded">
          Insights may be stale
        </div>
      )}
      <section>
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Topics
        </h2>
        <TopicClusters topics={insights.topics} />
      </section>
      <section>
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Action Items
        </h2>
        <ActionItems actions={insights.actions} />
      </section>
      <section>
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Decisions
        </h2>
        <Decisions decisions={insights.decisions} />
      </section>
    </div>
  );
}
