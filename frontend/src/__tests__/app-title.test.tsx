import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "@/App";

vi.mock("@/components/Brain", () => ({ Brain: () => <div>brain</div> }));
vi.mock("@/components/BrainHealthCard", () => ({ BrainHealthCard: () => <div /> }));
vi.mock("@/components/QueryBar", () => ({ QueryBar: () => <div /> }));
vi.mock("@/components/EdgeLegend", () => ({ EdgeLegend: () => <div /> }));
vi.mock("@/components/EntityInspector", () => ({ EntityInspector: () => <div /> }));
vi.mock("@/components/StatusFooter", () => ({ StatusFooter: () => <div /> }));
vi.mock("@/components/CommandPalette", () => ({ CommandPalette: () => <div /> }));
vi.mock("@/lib/websocket", () => ({
  BrainSocket: class {
    onStatus() {
      return () => {};
    }
    start() {}
    close() {}
  },
}));

describe("App shell", () => {
  beforeEach(() => {
    window.history.pushState({}, "", "/settings");
  });

  it("renders studio nav and settings heading", () => {
    render(<App />);
    expect(screen.getByText("AXIOM")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
  });
});
