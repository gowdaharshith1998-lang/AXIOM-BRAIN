import { request } from "@/lib/http";

export type StudioSettings = Record<string, unknown>;

export type MCPToolStat = {
  name: string;
  calls: number;
  last_called: number | null;
};

export type MCPStats = {
  tools: MCPToolStat[];
  connected_clients: number;
  active_agents: string[];
  observed_agents?: string[];
  last_tool_call: number | null;
  recent_actions: Array<{
    agent_name: string;
    intent: string;
    status: string;
    timestamp: number;
    duration_ms?: number;
  }>;
};

export async function getStudioSettings(): Promise<StudioSettings> {
  const data = await request<{ settings: StudioSettings }>("/api/internal/settings");
  return data.settings;
}

export async function saveStudioSettings(payload: StudioSettings): Promise<StudioSettings> {
  const data = await request<{ settings: StudioSettings }>("/api/internal/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return data.settings;
}

export async function getMcpStats(): Promise<MCPStats> {
  return request<MCPStats>("/api/internal/mcp-stats");
}

export async function getHealth(): Promise<{ status: string }> {
  return request<{ status: string }>("/api/health");
}
