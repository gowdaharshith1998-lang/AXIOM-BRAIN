import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GovernancePage } from "@/pages/GovernancePage";

const watchdogApi = vi.hoisted(() => ({
  listWatchdogAlerts: vi.fn(),
  acknowledgeWatchdogAlert: vi.fn(),
  resolveWatchdogAlert: vi.fn(),
}));

vi.mock("@/lib/watchdogClient", () => watchdogApi);

const governanceSnapshot = {
  generated_at: "2026-05-10T00:00:00",
  summary: {
    policy_count: 0,
    active_policy_count: 0,
    check_count: 0,
    healthy_check_count: 0,
    degraded_check_count: 0,
    critical_check_count: 0,
    receipt_count: 0,
    signed_receipt_count: 0,
    action_count: 0,
    denied_action_count: 0,
    current_merkle_root: null,
    graph_entity_count: 0,
    graph_edge_count: 0,
    source_count: 0,
    latest_event_at: null,
    current_seq: 0,
    generated_at_ms: 0,
  },
  policies: [],
  checks: [],
  receipts: [],
  audit_events: [],
  sources: [],
  lineage: { entities: [], edges: [] },
};

const rules = [
  {
    rule_id: "watchdog.R2.ticket_severity_mismatch_runbook",
    description: "Pause agent actions while watchdog rule R2 is open.",
    action: "pause",
    severity: "critical",
    predicate: 'watchdog.has_open_alert_on(entity, rule_id="R2") == true',
    source_file: null,
    guidance: "Attach runbook before continuing.",
    metadata: { source: "watchdog", watchdog_rule_id: "R2" },
  },
  {
    rule_id: "starter.scope.intent_must_be_allowed",
    description: "Agents can only use allowed intents.",
    action: "deny",
    severity: "high",
    predicate: "agent.intent in passport.scope_intents",
    source_file: "/repo/policies/starter-pack/scope.yaml",
    metadata: { source: "starter_pack" },
  },
  {
    rule_id: "custom.local.review_required",
    description: "Local governance override.",
    action: "advise",
    severity: "medium",
    predicate: "true",
    source_file: "/repo/policies/custom.yaml",
    metadata: { source: "custom" },
  },
];

const alert = {
  alert_id: "al_1",
  entity_id: "ticket_1",
  rule_id: "R2",
  severity: "critical" as const,
  reason: "P1 ticket has no runbook",
  evidence: {},
  suggested_action: "Attach runbook",
  status: "open" as const,
  detected_at: "2026-05-10T00:00:00",
  resolved_at: null,
  resolved_by: null,
};

function policyRulesFor(path: string) {
  const url = new URL(path, "http://localhost");
  const source = url.searchParams.get("source") ?? "all";
  const filtered = source === "all" ? rules : rules.filter((rule) => rule.metadata.source === source);
  return { count: filtered.length, rules: filtered };
}

function renderPolicyTab() {
  return render(
    <MemoryRouter initialEntries={["/governance?tab=policies"]}>
      <GovernancePage />
    </MemoryRouter>,
  );
}

describe("watchdog policy UI", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    watchdogApi.listWatchdogAlerts.mockResolvedValue([alert]);
    watchdogApi.acknowledgeWatchdogAlert.mockResolvedValue(alert);
    watchdogApi.resolveWatchdogAlert.mockResolvedValue({ ...alert, status: "resolved" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const path = typeof input === "string" ? input : input.toString();
        if (path === "/api/governance") return new Response(JSON.stringify(governanceSnapshot), { status: 200 });
        if (path.startsWith("/api/internal/policies?")) return new Response(JSON.stringify(policyRulesFor(path)), { status: 200 });
        return new Response("{}", { status: 404 });
      }),
    );
  });

  it("governance_policy_tab_lists_real_rules_from_endpoint", async () => {
    renderPolicyTab();
    expect((await screen.findAllByText("watchdog.R2.ticket_severity_mismatch_runbook")).length).toBeGreaterThan(0);
    expect(screen.getByText("starter.scope.intent_must_be_allowed")).toBeInTheDocument();
  });

  it("governance_policy_tab_filters_by_source", async () => {
    renderPolicyTab();
    await screen.findByText("custom.local.review_required");
    fireEvent.click(screen.getByRole("button", { name: "Source Watchdog" }));
    await waitFor(() => expect(screen.queryAllByText("starter.scope.intent_must_be_allowed")).toHaveLength(0));
    expect(screen.getAllByText("watchdog.R2.ticket_severity_mismatch_runbook").length).toBeGreaterThan(0);
  });

  it("governance_policy_drawer_shows_fire_history", async () => {
    renderPolicyTab();
    fireEvent.click(await screen.findByRole("button", { name: "watchdog.R2.ticket_severity_mismatch_runbook" }));
    expect(await screen.findByText("Fire History")).toBeInTheDocument();
    expect(screen.getByText(/ticket_1/)).toBeInTheDocument();
    expect(screen.getByText("Attach runbook before continuing.")).toBeInTheDocument();
  });
});
