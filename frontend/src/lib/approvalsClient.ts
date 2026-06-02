import { requestRaw } from "@/lib/http";

export type ApprovalRequest = {
  id: string;
  action_id: string;
  agent_name: string;
  passport_id: string | null;
  intent: string;
  target_entity_id: string | null;
  proposed_action: Record<string, unknown>;
  policy_id: string;
  reason: string;
  guidance: string | null;
  required_role: string | null;
  status: "pending" | "approved" | "denied" | "expired";
  created_at: string;
  expires_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
  resolution_note: string | null;
  resume_token: string;
};

export type ApprovalResolution = {
  by_user: string;
  note?: string | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await requestRaw(path, {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as T;
}

export async function listApprovals(status = "pending"): Promise<ApprovalRequest[]> {
  const data = await request<{ approvals: ApprovalRequest[] }>(
    `/api/internal/approvals?status=${encodeURIComponent(status)}`,
  );
  return data.approvals;
}

export async function approveApproval(
  id: string,
  body: ApprovalResolution,
): Promise<ApprovalRequest> {
  return request<ApprovalRequest>(`/api/internal/approvals/${id}/approve`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function denyApproval(
  id: string,
  body: ApprovalResolution,
): Promise<ApprovalRequest> {
  return request<ApprovalRequest>(`/api/internal/approvals/${id}/deny`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}
