import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { InspectorPanel } from "@/components/InspectorPanel";
import { useBrainStore } from "@/state/brain.store";

describe("InspectorPanel", () => {
  afterEach(cleanup);
  it("renders the company brain architecture by default", () => {
    useBrainStore.setState({ entities: new Map(), edges: new Map(), selectedId: null, selectedClusterId: null, receipts: [] });
    render(<InspectorPanel />);
    expect(screen.getByText("The Company Brain")).toBeInTheDocument();
    expect(screen.getByText("Executable Skills")).toBeInTheDocument();
    expect(screen.getByText(/Tom Blomfield/)).toBeInTheDocument();
  });

  it("renders selected cluster detail", () => {
    useBrainStore.setState({
      selectedId: null,
      selectedClusterId: "billing_payments",
      agentActions: [
        {
          action_id: "act_1",
          agent_name: "claude",
          cluster_id: "billing_payments",
          skill_called: "skills.billing.refund_lookup",
          decision: "allow",
          timestamp: "t",
        },
      ],
      clusterHealth: { billing_payments: { cluster_id: "billing_payments", status: "degraded", ingest_rate_per_min: 1, last_ingest_at: null, total_entities: 1 } },
      entities: new Map([
        ["e1", { id: "e1", type: "doc", data: { title: "Refund Policy 2026" }, source_id: null, created_at: "t", updated_at: "t", cluster_id: "billing_payments", composite_importance: 0.94 }],
      ]),
      edges: new Map(),
    });
    render(<InspectorPanel />);
    expect(screen.getAllByText("Billing & Payments").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Refund Policy 2026/)).toBeInTheDocument();
    expect(screen.getByText("degraded")).toBeInTheDocument();
    expect(screen.getByText(/skills.billing.refund_lookup/)).toBeInTheDocument();
  });

  it("renders selected entity detail", () => {
    useBrainStore.setState({
      selectedId: "e1",
      selectedClusterId: null,
      entities: new Map([
        ["e1", { id: "e1", type: "doc", data: { title: "Stripe webhook handler" }, source_id: null, created_at: "t", updated_at: "t", cluster_id: "engineering_code", composite_importance: 0.91 }],
      ]),
      edges: new Map(),
    });
    render(<InspectorPanel />);
    expect(screen.getAllByText("Stripe webhook handler").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/engineering_code/)).toBeInTheDocument();
  });

  it("embeds AI insight in the default inspector", () => {
    useBrainStore.setState({ entities: new Map(), edges: new Map(), selectedId: null, selectedClusterId: null, insights: [] });
    render(<InspectorPanel />);
    expect(screen.getByText("AI Insight")).toBeInTheDocument();
  });
});
