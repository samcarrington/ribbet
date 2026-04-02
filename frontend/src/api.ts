/** REST API helpers. */

const BASE = "/api";

export async function startSession(): Promise<{ session_id: string }> {
  const res = await fetch(`${BASE}/sessions`, { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function stopSession(sessionId: string): Promise<void> {
  const res = await fetch(`${BASE}/sessions/${sessionId}/stop`, { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
}

export async function listSessions(): Promise<{ sessions: import("./types").SessionSummary[] }> {
  const res = await fetch(`${BASE}/sessions`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function createBookmark(
  sessionId: string,
  note: string
): Promise<import("./types").Bookmark> {
  const res = await fetch(`${BASE}/sessions/${sessionId}/bookmarks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
