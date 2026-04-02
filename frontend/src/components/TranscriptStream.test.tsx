import { render, screen } from "@testing-library/react";
import { TranscriptStream } from "./TranscriptStream";
import type { TranscriptSegment } from "../types";

const makeSegment = (id: string, text: string, partial = false): TranscriptSegment => ({
  id,
  text,
  start_time: 0,
  end_time: 1,
  is_partial: partial,
});

describe("TranscriptStream", () => {
  it("shows placeholder when empty", () => {
    render(<TranscriptStream segments={[]} />);
    expect(screen.getByText(/transcript will appear here/i)).toBeInTheDocument();
  });

  it("renders segment text", () => {
    render(<TranscriptStream segments={[makeSegment("1", "Hello world")]} />);
    expect(screen.getByText("Hello world")).toBeInTheDocument();
  });

  it("renders multiple segments", () => {
    const segments = [
      makeSegment("1", "First segment"),
      makeSegment("2", "Second segment"),
    ];
    render(<TranscriptStream segments={segments} />);
    expect(screen.getByText("First segment")).toBeInTheDocument();
    expect(screen.getByText("Second segment")).toBeInTheDocument();
  });

  it("applies reduced opacity to partial segments", () => {
    render(<TranscriptStream segments={[makeSegment("1", "Partial text", true)]} />);
    const row = screen.getByText("Partial text").closest(".flex");
    expect(row).toHaveClass("opacity-60");
  });

  it("formats timestamp correctly", () => {
    const seg: TranscriptSegment = { ...makeSegment("1", "Test"), start_time: 90 };
    render(<TranscriptStream segments={[seg]} />);
    expect(screen.getByText("1:30")).toBeInTheDocument();
  });
});
