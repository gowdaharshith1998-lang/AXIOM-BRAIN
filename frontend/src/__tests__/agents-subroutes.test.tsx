import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ActivityPage } from "@/pages/agents/ActivityPage";
import { RuntimePage } from "@/pages/agents/RuntimePage";
import { SchedulesPage } from "@/pages/agents/SchedulesPage";
import { TriggersPage } from "@/pages/agents/TriggersPage";

const skillsApi = vi.hoisted(() => ({
  listSkills: vi.fn(),
}));
const studioApi = vi.hoisted(() => ({
  getMcpStats: vi.fn(),
}));
const agentsApi = vi.hoisted(() => ({
  listRecentReceipts: vi.fn(),
}));

vi.mock("@/lib/skillsClient", () => skillsApi);
vi.mock("@/lib/studioClient", () => studioApi);
vi.mock("@/lib/agentsClient", () => agentsApi);

const scheduledSkill = {
  id: "sk_schedule",
  name: "daily_digest",
  description: "Daily digest",
  intent: "summarize",
  trigger_type: "schedule",
  trigger_config: { cron: "0 9 * * *", next_run_at: "2026-05-11T09:00:00Z" },
  prompt_template: "Summarize",
  llm_provider: "openai",
  llm_model: "gpt-4o-mini",
  status: "active",
  created_by: "ops",
  created_at: "2026-05-10T00:00:00Z",
  updated_at: "2026-05-10T00:00:00Z",
  last_run_at: null,
  total_runs: 3,
};

const eventSkill = {
  ...scheduledSkill,
  id: "sk_event",
  name: "watch_ticket",
  trigger_type: "event",
  trigger_config: { event_type: "ticket.created" },
};

describe("Agents sub-routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("schedules_page_lists_scheduled_skills", async () => {
    skillsApi.listSkills.mockResolvedValue([scheduledSkill]);
    render(<SchedulesPage />);
    expect(await screen.findByText("daily_digest")).toBeInTheDocument();
    expect(screen.getByText("0 9 * * *")).toBeInTheDocument();
    expect(screen.getByText(/May 11, 2026/)).toBeInTheDocument();
    expect(skillsApi.listSkills).toHaveBeenCalledWith({ triggerType: "schedule" });
  });

  it("schedules_page_empty_state", async () => {
    skillsApi.listSkills.mockResolvedValue([]);
    render(<SchedulesPage />);
    expect(await screen.findByText("No scheduled skills yet.")).toBeInTheDocument();
  });

  it("triggers_page_lists_event_skills", async () => {
    skillsApi.listSkills.mockResolvedValue([eventSkill]);
    render(<TriggersPage />);
    expect(await screen.findByText("watch_ticket")).toBeInTheDocument();
    expect(screen.getByText("ticket.created")).toBeInTheDocument();
    expect(skillsApi.listSkills).toHaveBeenCalledWith({ triggerType: "event" });
  });

  it("triggers_page_empty_state", async () => {
    skillsApi.listSkills.mockResolvedValue([]);
    render(<TriggersPage />);
    expect(await screen.findByText("No event-triggered skills yet.")).toBeInTheDocument();
  });

  it("runtime_page_renders_mcp_stats", async () => {
    studioApi.getMcpStats.mockResolvedValue({
      tools: [{ name: "axiom_query_brain", calls: 7, last_called: 1710000000000 }],
      connected_clients: 1,
      active_agents: ["researcher"],
      observed_agents: ["researcher"],
      last_tool_call: 1710000000000,
      recent_actions: [{ agent_name: "researcher", intent: "read", status: "allow", timestamp: 1710000000000 }],
    });
    render(<RuntimePage />);
    expect(await screen.findByText("researcher")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("axiom_query_brain")).toBeInTheDocument();
  });

  it("runtime_page_handles_empty_stats", async () => {
    studioApi.getMcpStats.mockResolvedValue({
      tools: [],
      connected_clients: 0,
      active_agents: [],
      observed_agents: [],
      last_tool_call: null,
      recent_actions: [],
    });
    render(<RuntimePage />);
    expect(await screen.findByText("No active runtime signals yet.")).toBeInTheDocument();
  });

  it("activity_page_renders_receipt_log", async () => {
    agentsApi.listRecentReceipts.mockResolvedValue([
      { receipt_id: "r1", action_id: "act_1", agent_name: "researcher", intent: "read", target_entity_id: "e1", decision: "allow", policy_id: "AEGIS-1", created_at: "2026-05-10T10:15:00Z" },
    ]);
    render(<ActivityPage />);
    expect(await screen.findByText("act_1")).toBeInTheDocument();
    expect(screen.getByText("researcher")).toBeInTheDocument();
    expect(screen.getByText("allow")).toBeInTheDocument();
  });

  it("activity_page_groups_by_hour", async () => {
    agentsApi.listRecentReceipts.mockResolvedValue([
      { receipt_id: "r1", action_id: "act_1", agent_name: "a", intent: "read", target_entity_id: "e1", decision: "allow", policy_id: "AEGIS-1", created_at: "2026-05-10T10:15:00Z" },
      { receipt_id: "r2", action_id: "act_2", agent_name: "b", intent: "write", target_entity_id: "e2", decision: "deny", policy_id: "AEGIS-2", created_at: "2026-05-10T10:45:00Z" },
    ]);
    render(<ActivityPage />);
    expect(await screen.findByText("2026-05-10 10:00")).toBeInTheDocument();
    expect(screen.getByText("2 receipts")).toBeInTheDocument();
  });
});
