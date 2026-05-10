import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AgentsPage } from "@/pages/AgentsPage";
import { GovernancePage } from "@/pages/GovernancePage";
import { SkillsPage } from "@/pages/SkillsPage";

const agentsApi = vi.hoisted(() => ({
  listAgentRegistry: vi.fn(),
  registerAgent: vi.fn(),
  listAgentReceipts: vi.fn(),
  passportLabel: vi.fn((passport: { agent_name: string; status: string; passport_id: string }) => `${passport.agent_name} · ${passport.status} · ${passport.passport_id}`),
}));
const passportsApi = vi.hoisted(() => ({
  listPassports: vi.fn(),
  revokePassport: vi.fn(),
}));
const skillsApi = vi.hoisted(() => ({
  listSkills: vi.fn(),
  registerSkill: vi.fn(),
  archiveSkill: vi.fn(),
  listSkillRuns: vi.fn(),
}));
const watchdogApi = vi.hoisted(() => ({
  listWatchdogAlerts: vi.fn(),
  acknowledgeWatchdogAlert: vi.fn(),
  resolveWatchdogAlert: vi.fn(),
}));

vi.mock("@/lib/agentsClient", () => agentsApi);
vi.mock("@/lib/passportsClient", () => passportsApi);
vi.mock("@/lib/skillsClient", () => skillsApi);
vi.mock("@/lib/watchdogClient", () => watchdogApi);

const agent = {
  agent_name: "researcher",
  name: "researcher",
  agent_class: "worker",
  owner_email: "ops@example.com",
  passport_id: "pp_1",
  passport_status: "active",
  first_seen: "2026-05-10T00:00:00",
  last_seen: "2026-05-10T01:00:00",
  total_actions: 2,
  allow_count: 2,
  correct_count: 0,
  deny_count: 0,
  last_intent: "read",
  last_action_id: "act_1",
  agent_type: "external_mcp",
};

const passport = {
  passport_id: "pp_1",
  agent_name: "researcher",
  agent_class: "worker",
  owner_email: "ops@example.com",
  scope_clusters: ["*"],
  scope_intents: ["*"],
  scope_skills: ["*"],
  issued_at: "2026-05-10T00:00:00",
  expires_at: "2026-05-11T00:00:00",
  kill_switch: false,
  revoked_at: null,
  revocation_reason: null,
  status: "active",
};

const skill = {
  id: "sk_1",
  name: "summarize_policy",
  description: "Summarize policy",
  intent: "summarize",
  prompt_template: "Summarize {text}",
  llm_provider: "openai",
  llm_model: "gpt-4o-mini",
  status: "draft",
  created_by: "test",
  created_at: "2026-05-10T00:00:00",
  updated_at: "2026-05-10T00:00:00",
  last_run_at: null,
  total_runs: 1,
};

const run = {
  id: "run_1",
  skill_id: "sk_1",
  run_at: new Date().toISOString(),
  status: "success",
  input_payload: { text: "hello" },
  output_payload: { summary: "hi" },
  receipt_id: "r1",
  error_message: null,
  duration_ms: 12,
  agent_name: "researcher",
};

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

describe("Phase 13.B UI", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    agentsApi.listAgentRegistry.mockResolvedValue([agent]);
    agentsApi.registerAgent.mockResolvedValue({ ...agent, agent_name: "builder", name: "builder", total_actions: 0 });
    agentsApi.listAgentReceipts.mockResolvedValue([{ receipt_id: "rec_1", action_id: "act_1", agent_name: "researcher", intent: "read", target_entity_id: null, decision: "advise", policy_id: "p", created_at: "2026-05-10T00:00:00" }]);
    passportsApi.listPassports.mockResolvedValue([passport]);
    passportsApi.revokePassport.mockResolvedValue({ ...passport, status: "revoked" });
    skillsApi.listSkills.mockResolvedValue([skill]);
    skillsApi.registerSkill.mockResolvedValue({ ...skill, id: "sk_2", name: "extract_company", intent: "extract" });
    skillsApi.archiveSkill.mockResolvedValue({ ...skill, status: "archived" });
    skillsApi.listSkillRuns.mockResolvedValue([run]);
    watchdogApi.listWatchdogAlerts.mockResolvedValue([alert]);
    watchdogApi.acknowledgeWatchdogAlert.mockResolvedValue({ ...alert, status: "acknowledged" });
    watchdogApi.resolveWatchdogAlert.mockResolvedValue({ ...alert, status: "resolved", resolved_at: "2026-05-10T00:10:00" });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(governanceSnapshot))));
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("register-agent modal validates, posts, and chains passport issuance", async () => {
    render(<AgentsPage />);
    fireEvent.click(screen.getByRole("button", { name: /Register Agent/ }));
    const dialog = await screen.findByRole("form", { name: "Register Agent" });
    const submit = within(dialog).getByRole("button", { name: "Register" });
    expect(submit).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "builder" } });
    fireEvent.change(within(dialog).getByLabelText("Class"), { target: { value: "worker" } });
    fireEvent.change(within(dialog).getByLabelText("Owner Email"), { target: { value: "ops@example.com" } });
    fireEvent.click(submit);
    await waitFor(() => expect(agentsApi.registerAgent).toHaveBeenCalledWith(expect.objectContaining({ name: "builder", issue_new_passport: true })));
  });

  it("register-agent modal can select an existing passport", async () => {
    render(<AgentsPage />);
    fireEvent.click(screen.getByRole("button", { name: /Register Agent/ }));
    const dialog = await screen.findByRole("form", { name: "Register Agent" });
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "linked" } });
    fireEvent.change(within(dialog).getByLabelText("Class"), { target: { value: "external_mcp" } });
    fireEvent.change(within(dialog).getByLabelText("Owner Email"), { target: { value: "ops@example.com" } });
    fireEvent.click(within(dialog).getByLabelText("Issue new passport"));
    fireEvent.change(within(dialog).getByLabelText("Passport"), { target: { value: "pp_1" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Register" }));
    await waitFor(() => expect(agentsApi.registerAgent).toHaveBeenCalledWith(expect.objectContaining({ passport_id: "pp_1", issue_new_passport: false })));
  });

  it("register-skill modal posts to backend", async () => {
    render(<SkillsPage />);
    fireEvent.click(screen.getByRole("button", { name: /Register Skill/ }));
    const dialog = await screen.findByRole("form", { name: "Register Skill" });
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "extract_company" } });
    fireEvent.change(within(dialog).getByLabelText("Prompt Template"), { target: { value: "Extract {text}" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Register" }));
    await waitFor(() => expect(skillsApi.registerSkill).toHaveBeenCalledWith(expect.objectContaining({ name: "extract_company" })));
  });

  it("skills table renders and filters", async () => {
    render(<SkillsPage />);
    expect(await screen.findByText("summarize_policy")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("Filter skills"), { target: { value: "missing" } });
    expect(await screen.findByText("No skills registered yet.")).toBeInTheDocument();
  });

  it("archive button confirms then archives", async () => {
    render(<SkillsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Open" }));
    fireEvent.click(await screen.findByRole("button", { name: /Archive/ }));
    await waitFor(() => expect(skillsApi.archiveSkill).toHaveBeenCalledWith("sk_1"));
  });

  it("agent drawer shows recent receipts and can revoke passport", async () => {
    render(<AgentsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Open" }));
    expect(await screen.findByText("advise")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Revoke Passport/ }));
    await waitFor(() => expect(passportsApi.revokePassport).toHaveBeenCalledWith("pp_1"));
  });

  it("skill drawer shows recent runs with input and output", async () => {
    render(<SkillsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Open" }));
    expect(await screen.findByText("success")).toBeInTheDocument();
    expect(screen.getByText(/summary/)).toBeInTheDocument();
  });

  it("websocket skill_registered updates table in place", async () => {
    render(<SkillsPage />);
    await screen.findByText("summarize_policy");
    window.dispatchEvent(new CustomEvent("axiom:brain-event", { detail: { type: "skill_registered", payload: { skill: { ...skill, id: "sk_ws", name: "ws_skill" } } } }));
    expect(await screen.findByText("ws_skill")).toBeInTheDocument();
  });

  it("websocket skill_run_completed updates skill run drawer", async () => {
    render(<SkillsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Open" }));
    window.dispatchEvent(new CustomEvent("axiom:brain-event", { detail: { type: "skill_run_completed", payload: { run: { ...run, id: "run_ws", status: "failed", error_message: "bad input" } } } }));
    expect(await screen.findByText("failed")).toBeInTheDocument();
  });

  it("websocket agent_action increments total_actions counter", async () => {
    render(<AgentsPage />);
    expect(await screen.findByText("2")).toBeInTheDocument();
    window.dispatchEvent(new CustomEvent("axiom:brain-event", { detail: { type: "agent_action", payload: { agent_name: "researcher" } } }));
    expect(await screen.findByText("3")).toBeInTheDocument();
  });

  it("websocket agent_action creates a new registry row", async () => {
    render(<AgentsPage />);
    await screen.findByText("researcher");
    window.dispatchEvent(new CustomEvent("axiom:brain-event", { detail: { type: "agent_action", payload: { agent_name: "new-agent" } } }));
    expect(await screen.findByText("new-agent")).toBeInTheDocument();
  });

  it("watchdog feed renders alerts", async () => {
    render(<MemoryRouter><GovernancePage /></MemoryRouter>);
    expect(await screen.findByText("P1 ticket has no runbook")).toBeInTheDocument();
  });

  it("watchdog feed applies raised websocket alerts", async () => {
    watchdogApi.listWatchdogAlerts.mockResolvedValue([]);
    render(<MemoryRouter><GovernancePage /></MemoryRouter>);
    await screen.findByText("No open watchdog alerts.");
    window.dispatchEvent(new CustomEvent("axiom:brain-event", { detail: { type: "watchdog_alert_raised", payload: { ...alert, alert_id: "al_ws", reason: "New watchdog alert" } } }));
    expect(await screen.findByText("New watchdog alert")).toBeInTheDocument();
  });

  it("watchdog acknowledge button calls endpoint", async () => {
    render(<MemoryRouter><GovernancePage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "Acknowledge" }));
    await waitFor(() => expect(watchdogApi.acknowledgeWatchdogAlert).toHaveBeenCalledWith("al_1"));
  });

  it("watchdog resolve modal posts note", async () => {
    render(<MemoryRouter><GovernancePage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "Resolve" }));
    fireEvent.change(await screen.findByPlaceholderText("Resolution note"), { target: { value: "Linked runbook" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Resolve" })[1]);
    await waitFor(() => expect(watchdogApi.resolveWatchdogAlert).toHaveBeenCalledWith("al_1", "Linked runbook"));
  });

  it("empty states are honest for agents, skills, and watchdog", async () => {
    agentsApi.listAgentRegistry.mockResolvedValue([]);
    skillsApi.listSkills.mockResolvedValue([]);
    watchdogApi.listWatchdogAlerts.mockResolvedValue([]);
    const { unmount } = render(<AgentsPage />);
    expect(await screen.findByText("No registered agents yet.")).toBeInTheDocument();
    unmount();
    const skillsRender = render(<SkillsPage />);
    expect(await screen.findByText("No skills registered yet.")).toBeInTheDocument();
    skillsRender.unmount();
    render(<MemoryRouter><GovernancePage /></MemoryRouter>);
    expect(await screen.findByText("No open watchdog alerts.")).toBeInTheDocument();
  });
});
