import { useState } from "react";
import { useSession } from "./hooks/useSession";
import { ControlBar } from "./components/ControlBar";
import { TranscriptStream } from "./components/TranscriptStream";
import { InsightPanel } from "./components/InsightPanel";
import { BookmarkDialog } from "./components/BookmarkDialog";
import { SessionList } from "./components/SessionList";
import { SessionReview } from "./components/SessionReview";

function App() {
  const session = useSession();
  const [bookmarkOpen, setBookmarkOpen] = useState(false);
  const [reviewSessionId, setReviewSessionId] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col">
      <ControlBar
        sessionStatus={session.sessionStatus}
        sourceStatus={session.sourceStatus}
        modelStatus={session.modelStatus}
        connected={session.connected}
        loading={session.loading}
        onStart={session.start}
        onStop={session.stop}
        onBookmark={() => setBookmarkOpen(true)}
      />
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Insights or session history */}
        <div className="w-80 border-r border-gray-800 flex-shrink-0 overflow-y-auto">
          <div className="border-b border-gray-800 px-4 py-2 flex gap-2">
            <button
              type="button"
              onClick={() => { setShowHistory(false); setReviewSessionId(null); }}
              className={`text-xs px-2 py-1 rounded ${!showHistory ? "bg-gray-700 text-white" : "text-gray-400 hover:text-white"}`}
            >
              Insights
            </button>
            <button
              type="button"
              onClick={() => setShowHistory(true)}
              className={`text-xs px-2 py-1 rounded ${showHistory ? "bg-gray-700 text-white" : "text-gray-400 hover:text-white"}`}
            >
              History
            </button>
          </div>
          {showHistory ? (
            <SessionList onSelect={(id) => { setReviewSessionId(id); }} />
          ) : (
            <InsightPanel insights={session.insights} />
          )}
        </div>
        {/* Right: Transcript or session review */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {reviewSessionId ? (
            <SessionReview
              sessionId={reviewSessionId}
              onBack={() => setReviewSessionId(null)}
            />
          ) : (
            <TranscriptStream segments={session.segments} />
          )}
        </div>
      </div>
      <BookmarkDialog
        open={bookmarkOpen}
        onClose={() => setBookmarkOpen(false)}
        onSubmit={(note) => { void session.bookmark(note); }}
      />
    </div>
  );
}

export default App;

