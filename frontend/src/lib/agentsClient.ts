import type { Passport } from "@/lib/passportsClient";

export type AgentRegistryRow = {
  agent_name: string;
  name?: string;
  agent_class: string;
  owner_email: string | null;
  passport_id: string | null;
  passport_status: string;
  first_seen: string;
  last_seen: string;
  total_actions: number;
  allow_count: number;
  correct_count: number;
  deny_count: number;
  last_intent: string | null;
  last_action_id: string | null;
  agent_type: string;
};

export type RegisterAgentBody = {
  name: string;
  agent_class: string;
  owner_email: string;
  passport_id?: string | null;
  issue_new_passport: boolean;
  ttl_hours?: number;
};

export type ReceiptRow = {
  receipt_id: string;
  action_id: string;
  agent_name: string;
  intent: string;
  target_entity_id: string | null;
  decision: string;
  policy_id: string;
  created_at: string;
  timestamp?: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as T;
}

export async function listAgentRegistry(): Promise<AgentRegistryRow[]> {
  const data = await request<{ agents: AgentRegistryRow[] }>("/api/internal/agent-registry");
  return data.agents;
}

export async function registerAgent(body: RegisterAgentBody): Promise<AgentRegistryRow> {
  return request<AgentRegistryRow>("/api/internal/agent-registry", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listAgentReceipts(agentName: string): Promise<ReceiptRow[]> {
  const data = await request<{ receipts: ReceiptRow[] }>(
    `/api/internal/receipts?agent=${encodeURIComponent(agentName)}&limit=20`,
  );
  return data.receipts;
}

export async function listRecentReceipts(limit = 50): Promise<ReceiptRow[]> {
  const data = await request<{ receipts: ReceiptRow[] }>(
    `/api/internal/receipts?limit=${encodeURIComponent(String(limit))}`,
  );
  return data.receipts;
}

export function passportLabel(passport: Passport): string {
  return `${passport.agent_name} · ${passport.status} · ${passport.passport_id.slice(0, 8)}`;
}
