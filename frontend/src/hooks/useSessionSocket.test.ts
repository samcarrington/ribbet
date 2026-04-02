import { renderHook, act } from "@testing-library/react";
import { useSessionSocket } from "./useSessionSocket";

// Minimal mock WebSocket that captures handlers and lets tests drive them
class MockWebSocket {
  static instances: MockWebSocket[] = [];

  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  readonly url: string;
  closed = false;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  close() {
    this.closed = true;
    // Intentionally do NOT fire onclose here; the real browser behaviour is
    // async, and our fix must not rely on it being called.
  }

  /** Helper: simulate server sending a message */
  emit(data: object) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}

function latestSocket() {
  return MockWebSocket.instances[MockWebSocket.instances.length - 1];
}

beforeEach(() => {
  MockWebSocket.instances = [];
  vi.stubGlobal("WebSocket", MockWebSocket);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useSessionSocket – stale-socket guard", () => {
  it("initial connection sets connected=true on open", () => {
    const { result } = renderHook(() => useSessionSocket());

    act(() => {
      latestSocket().onopen?.();
    });

    expect(result.current.connected).toBe(true);
  });

  it("onclose from stale socket does NOT set connected=false after reconnect", () => {
    const { result } = renderHook(() => useSessionSocket());

    // Open the first socket
    const firstSocket = latestSocket();
    act(() => firstSocket.onopen?.());
    expect(result.current.connected).toBe(true);

    // Trigger reconnect — this should close the old socket and open a new one
    act(() => result.current.reconnect());

    const secondSocket = latestSocket();
    expect(secondSocket).not.toBe(firstSocket);

    // Open the second socket so connected goes true again
    act(() => secondSocket.onopen?.());
    expect(result.current.connected).toBe(true);

    // NOW fire onclose on the FIRST (stale) socket — must be ignored
    act(() => firstSocket.onclose?.());

    expect(result.current.connected).toBe(true); // still true
  });

  it("onerror from stale socket does NOT overwrite error state after reconnect", () => {
    const { result } = renderHook(() => useSessionSocket());

    const firstSocket = latestSocket();
    act(() => firstSocket.onopen?.());

    act(() => result.current.reconnect());

    const secondSocket = latestSocket();
    act(() => secondSocket.onopen?.());
    expect(result.current.error).toBeNull();

    // Stale socket fires onerror — should be ignored
    act(() => firstSocket.onerror?.());

    expect(result.current.error).toBeNull();
  });

  it("onmessage from stale socket does NOT append segments after reconnect", () => {
    const { result } = renderHook(() => useSessionSocket());

    const firstSocket = latestSocket();
    act(() => firstSocket.onopen?.());

    // Reconnect, wipe segments via resetSegments
    act(() => result.current.reconnect());
    act(() => result.current.resetSegments());

    const staleMsg = {
      type: "transcript",
      segment: { id: "s1", text: "stale", start_time: 0, end_time: 1, is_partial: false },
    };

    // Stale socket message arrives after reconnect — must be ignored
    act(() => firstSocket.emit(staleMsg));

    expect(result.current.segments).toHaveLength(0);
  });

  it("valid socket messages after reconnect are processed normally", () => {
    const { result } = renderHook(() => useSessionSocket());

    act(() => result.current.reconnect());

    const freshSocket = latestSocket();
    act(() => freshSocket.onopen?.());

    act(() => {
      freshSocket.emit({
        type: "transcript",
        segment: { id: "s1", text: "hello", start_time: 0, end_time: 1, is_partial: false },
      });
    });

    expect(result.current.segments).toHaveLength(1);
    expect(result.current.segments[0].text).toBe("hello");
  });

  it("disconnect advances generation so subsequent onclose is ignored", () => {
    const { result, unmount } = renderHook(() => useSessionSocket());

    const sock = latestSocket();
    act(() => sock.onopen?.());
    expect(result.current.connected).toBe(true);

    unmount(); // triggers disconnect via cleanup

    // onclose fires after unmount — must not throw or update state
    expect(() => act(() => sock.onclose?.())).not.toThrow();
  });
});
