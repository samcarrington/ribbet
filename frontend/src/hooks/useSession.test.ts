import { renderHook, act, waitFor } from "@testing-library/react";
import { useSession } from "./useSession";

// ── WebSocket mock ────────────────────────────────────────────────────────────

class MockWebSocket {
  static instances: MockWebSocket[] = [];

  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(_url: string) {
    MockWebSocket.instances.push(this);
  }

  close() {
    this.closed = true;
  }

  emit(data: object) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}

function latestSocket() {
  return MockWebSocket.instances[MockWebSocket.instances.length - 1];
}

// ── API mock ──────────────────────────────────────────────────────────────────

vi.mock("../api", () => ({
  startSession: vi.fn().mockResolvedValue({ session_id: "sess-1" }),
  stopSession: vi.fn().mockResolvedValue(undefined),
  createBookmark: vi.fn().mockResolvedValue({ id: "bm-1", note: "x" }),
}));

beforeEach(() => {
  MockWebSocket.instances = [];
  vi.stubGlobal("WebSocket", MockWebSocket);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ── Helper: send a WS status message ─────────────────────────────────────────

function sendStatus(
  sock: MockWebSocket,
  session: string,
  source = "ready",
  model = "ready"
) {
  act(() => {
    sock.emit({ type: "status", session, source, model });
  });
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("useSession – resetSegments race fix", () => {
  it("segments are NOT cleared optimistically at start time", async () => {
    const { result } = renderHook(() => useSession());

    const sock = latestSocket();
    act(() => sock.onopen?.());

    // Some segments arrive before we call start
    act(() => {
      sock.emit({
        type: "transcript",
        segment: { id: "s1", text: "pre-existing", start_time: 0, end_time: 1, is_partial: false },
      });
    });
    expect(result.current.segments).toHaveLength(1);

    // Start the session — old code reset segments here; new code must NOT
    await act(async () => {
      void result.current.start();
    });

    // Segments should still be present immediately after start() resolves
    // (we haven't received the "active" status event yet)
    expect(result.current.segments).toHaveLength(1);
  });

  it("segments ARE cleared when status transitions to 'active'", async () => {
    const { result } = renderHook(() => useSession());

    const sock = latestSocket();
    act(() => sock.onopen?.());

    // Pre-existing segment from prior session
    act(() => {
      sock.emit({
        type: "transcript",
        segment: { id: "s0", text: "old", start_time: 0, end_time: 1, is_partial: false },
      });
    });
    expect(result.current.segments).toHaveLength(1);

    await act(async () => {
      void result.current.start();
    });

    // Server confirms session is now active
    sendStatus(sock, "active");

    await waitFor(() => expect(result.current.segments).toHaveLength(0));
  });

  it("trailing WS messages from prior session that arrive after start but before active are discarded on reset", async () => {
    const { result } = renderHook(() => useSession());

    const sock = latestSocket();
    act(() => sock.onopen?.());

    // 1. Prior session segment arrives
    act(() => {
      sock.emit({
        type: "transcript",
        segment: { id: "old-1", text: "old", start_time: 0, end_time: 1, is_partial: false },
      });
    });

    await act(async () => {
      void result.current.start();
    });

    // 2. Another trailing message from the prior session arrives AFTER start()
    act(() => {
      sock.emit({
        type: "transcript",
        segment: { id: "old-2", text: "trailing", start_time: 1, end_time: 2, is_partial: false },
      });
    });
    expect(result.current.segments).toHaveLength(2); // still accumulated

    // 3. "active" transition — both old segments should be wiped
    sendStatus(sock, "active");

    await waitFor(() => expect(result.current.segments).toHaveLength(0));
  });

  it("a second start() does not double-reset if status was already active", async () => {
    const { result } = renderHook(() => useSession());

    const sock = latestSocket();
    act(() => sock.onopen?.());

    await act(async () => void result.current.start());
    sendStatus(sock, "active");
    await waitFor(() => expect(result.current.segments).toHaveLength(0));

    // New segment arrives while active
    act(() => {
      sock.emit({
        type: "transcript",
        segment: { id: "n1", text: "new", start_time: 0, end_time: 1, is_partial: false },
      });
    });
    expect(result.current.segments).toHaveLength(1);

    // Second start without a status transition back through non-active
    await act(async () => void result.current.start());
    // Status goes active again (same value → no transition, no reset)
    sendStatus(sock, "active");

    // Segment should still be there — only a genuine idle→active transition resets
    await waitFor(() => expect(result.current.segments).toHaveLength(1));
  });
});
