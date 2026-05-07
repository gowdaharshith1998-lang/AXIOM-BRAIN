import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { computeCrossClusterCount, computeHealthPercent, healthColor, HUD } from "@/components/HUD";
import { useBrainStore } from "@/state/brain.store";

describe("HUD", () => {
  afterEach(() => cleanup());

  it("renders six stats", () => {
    useBrainStore.setState({
      entities: new Map([
        [
          "e1",
          {
            id: "e1",
            type: "thread",
            data: {},
            source_id: null,
            created_at: "t",
            updated_at: "t",
            cluster_id: "billing_payments",
          },
        ],
      ]),
      edges: new Map([
        [
          "edge-1",
          {
            id: "edge-1",
            source_id: "e1",
            target_id: "e2",
            relationship: "mentions",
            data: {},
            created_at: "t",
          },
        ],
      ]),
      lastSeq: 0,
      fps: 60,
      selectedId: null,
      connectionStatus: "live",
    });

    render(<HUD />);
    expect(screen.getByText("Entities")).toBeInTheDocument();
    expect(screen.getByText("Edges")).toBeInTheDocument();
    expect(screen.getByText("Agents")).toBeInTheDocument();
    expect(screen.getByText("Receipts")).toBeInTheDocument();
    expect(screen.getByText("Low-confidence")).toBeInTheDocument();
    expect(screen.getByText("Cross-cluster")).toBeInTheDocument();
    expect(screen.getAllByText("1").length).toBeGreaterThanOrEqual(1);
  });

  it("colors health by threshold", () => {
    expect(healthColor(98)).toBe("#22c55e");
    expect(healthColor(80)).toBe("#eab308");
    expect(healthColor(50)).toBe("#ef4444");
  });

  it("uses connection state in health", () => {
    expect(computeHealthPercent("live", 100)).toBe(98);
    expect(computeHealthPercent("offline", 100)).toBe(70);
  });

  it("counts cross-cluster edges", () => {
    const entities = new Map([
      [
        "a",
        {
          id: "a",
          type: "thread",
          data: {},
          source_id: null,
          created_at: "t",
          updated_at: "t",
          cluster_id: "billing_payments",
        },
      ],
      [
        "b",
        {
          id: "b",
          type: "thread",
          data: {},
          source_id: null,
          created_at: "t",
          updated_at: "t",
          cluster_id: "incidents_ops",
        },
      ],
    ]);
    const edges = [
      { id: "e", source_id: "a", target_id: "b", relationship: "mentions", data: {}, created_at: "t" },
    ];
    expect(computeCrossClusterCount(edges, entities)).toBe(1);
  });

  it("shows selected entity name", () => {
    useBrainStore.setState({
      entities: new Map([
        [
          "e1",
          {
            id: "e1",
            type: "thread",
            data: { title: "Refund escalation policy" },
            source_id: null,
            created_at: "t",
            updated_at: "t",
          },
        ],
      ]),
      edges: new Map(),
      selectedId: "e1",
      connectionStatus: "live",
    });
    render(<HUD />);
    expect(screen.getAllByText(/Refund escalation policy/).length).toBeGreaterThanOrEqual(1);
  });

  it("flashes count values on change", () => {
    vi.useFakeTimers();
    useBrainStore.setState({
      entities: new Map(),
      edges: new Map(),
      selectedId: null,
      connectionStatus: "live",
    });
    const { container, rerender } = render(<HUD />);
    useBrainStore.setState({
      entities: new Map([
        [
          "e1",
          {
            id: "e1",
            type: "thread",
            data: {},
            source_id: null,
            created_at: "t",
            updated_at: "t",
          },
        ],
      ]),
    });
    rerender(<HUD />);
    expect(container.querySelector(".axiom-value-flash")).toBeTruthy();
    act(() => vi.advanceTimersByTime(700));
    rerender(<HUD />);
    expect(container.querySelector(".axiom-value-flash")).toBeFalsy();
    vi.useRealTimers();
  });

  it("animates the live pip when live", () => {
    useBrainStore.setState({ connectionStatus: "live" });
    const { container } = render(<HUD />);
    expect(container.querySelector(".h-2.w-2.rounded-full.animate-pulse")).toBeTruthy();
  });

  it("adds shimmer animation to the health bar", () => {
    const { container } = render(<HUD />);
    expect(container.querySelector(".axiom-health-shimmer")).toBeTruthy();
  });
});
