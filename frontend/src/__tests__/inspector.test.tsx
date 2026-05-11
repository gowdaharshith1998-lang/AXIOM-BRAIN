import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EntityInspector } from "@/components/EntityInspector";
import { prettyMetadata } from "@/lib/inspector";
import { useBrainStore } from "@/state/brain.store";

const entity = {
  id: "e1",
  type: "document",
  source_id: "linear-main",
  created_at: "2026-05-07T00:00:00Z",
  updated_at: "2026-05-07T00:00:00Z",
};

const receipt = {
  receipt_id: "receipt_1",
  id: "receipt_1",
  action_id: "act_1",
  agent_name: "watchdog",
  intent: "watchdog_alert",
  target_entity_id: "e1",
  decision: "deny",
  policy_id: "AEGIS-1",
  this_hash: "abc123def4567890",
  merkle_root: "abc123def4567890",
  signing_scheme: "ed25519",
  created_at: "2026-05-10T00:00:00Z",
  timestamp: "2026-05-10T00:00:00Z",
};

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
}

function installInspectorFetch(overrides: Record<string, unknown> = {}) {
  const payloads: Record<string, unknown> = {
    "/api/internal/receipts?target_entity_id=e1&limit=20": { receipts: [receipt], total_count: 1, merkle_head: receipt.this_hash },
    "/api/internal/receipts/receipt_1": { ...receipt, verification_status: "verified", chain_verified: true, signature_verified: true },
    "/api/sources": [{ source_id: "linear-main", display_name: "Linear", source_type: "linear", count: 1 }],
    "/api/entities/e1/edges": {
      incoming: [{ id: "edge_in", source_id: "src_1", target_id: "e1", relationship: "blocks", data: {}, created_at: "2026-05-10T00:00:00Z" }],
      outgoing: [{ id: "edge_out", source_id: "e1", target_id: "dst_1", relationship: "creates", data: {}, created_at: "2026-05-10T00:00:00Z" }],
    },
    "/api/entities/e1/lineage?depth=2": {
      nodes: [
        { id: "e1", type: "document", data: { title: "A" }, source_id: "linear-main", created_at: "2026-05-07T00:00:00Z", updated_at: "2026-05-07T00:00:00Z" },
        { id: "src_1", type: "decision", data: { title: "Source Decision" }, source_id: "linear-main", created_at: "2026-05-07T00:00:00Z", updated_at: "2026-05-07T00:00:00Z" },
      ],
      edges: [{ id: "edge_in", source_id: "src_1", target_id: "e1", relationship: "blocks", data: {}, created_at: "2026-05-10T00:00:00Z" }],
    },
    "/api/internal/policies/active?entity_id=e1": { rules: [] },
    ...overrides,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input.toString();
      if (!(path in payloads)) return new Response("{}", { status: 404 });
      return jsonResponse(payloads[path]);
    }),
  );
}

function renderSelectedInspector(data: Record<string, unknown> = {}) {
  useBrainStore.setState({
    entities: new Map([["e1", { ...entity, data: { title: "A", ...data } }]]),
    edges: new Map(),
    selectedId: "e1",
    selectedClusterId: null,
  });
  return render(<EntityInspector />);
}

describe("inspector metadata", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useBrainStore.setState({ entities: new Map(), edges: new Map(), selectedId: null, selectedClusterId: null });
    installInspectorFetch();
  });

  it("hides null Calibra fields", () => {
    expect(prettyMetadata({ calibra: null, name: "Invoice" })).toBe('{\n  "name": "Invoice"\n}');
  });

  it("hides empty string fields", () => {
    expect(prettyMetadata({ name: "", title: "Policy" })).toContain("Policy");
    expect(prettyMetadata({ name: "", title: "Policy" })).not.toContain("name");
  });

  it("hides empty metadata objects", () => {
    expect(prettyMetadata({ calibra: { id: null }, empty: {} })).toBeNull();
  });

  it("shows populated fields unchanged", () => {
    expect(prettyMetadata({ nested: { id: "c1" } })).toBe('{\n  "nested": {\n    "id": "c1"\n  }\n}');
  });

  it("renders selected entity overview", () => {
    renderSelectedInspector();
    expect(screen.getAllByText((content) => content.includes("e1")).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Overview").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Trust & Governance")).toBeInTheDocument();
  });

  it("inspector_merkle_root_renders_real_receipt_hash", async () => {
    renderSelectedInspector();
    expect(await screen.findByText("abc123def4567890")).toBeInTheDocument();
  });

  it("inspector_merkle_root_shows_empty_state_no_receipts", async () => {
    installInspectorFetch({ "/api/internal/receipts?target_entity_id=e1&limit=20": { receipts: [], total_count: 0, merkle_head: null } });
    renderSelectedInspector();
    await waitFor(() => expect(screen.getAllByText("No receipts yet.").length).toBeGreaterThanOrEqual(1));
  });

  it("inspector_policy_status_renders_last_decision", async () => {
    renderSelectedInspector();
    expect(await screen.findByText("Deny")).toBeInTheDocument();
  });

  it("inspector_policy_status_empty_state", async () => {
    installInspectorFetch({ "/api/internal/receipts?target_entity_id=e1&limit=20": { receipts: [], total_count: 0, merkle_head: null } });
    renderSelectedInspector();
    expect(await screen.findByText("No policy decisions yet.")).toBeInTheDocument();
  });

  it("inspector_signed_receipt_calls_verify_endpoint", async () => {
    renderSelectedInspector();
    expect(await screen.findByText("verified")).toBeInTheDocument();
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/internal/receipts/receipt_1"));
  });

  it("inspector_data_sources_renders_real_source_name", async () => {
    renderSelectedInspector();
    expect(await screen.findByText((content) => content.includes("Linear"))).toBeInTheDocument();
  });

  it("inspector_connections_tab_renders_real_edges", async () => {
    renderSelectedInspector();
    fireEvent.click(screen.getByRole("button", { name: "Connections" }));
    expect(await screen.findByText("blocks")).toBeInTheDocument();
    expect(screen.getByText("creates")).toBeInTheDocument();
  });

  it("inspector_lineage_tab_renders_traversal", async () => {
    renderSelectedInspector();
    fireEvent.click(screen.getByRole("button", { name: "Lineage" }));
    expect(await screen.findByText("Source Decision")).toBeInTheDocument();
    expect(screen.getByText("edge_in")).toBeInTheDocument();
  });

  it("inspector_activity_tab_renders_receipt_list", async () => {
    renderSelectedInspector();
    fireEvent.click(screen.getByRole("button", { name: "Activity" }));
    expect(await screen.findByText("act_1")).toBeInTheDocument();
    expect(screen.getByText((content) => content.includes("watchdog"))).toBeInTheDocument();
  });

  it("entity_inspector_active_policies_section_renders", async () => {
    installInspectorFetch({
      "/api/internal/policies/active?entity_id=e1": {
        rules: [
          {
            rule_id: "watchdog.R1.billing_change_without_decision",
            description: "Billing change requires a linked decision.",
            action: "pause",
            severity: "critical",
            reason: "Billing change without decision",
          },
        ],
      },
    });
    renderSelectedInspector();
    expect(await screen.findByText("Active Policies")).toBeInTheDocument();
    expect(screen.getByText("watchdog.R1.billing_change_without_decision")).toBeInTheDocument();
  });

  it("entity_inspector_active_policies_updates_on_watchdog_alert", async () => {
    const activePayload = { rules: [] as Array<Record<string, unknown>> };
    installInspectorFetch({ "/api/internal/policies/active?entity_id=e1": activePayload });
    renderSelectedInspector();
    expect(await screen.findByText("No active policy clauses.")).toBeInTheDocument();

    activePayload.rules = [
      {
        rule_id: "watchdog.R2.ticket_severity_mismatch_runbook",
        description: "P1 ticket requires a runbook.",
        action: "pause",
        severity: "critical",
        reason: "P1 ticket has no runbook",
      },
    ];
    window.dispatchEvent(new CustomEvent("axiom:brain-event", { detail: { type: "policy_clause_activated", payload: { entity_id: "e1" } } }));
    expect(await screen.findByText("watchdog.R2.ticket_severity_mismatch_runbook")).toBeInTheDocument();
  });

  it("inspector_no_hardcoded_strings_remain", async () => {
    renderSelectedInspector();
    expect(screen.queryByText("This tab is reserved for the next interaction pass.")).not.toBeInTheDocument();
    expect(screen.queryByText("Data Sources: CRM · Docs · Receipts")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Verified")).not.toBeInTheDocument());
  });
});
