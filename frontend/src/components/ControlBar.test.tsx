import { render, screen, fireEvent } from "@testing-library/react";
import { ControlBar } from "./ControlBar";

const defaultProps = {
  sessionStatus: "idle" as const,
  sourceStatus: "unknown" as const,
  modelStatus: "cold" as const,
  connected: true,
  loading: false,
  onStart: vi.fn(),
  onStop: vi.fn(),
  onBookmark: vi.fn(),
};

describe("ControlBar", () => {
  it("shows Start Session button when idle", () => {
    render(<ControlBar {...defaultProps} />);
    expect(screen.getByRole("button", { name: /start session/i })).toBeInTheDocument();
  });

  it("shows Stop Session button when active", () => {
    render(<ControlBar {...defaultProps} sessionStatus="active" />);
    expect(screen.getByRole("button", { name: /stop session/i })).toBeInTheDocument();
  });

  it("shows Bookmark button only when active", () => {
    const { rerender } = render(<ControlBar {...defaultProps} sessionStatus="idle" />);
    expect(screen.queryByRole("button", { name: /bookmark/i })).toBeNull();

    rerender(<ControlBar {...defaultProps} sessionStatus="active" />);
    expect(screen.getByRole("button", { name: /bookmark/i })).toBeInTheDocument();
  });

  it("disables Start button while loading", () => {
    render(<ControlBar {...defaultProps} loading={true} />);
    expect(screen.getByRole("button", { name: /starting/i })).toBeDisabled();
  });

  it("calls onStart when Start Session clicked", () => {
    const onStart = vi.fn();
    render(<ControlBar {...defaultProps} onStart={onStart} />);
    fireEvent.click(screen.getByRole("button", { name: /start session/i }));
    expect(onStart).toHaveBeenCalledOnce();
  });

  it("calls onStop when Stop Session clicked", () => {
    const onStop = vi.fn();
    render(<ControlBar {...defaultProps} sessionStatus="active" onStop={onStop} />);
    fireEvent.click(screen.getByRole("button", { name: /stop session/i }));
    expect(onStop).toHaveBeenCalledOnce();
  });

  it("calls onBookmark when Bookmark clicked", () => {
    const onBookmark = vi.fn();
    render(<ControlBar {...defaultProps} sessionStatus="active" onBookmark={onBookmark} />);
    fireEvent.click(screen.getByRole("button", { name: /bookmark/i }));
    expect(onBookmark).toHaveBeenCalledOnce();
  });

  it("shows disconnected indicator when not connected", () => {
    render(<ControlBar {...defaultProps} connected={false} />);
    expect(screen.getByText(/disconnected/i)).toBeInTheDocument();
  });
});
