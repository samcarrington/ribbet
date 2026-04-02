import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { SessionList } from "./SessionList";
import * as api from "../api";

describe("SessionList", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("shows loading state initially", () => {
    vi.spyOn(api, "listSessions").mockReturnValue(new Promise(() => {}));
    render(<SessionList onSelect={vi.fn()} />);
    expect(screen.getByText(/loading sessions/i)).toBeInTheDocument();
  });

  it("renders empty state when no sessions returned", async () => {
    vi.spyOn(api, "listSessions").mockResolvedValue({ sessions: [] });
    render(<SessionList onSelect={vi.fn()} />);
    await waitFor(() => expect(screen.getByText(/no sessions yet/i)).toBeInTheDocument());
  });

  it("renders a list of sessions", async () => {
    vi.spyOn(api, "listSessions").mockResolvedValue({
      sessions: [
        {
          id: "s1",
          started_at: "2026-04-02T10:00:00.000Z",
          ended_at: "2026-04-02T10:30:00.000Z",
          status: "stopped",
          segment_count: 42,
        },
      ],
    });
    render(<SessionList onSelect={vi.fn()} />);
    await waitFor(() => expect(screen.getByText(/42 segments/i)).toBeInTheDocument());
    expect(screen.getByText(/stopped/i)).toBeInTheDocument();
  });

  it("calls onSelect with session id when a session is clicked", async () => {
    const onSelect = vi.fn();
    vi.spyOn(api, "listSessions").mockResolvedValue({
      sessions: [
        {
          id: "s1",
          started_at: "2026-04-02T10:00:00.000Z",
          ended_at: null,
          status: "active",
          segment_count: 5,
        },
      ],
    });
    render(<SessionList onSelect={onSelect} />);
    await waitFor(() => expect(screen.getByText(/5 segments/i)).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /segments/i }));
    expect(onSelect).toHaveBeenCalledWith("s1");
  });

  it("shows error state when listSessions fails", async () => {
    vi.spyOn(api, "listSessions").mockRejectedValue(new Error("Network error"));
    render(<SessionList onSelect={vi.fn()} />);
    await waitFor(() => expect(screen.getByText(/network error/i)).toBeInTheDocument());
  });
});
