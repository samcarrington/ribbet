import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { SessionReview } from "./SessionReview";
import * as api from "../api";

describe("SessionReview", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("shows loading state initially", () => {
    vi.spyOn(api, "getSessionTranscript").mockReturnValue(new Promise(() => {}));
    render(<SessionReview sessionId="s1" onBack={vi.fn()} />);
    expect(screen.getByText(/loading transcript/i)).toBeInTheDocument();
  });

  it("renders the session review heading", async () => {
    vi.spyOn(api, "getSessionTranscript").mockResolvedValue({
      session_id: "s1",
      segments: [],
    });
    render(<SessionReview sessionId="s1" onBack={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("Session Review")).toBeInTheDocument());
  });

  it("renders transcript segments when loaded", async () => {
    vi.spyOn(api, "getSessionTranscript").mockResolvedValue({
      session_id: "s1",
      segments: [
        { id: "seg1", text: "Hello world", start_time: 0.0, end_time: 1.5, is_partial: false },
        { id: "seg2", text: "Second segment", start_time: 1.5, end_time: 3.0, is_partial: false },
      ],
    });
    render(<SessionReview sessionId="s1" onBack={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("Hello world")).toBeInTheDocument());
    expect(screen.getByText("Second segment")).toBeInTheDocument();
  });

  it("shows error when getSessionTranscript fails", async () => {
    vi.spyOn(api, "getSessionTranscript").mockRejectedValue(new Error("Not found"));
    render(<SessionReview sessionId="s1" onBack={vi.fn()} />);
    await waitFor(() => expect(screen.getByText(/not found/i)).toBeInTheDocument());
  });

  it("calls onBack when back button is clicked", async () => {
    const onBack = vi.fn();
    vi.spyOn(api, "getSessionTranscript").mockResolvedValue({
      session_id: "s1",
      segments: [],
    });
    render(<SessionReview sessionId="s1" onBack={onBack} />);
    await waitFor(() => screen.getByRole("button", { name: /back/i }));
    await userEvent.click(screen.getByRole("button", { name: /back/i }));
    expect(onBack).toHaveBeenCalled();
  });

  it("shows empty transcript message for sessions with no segments", async () => {
    vi.spyOn(api, "getSessionTranscript").mockResolvedValue({
      session_id: "s1",
      segments: [],
    });
    render(<SessionReview sessionId="s1" onBack={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByText(/transcript will appear here/i)).toBeInTheDocument()
    );
  });

  it("re-fetches when sessionId changes", async () => {
    const spy = vi.spyOn(api, "getSessionTranscript").mockResolvedValue({
      session_id: "s1",
      segments: [],
    });
    const { rerender } = render(<SessionReview sessionId="s1" onBack={vi.fn()} />);
    await waitFor(() => expect(spy).toHaveBeenCalledWith("s1"));

    spy.mockResolvedValue({ session_id: "s2", segments: [] });
    rerender(<SessionReview sessionId="s2" onBack={vi.fn()} />);
    await waitFor(() => expect(spy).toHaveBeenCalledWith("s2"));
    expect(spy).toHaveBeenCalledTimes(2);
  });
});
