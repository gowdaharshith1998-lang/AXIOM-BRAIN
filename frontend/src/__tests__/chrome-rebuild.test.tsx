import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BrainHealthCard } from "@/components/BrainHealthCard";
import { EdgeLegend } from "@/components/EdgeLegend";
import { EntityInspector } from "@/components/EntityInspector";
import { NavRail } from "@/components/NavRail";
import { QueryBar } from "@/components/QueryBar";
import { StatusFooter } from "@/components/StatusFooter";
import { TopHeader } from "@/components/TopHeader";
import { useBrainStore } from "@/state/brain.store";

describe("phase 5.12 visual chrome", () => {
  it("renders the active left nav rail", () => {
    render(<NavRail />);
    expect(screen.getByTitle("Brain")).toHaveClass("text-[#00E5D8]");
    expect(screen.getByTitle("Explore")).toBeInTheDocument();
    expect(screen.getByTitle("Governance")).toBeInTheDocument();
  });

  it("renders the centered AXIOM live header", () => {
    render(<TopHeader />);
    expect(screen.getByText("AXIOM")).toBeInTheDocument();
    expect(screen.getByText("LIVE")).toBeInTheDocument();
  });

  it("renders brain health card rows from store-backed metrics", () => {
    useBrainStore.setState({
      entities: new Map([["a", { id: "a", type: "document", data: { composite_importance: 0.9 }, source_id: null, created_at: "t", updated_at: "t" }]]),
      edges: new Map([["e", { id: "e", source_id: "a", target_id: "b", relationship: "mentions", data: {}, created_at: "t" }]]),
      clusterHealth: {},
    });
    render(<BrainHealthCard />);
    expect(screen.getByText("Brain Health")).toBeInTheDocument();
    expect(screen.getByText("Entities")).toBeInTheDocument();
    expect(screen.getByText("Relationships")).toBeInTheDocument();
    expect(screen.getByText("Classified")).toBeInTheDocument();
    expect(screen.getByText("Health")).toBeInTheDocument();
    expect(screen.queryByText("2.48M")).not.toBeInTheDocument();
    expect(screen.getByText("Initializing")).toBeInTheDocument();
  });

  // HIDDEN-V2: asserts governance UI removed for YC company-brain positioning. unskip when re-surfacing.
  it.skip("[HIDDEN-V2] query prompt chips dispatch traversal events", () => {
    const spy = vi.fn();
    const searchSpy = vi.fn();
    window.addEventListener("axiom:traverse-clusters", spy);
    window.addEventListener("axiom:palette-query", searchSpy);
    render(<QueryBar />);
    fireEvent.click(screen.getByText("What impacted Q2 revenue?"));
    expect(spy).toHaveBeenCalled();
    expect(searchSpy).toHaveBeenCalledWith(expect.objectContaining({
      detail: { query: "What impacted Q2 revenue?" },
    }));
    window.removeEventListener("axiom:traverse-clusters", spy);
    window.removeEventListener("axiom:palette-query", searchSpy);
  });

  it("send query dispatches a searchable palette query", () => {
    const searchSpy = vi.fn();
    window.addEventListener("axiom:palette-query", searchSpy);
    render(<QueryBar />);
    fireEvent.change(screen.getByPlaceholderText("Ask the Company Brain anything..."), {
      target: { value: "policy" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send query" }));
    expect(searchSpy).toHaveBeenCalledWith(expect.objectContaining({
      detail: { query: "policy" },
    }));
    window.removeEventListener("axiom:palette-query", searchSpy);
  });

  it("query input submits with Enter without opening an empty palette on focus", () => {
    const openSpy = vi.fn();
    const searchSpy = vi.fn();
    window.addEventListener("axiom:open-palette", openSpy);
    window.addEventListener("axiom:palette-query", searchSpy);
    render(<QueryBar />);
    const input = screen.getByPlaceholderText("Ask the Company Brain anything...");

    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "policy" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(openSpy).not.toHaveBeenCalled();
    expect(searchSpy).toHaveBeenCalledWith(expect.objectContaining({
      detail: { query: "policy" },
    }));
    window.removeEventListener("axiom:open-palette", openSpy);
    window.removeEventListener("axiom:palette-query", searchSpy);
  });

  // HIDDEN-V2: asserts governance UI removed for YC company-brain positioning. unskip when re-surfacing.
  it.skip("[HIDDEN-V2] renders the edge legend categories", () => {
    render(<EdgeLegend />);
    expect(screen.getByText("Knowledge")).toBeInTheDocument();
    expect(screen.getByText("Execution")).toBeInTheDocument();
    expect(screen.getAllByText("Governance").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("External")).toBeInTheDocument();
  });

  it("renders the graph footer with FPS and active Graph tab", () => {
    useBrainStore.setState({ fps: 58 });
    render(<StatusFooter />);
    expect(screen.getByText("AXIOM v0.1")).toBeInTheDocument();
    expect(screen.getByText("58 FPS")).toBeInTheDocument();
    expect(screen.getByText("Graph")).toHaveClass("text-[#00E5D8]");
  });

  // HIDDEN-V2: asserts governance UI removed for YC company-brain positioning. unskip when re-surfacing.
  it.skip("[HIDDEN-V2] slides entity inspector open for a selected entity", () => {
    useBrainStore.setState({
      selectedId: "a",
      entities: new Map([["a", { id: "a", type: "policy", data: { title: "Data Policy" }, source_id: null, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" }]]),
      edges: new Map(),
    });
    render(<EntityInspector />);
    expect(screen.getByText("Data Policy")).toBeInTheDocument();
    expect(screen.getByText("Trust & Governance")).toBeInTheDocument();
  });
});
