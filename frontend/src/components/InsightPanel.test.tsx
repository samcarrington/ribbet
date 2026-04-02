import { render, screen } from "@testing-library/react";
import { InsightPanel } from "./InsightPanel";
import type { InsightSnapshot } from "../types";

const emptyInsights: InsightSnapshot = {
  topics: [],
  actions: [],
  decisions: [],
  stale: true,
  last_updated: null,
};

describe("InsightPanel", () => {
  it("renders empty state for all sections", () => {
    render(<InsightPanel insights={emptyInsights} />);
    expect(screen.getByText("No topics detected yet")).toBeInTheDocument();
    expect(screen.getByText("No action items detected yet")).toBeInTheDocument();
    expect(screen.getByText("No decisions detected yet")).toBeInTheDocument();
  });

  it("does not show stale indicator when no last_updated", () => {
    render(<InsightPanel insights={emptyInsights} />);
    expect(screen.queryByText(/stale/i)).toBeNull();
  });

  it("shows stale indicator when stale and has last_updated", () => {
    const insights = { ...emptyInsights, stale: true, last_updated: "2026-04-02T10:00:00Z" };
    render(<InsightPanel insights={insights} />);
    expect(screen.getByText(/may be stale/i)).toBeInTheDocument();
  });

  it("renders topic clusters", () => {
    const insights: InsightSnapshot = {
      ...emptyInsights,
      stale: false,
      topics: [{ label: "Budget", prominence: 0.8, keywords: ["budget", "cost"] }],
    };
    render(<InsightPanel insights={insights} />);
    expect(screen.getByText("Budget")).toBeInTheDocument();
    expect(screen.getByText("80%")).toBeInTheDocument();
    expect(screen.getByText("budget")).toBeInTheDocument();
  });

  it("renders action items", () => {
    const insights: InsightSnapshot = {
      ...emptyInsights,
      stale: false,
      actions: [{ id: "a1", text: "Review the budget", timestamp: 60 }],
    };
    render(<InsightPanel insights={insights} />);
    expect(screen.getByText("Review the budget")).toBeInTheDocument();
  });

  it("renders decisions", () => {
    const insights: InsightSnapshot = {
      ...emptyInsights,
      stale: false,
      decisions: [{ id: "d1", text: "Approved Q3 plan", timestamp: 120 }],
    };
    render(<InsightPanel insights={insights} />);
    expect(screen.getByText("Approved Q3 plan")).toBeInTheDocument();
  });
});
