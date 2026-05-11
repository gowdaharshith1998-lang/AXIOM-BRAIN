import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GovernancePage } from "@/pages/GovernancePage";

vi.mock("@/lib/watchdogClient", () => ({
  listWatchdogAlerts: vi.fn().mockResolvedValue([]),
  acknowledgeWatchdogAlert: vi.fn(),
  resolveWatchdogAlert: vi.fn(),
}));

const snapshot = {
  generated_at: "2026-05-10T00:00:00",
  summary: {
    policy_count: 0,
    active_policy_count: 0,
    check_count: 2,
    healthy_check_count: 1,
    degraded_check_count: 0,
    critical_check_count: 1,
    receipt_count: 2,
    signed_receipt_count: 1,
    action_count: 2,
    denied_action_count: 1,
    current_merkle_root: "abcdef1234567890",
    graph_entity_count: 2,
    graph_edge_count: 1,
    source_count: 1,
    latest_event_at: null,
    current_seq: 9,
    generated_at_ms: 0,
  },
  policies: [],
  checks: [
    { id: "check_ok", entity: "Graph ingest", type: "freshness", severity: "info", result: "healthy", last_run: "2026-05-10T00:00:00", owner: "platform", ingest_rate_per_min: 3, total_entities: 10 },
    { id: "check_critical", entity: "Receipt signer", type: "signature", severity: "critical", result: "critical", last_run: "2026-05-10T00:00:00", owner: "security", ingest_rate_per_min: 0, total_entities: 2 },
  ],
  receipts: [
    { id: "row_1", receipt_id: "rec_signed", receipt_type: "policy", action_id: "act_1", decision: "allow", agent_name: "researcher", signing_scheme: "ed25519", merkle_root: "root", signed: true, created_at: "2026-05-10T00:00:00" },
    { id: "row_2", receipt_id: "rec_unsigned", receipt_type: "policy", action_id: "act_2", decision: "deny", agent_name: "warden", signing_scheme: null, merkle_root: null, signed: false, created_at: "2026-05-10T00:00:00" },
  ],
  audit_events: [
    { id: "audit_1", timestamp: "2026-05-10T00:00:00", actor: "researcher", action: "read", entity: "doc_1", category: "agent_action", result: "allow", source: "actions" },
    { id: "audit_2", timestamp: "2026-05-10T00:00:00", actor: "mcp", action: "write", entity: "doc_2", category: "mcp_event", result: "deny", source: "mcp" },
  ],
  sources: [{ id: "src_1", source_type: "github", display_name: "GitHub", connected: true, created_at: "2026-05-10T00:00:00", updated_at: "2026-05-10T00:00:00" }],
  lineage: {
    entities: [
      { id: "doc_1", name: "Design Doc", type: "document", cluster_id: "product", updated_at: "2026-05-10T00:00:00" },
      { id: "doc_2", name: "Runbook", type: "document", cluster_id: "security", updated_at: "2026-05-10T00:00:00" },
    ],
    edges: [{ id: "edge_1", source_id: "doc_1", target_id: "doc_2", relationship: "references", created_at: "2026-05-10T00:00:00" }],
  },
};

function renderGovernance(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <GovernancePage />
    </MemoryRouter>,
  );
}

describe("governance interactive controls", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = typeof input === "string" ? input : input.toString();
      if (path === "/api/governance") return new Response(JSON.stringify(snapshot), { status: 200 });
      if (path.startsWith("/api/internal/policies?")) return new Response(JSON.stringify({ count: 0, rules: [] }), { status: 200 });
      return new Response("{}", { status: 404 });
    }));
    URL.createObjectURL = vi.fn(() => "blob:csv");
    URL.revokeObjectURL = vi.fn();
  });

  it("receipts filters by verification status and exports the filtered ledger", async () => {
    renderGovernance("/governance?tab=receipts");
    expect((await screen.findAllByText("rec_signed")).length).toBeGreaterThan(0);
    expect(screen.getByText("rec_unsigned")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Verification Status"), { target: { value: "unsigned" } });
    await waitFor(() => expect(screen.queryByText("rec_signed")).not.toBeInTheDocument());
    expect(screen.getAllByText("rec_unsigned").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Export Receipts CSV" }));
    expect(URL.createObjectURL).toHaveBeenCalled();
  });

  it("checks queue filters by query, severity, and result", async () => {
    renderGovernance("/governance?tab=checks");
    expect(await screen.findByText("Graph ingest")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Check Severity"), { target: { value: "critical" } });
    await waitFor(() => expect(screen.queryByText("Graph ingest")).not.toBeInTheDocument());
    expect(screen.getAllByText("Receipt signer").length).toBeGreaterThan(0);
    fireEvent.change(screen.getByPlaceholderText("Search checks..."), { target: { value: "missing" } });
    expect(screen.getByText("No cluster health checks match the current filters.")).toBeInTheDocument();
  });
});
