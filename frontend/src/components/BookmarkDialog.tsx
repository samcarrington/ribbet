import { useState, useEffect } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  onSubmit: (note: string) => void;
}

export function BookmarkDialog({ open, onClose, onSubmit }: Props) {
  const [note, setNote] = useState("");

  // Clear stale note whenever the dialog transitions to open so that
  // re-opening after a previous session never shows leftover text.
  useEffect(() => {
    if (open) {
      setNote("");
    }
  }, [open]);

  if (!open) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (note.trim()) {
      onSubmit(note.trim());
      setNote("");
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <form
        onSubmit={handleSubmit}
        className="bg-gray-900 border border-gray-700 rounded-lg p-6 w-96 space-y-4"
      >
        <h2 className="text-lg font-bold text-white">Create Bookmark</h2>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="What's noteworthy right now?"
          className="w-full bg-gray-800 text-gray-200 border border-gray-700 rounded p-2 text-sm resize-none h-24"
          ref={(el) => el?.focus()}
        />
        <div className="flex gap-2 justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-sm text-gray-400 hover:text-white"
          >
            Cancel
          </button>
          <button
            type="submit"
            className="px-3 py-1.5 text-sm bg-amber-600 hover:bg-amber-500 text-white rounded"
          >
            Save
          </button>
        </div>
      </form>
    </div>
  );
}
