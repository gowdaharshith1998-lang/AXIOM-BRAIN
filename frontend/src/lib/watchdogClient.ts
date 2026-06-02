import { request } from "@/lib/http";
import type { WatchdogAlert } from "@/state/brain.store";

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
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resolution_note: resolutionNote }),
    },
  );
}
