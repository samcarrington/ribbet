import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import App from "./App";

// Mock WebSocket constructor so the useSessionSocket hook doesn't fail in jsdom
function MockWebSocket(this: WebSocket) {
  // no-op constructor
}
MockWebSocket.prototype.send = vi.fn();
MockWebSocket.prototype.close = vi.fn();
vi.stubGlobal("WebSocket", MockWebSocket);

test("renders app title in control bar", () => {
  render(<App />);
  expect(screen.getByText("Ribbet")).toBeInTheDocument();
});

test("renders Start Session button when idle", () => {
  render(<App />);
  expect(screen.getByRole("button", { name: /start session/i })).toBeInTheDocument();
});

test("renders transcript placeholder when no segments", () => {
  render(<App />);
  expect(screen.getByText(/transcript will appear here/i)).toBeInTheDocument();
});

test("renders insight panel sections", () => {
  render(<App />);
  expect(screen.getByText("Topics")).toBeInTheDocument();
  expect(screen.getByText("Action Items")).toBeInTheDocument();
  expect(screen.getByText("Decisions")).toBeInTheDocument();
});
