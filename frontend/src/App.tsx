import { useState } from "react";
import { useSession } from "./hooks/useSession";
import { ControlBar } from "./components/ControlBar";
import { TranscriptStream } from "./components/TranscriptStream";
import { InsightPanel } from "./components/InsightPanel";
import { BookmarkDialog } from "./components/BookmarkDialog";

function App() {
  const session = useSession();
  const [bookmarkOpen, setBookmarkOpen] = useState(false);

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
        {/* Left: Insights */}
        <div className="w-80 border-r border-gray-800 flex-shrink-0">
          <InsightPanel insights={session.insights} />
        </div>
        {/* Right: Transcript */}
        <div className="flex-1 flex flex-col">
          <TranscriptStream segments={session.segments} />
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
