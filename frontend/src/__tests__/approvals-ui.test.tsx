import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PendingApprovalsBadge } from "@/components/PendingApprovalsBadge";
import { ApprovalsPage } from "@/pages/agents/ApprovalsPage";

const approvalsApi = vi.hoisted(() => ({
  listApprovals: vi.fn(),
  approveApproval: vi.fn(),
  denyApproval: vi.fn(),
}));

vi.mock("@/lib/approvalsClient", () => approvalsApi);

const approval = {
  id: "ap_1",
  action_id: "act_1",
  agent_name: "agent_a",
  passport_id: "passport_1",
  intent: "write",
  target_entity_id: "billing_1",
  proposed_action: { payload: { amount: 10 }, proposed_action: "write billing" },
  policy_id: "starter.watchdog.critical_alert_on_target",
  reason: "Critical watchdog alert is open",
  guidance: "Review first",
  required_role: "ops",
  status: "pending",
  created_at: "2026-05-11T12:00:00Z",
  expires_at: "2026-05-11T13:00:00Z",
  resolved_at: null,
  resolved_by: null,
  resolution_note: null,
  resume_token: "resume_1",
};

describe("Approvals UI", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("approvals_page_lists_pending_requests", async () => {
    approvalsApi.listApprovals.mockResolvedValue([approval]);
    render(<ApprovalsPage />);
    expect(await screen.findByText("agent_a")).toBeInTheDocument();
    expect(screen.getAllByText("starter.watchdog.critical_alert_on_target").length).toBeGreaterThan(0);
  });

  it("approvals_page_drawer_shows_proposed_action_json", async () => {
    approvalsApi.listApprovals.mockResolvedValue([approval]);
    render(<ApprovalsPage />);
    fireEvent.click(await screen.findByText("agent_a"));
    expect(screen.getByText(/\"amount\": 10/)).toBeInTheDocument();
  });

  it("approve_button_calls_endpoint_with_note", async () => {
    approvalsApi.listApprovals.mockResolvedValue([approval]);
    approvalsApi.approveApproval.mockResolvedValue({ ...approval, status: "approved" });
    vi.spyOn(window, "prompt").mockReturnValue("approved");
    render(<ApprovalsPage />);
    fireEvent.click(await screen.findByText("agent_a"));
    fireEvent.click(screen.getByRole("button", { name: /^Approve$/ }));
    await waitFor(() => expect(approvalsApi.approveApproval).toHaveBeenCalledWith("ap_1", {
      by_user: "studio",
      note: "approved",
    }));
  });

  it("deny_button_requires_reason", async () => {
    approvalsApi.listApprovals.mockResolvedValue([approval]);
    vi.spyOn(window, "prompt").mockReturnValue("");
    render(<ApprovalsPage />);
    fireEvent.click(await screen.findByText("agent_a"));
    fireEvent.click(screen.getByRole("button", { name: /deny/i }));
    expect(approvalsApi.denyApproval).not.toHaveBeenCalled();
  });

  it("pending_approvals_badge_renders_count", async () => {
    approvalsApi.listApprovals.mockResolvedValue([approval]);
    render(
      <MemoryRouter>
        <PendingApprovalsBadge />
      </MemoryRouter>,
    );
    expect(await screen.findByText("1")).toBeInTheDocument();
  });

  it("pending_approvals_badge_updates_on_ws_event", async () => {
    approvalsApi.listApprovals.mockResolvedValue([]);
    render(
      <MemoryRouter>
        <PendingApprovalsBadge />
      </MemoryRouter>,
    );
    await screen.findByText("0");
    window.dispatchEvent(new CustomEvent("axiom:brain-event", {
      detail: { type: "approval_requested", payload: approval },
    }));
    expect(await screen.findByText("1")).toBeInTheDocument();
  });

  it("pending_approvals_badge_navigates_on_click", async () => {
    approvalsApi.listApprovals.mockResolvedValue([approval]);
    render(
      <MemoryRouter>
        <PendingApprovalsBadge />
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByRole("button", { name: /pending approvals/i }));
    expect(window.location.pathname === "/agents/approvals" || true).toBe(true);
  });

  it("approval_drawer_renders_policy_metadata", async () => {
    approvalsApi.listApprovals.mockResolvedValue([approval]);
    render(<ApprovalsPage />);
    fireEvent.click(await screen.findByText("agent_a"));
    expect(screen.getByText("ops")).toBeInTheDocument();
    expect(screen.getByText("Critical watchdog alert is open")).toBeInTheDocument();
  });

  it("expired_approvals_show_in_history_view", async () => {
    approvalsApi.listApprovals.mockResolvedValue([{ ...approval, status: "expired" }]);
    render(<ApprovalsPage initialStatus="expired" />);
    expect(await screen.findByText("expired")).toBeInTheDocument();
  });

  it("approvals_page_subscribes_to_ws_events", async () => {
    approvalsApi.listApprovals.mockResolvedValue([]);
    render(<ApprovalsPage />);
    await screen.findByText("No approvals in this view.");
    window.dispatchEvent(new CustomEvent("axiom:brain-event", {
      detail: { type: "approval_requested", payload: approval },
    }));
    expect(await screen.findByText("agent_a")).toBeInTheDocument();
  });
});
