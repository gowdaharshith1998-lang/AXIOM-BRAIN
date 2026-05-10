import type { WatchdogAlert } from "@/state/brain.store";

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

export async function listWatchdogAlerts(status = "open"): Promise<WatchdogAlert[]> {
  const data = await request<{ alerts: WatchdogAlert[] }>(
    `/api/internal/watchdog/alerts?status=${encodeURIComponent(status)}&limit=50`,
  );
  return data.alerts;
}

export async function acknowledgeWatchdogAlert(alertId: string): Promise<WatchdogAlert> {
  return request<WatchdogAlert>(
    `/api/internal/watchdog/alerts/${encodeURIComponent(alertId)}/acknowledge`,
    { method: "POST" },
  );
}

export async function resolveWatchdogAlert(
  alertId: string,
  resolutionNote: string,
): Promise<WatchdogAlert> {
  return request<WatchdogAlert>(
    `/api/internal/watchdog/alerts/${encodeURIComponent(alertId)}/resolve`,
    {
      method: "POST",
      body: JSON.stringify({ resolution_note: resolutionNote }),
    },
  );
}
