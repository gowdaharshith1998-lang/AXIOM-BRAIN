import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AIInsightCard } from "@/components/AIInsightCard";
import { useBrainStore } from "@/state/brain.store";

describe("AIInsightCard", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });
  it("renders honest no-alert state when watchdog has no open alerts", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ alerts: [] }))));
    useBrainStore.setState({ insights: [], watchdogAlerts: [] });
    render(<AIInsightCard />);
    await waitFor(() => expect(screen.getByText("WARDEN clear")).toBeInTheDocument());
    expect(screen.getByText("No open watchdog alerts.")).toBeInTheDocument();
  });

  it("dispatches related entity highlights", () => {
    const dispatch = vi.spyOn(window, "dispatchEvent");
    useBrainStore.setState({
      watchdogAlerts: [],
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
    fireEvent.click(screen.getAllByText("No action needed")[0]);
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: "axiom:highlight-entities" }));
  });

  it("renders connected entity ids from live insight", () => {
    useBrainStore.setState({
      watchdogAlerts: [],
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

  it("binds to the highest-severity real watchdog alert", () => {
    useBrainStore.setState({
      insights: [],
      watchdogAlerts: [
        {
          alert_id: "a1",
          entity_id: "entity-low",
          rule_id: "R5",
          severity: "info",
          reason: "Low signal",
          evidence: {},
          suggested_action: "Review cluster",
          status: "open",
          detected_at: "2026-05-10T10:00:00",
          resolved_at: null,
          resolved_by: null,
        },
        {
          alert_id: "a2",
          entity_id: "ticket-1",
          rule_id: "R2",
          severity: "critical",
          reason: "P1 ticket has no runbook",
          evidence: {},
          suggested_action: "Attach runbook",
          status: "open",
          detected_at: "2026-05-10T10:01:00",
          resolved_at: null,
          resolved_by: null,
        },
      ],
    });
    render(<AIInsightCard />);
    expect(screen.getByText("P1 ticket has no runbook")).toBeInTheDocument();
    expect(screen.getByText(/ticket-1/)).toBeInTheDocument();
  });
});
