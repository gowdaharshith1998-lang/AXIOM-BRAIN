import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AIInsightCard } from "@/components/AIInsightCard";
import { useBrainStore } from "@/state/brain.store";

describe("AIInsightCard", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });
  it("renders WARDEN fallback advisory", () => {
    useBrainStore.setState({ insights: [] });
    render(<AIInsightCard />);
    expect(screen.getByText("WARDEN flagged")).toBeInTheDocument();
    expect(screen.getByText(/PR-341/)).toBeInTheDocument();
  });

  it("dispatches related entity highlights", () => {
    const dispatch = vi.spyOn(window, "dispatchEvent");
    useBrainStore.setState({
      insights: [
        {
          insight_id: "ins_1",
          severity: "warning",
          message: "Refund volume up 28% week-over-week - investigate",
          confidence: 0.87,
          related_entity_ids: ["e1", "e2"],
          recommended_actions: [],
          timestamp: "t",
        },
      ],
    });
    render(<AIInsightCard />);
    fireEvent.click(screen.getAllByText("View recommended actions")[0]);
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: "axiom:highlight-entities" }));
  });

  it("renders connected entity ids from live insight", () => {
    useBrainStore.setState({
      insights: [
        {
          insight_id: "ins_2",
          severity: "critical",
          message: "Customer support ticket mentions undocumented pricing exception",
          confidence: 0.92,
          related_entity_ids: ["policy", "ticket", "pricing"],
          recommended_actions: [],
          timestamp: "t",
        },
      ],
    });
    render(<AIInsightCard />);
    expect(screen.getByText(/policy, ticket, pricing/)).toBeInTheDocument();
  });
});
