import { useEffect, useMemo, useState } from "react";

type ConnectorStatus = {
  vendor: string;
  status: "connected" | "disconnected" | "error";
  account_label?: string | null;
  last_sync_at?: string | null;
  entities_ingested?: number;
  events_24h?: number;
  writes_blocked_week?: number;
  watch_mode?: "webhook" | "polling";
};

type RecentEvent = {
  vendor: string;
  event_type: string;
  external_id?: string;
  received_at?: string;
};

const vendors = [
  { id: "github", label: "GitHub" },
  { id: "linear", label: "Linear" },
  { id: "slack", label: "Slack" },
  { id: "notion", label: "Notion" },
  { id: "gmail", label: "Gmail" },
];

export function ConnectorsPage() {
  const [statuses, setStatuses] = useState<ConnectorStatus[]>([]);
  const [recentEvents, setRecentEvents] = useState<RecentEvent[]>([]);
  const [drawerVendor, setDrawerVendor] = useState<string | null>(null);

  async function load() {
    const response = await fetch("/api/internal/connectors/status");
    if (!response.ok) return;
    const payload = await response.json();
    setStatuses(Array.isArray(payload.connectors) ? payload.connectors : []);
  }

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    if (typeof WebSocket === "undefined") return;
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const host = window.location.host || "localhost";
    const socket = new WebSocket(`${protocol}://${host}/ws/brain`);
    socket.onmessage = (message) => {
      try {
        const event = JSON.parse(String(message.data));
        if (
          event.type === "connector_event_received" ||
          event.type === "connector_write_blocked" ||
          event.type === "connector_write_executed"
        ) {
          const vendor = String(event.payload?.vendor || event.source_id || "");
          setRecentEvents((existing) => [
            {
              vendor,
              event_type: String(event.payload?.event_type || event.type),
              external_id: typeof event.persisted_id === "string" ? event.persisted_id : undefined,
            },
            ...existing,
          ].slice(0, 50));
          if (event.type === "connector_event_received") {
            setStatuses((existing) =>
              existing.map((status) =>
                status.vendor === vendor
                  ? { ...status, events_24h: (status.events_24h || 0) + 1 }
                  : status,
              ),
            );
          }
        }
      } catch {
        // ignore malformed websocket events
      }
    };
    return () => socket.close();
  }, []);

  const byVendor = useMemo(
    () => new Map(statuses.map((status) => [status.vendor, status])),
    [statuses],
  );

  async function connect(vendor: string) {
    const response = await fetch(`/api/internal/connectors/${vendor}/install`, { method: "POST" });
    if (!response.ok) return;
    const payload = await response.json();
    if (typeof payload.authorize_url === "string") {
      window.open(payload.authorize_url, `axiom-${vendor}-oauth`, "width=720,height=780");
    }
  }

  async function sync(vendor: string) {
    await fetch(`/api/internal/connectors/${vendor}/sync`, { method: "POST" });
    await load();
  }

  async function testConnection(vendor: string) {
    await fetch(`/api/internal/connectors/${vendor}/test`, { method: "POST" });
  }

  async function viewEvents(vendor: string) {
    setDrawerVendor(vendor);
    const response = await fetch(`/api/internal/connectors/${vendor}/events`);
    if (!response.ok) return;
    const payload = await response.json();
    if (Array.isArray(payload.events)) {
      setRecentEvents((existing) => [...payload.events, ...existing].slice(0, 50));
    }
  }

  async function disconnect(vendor: string) {
    await fetch(`/api/internal/connectors/${vendor}`, { method: "DELETE" });
    await load();
  }

  return (
    <div className="settings-stage">
      <section className="settings-panel">
        <h3 className="settings-panel-title">Connectors</h3>
        <div className="settings-panel-body space-y-3">
          {vendors.map((vendor) => {
            const status = byVendor.get(vendor.id);
            const connected = status?.status === "connected";
            const watchMode = status?.watch_mode === "polling" ? "Polling" : null;
            return (
              <div
                key={vendor.id}
                className="grid grid-cols-[120px_130px_1fr_240px_360px] items-center gap-3 border-b border-[#173657] py-3 text-[13px]"
              >
                <div className="text-[15px] font-semibold text-[#e8f2ff]">{vendor.label}</div>
                <div>
                  <span className={connected ? "settings-status-good" : "settings-status-muted"}>
                    {connected ? "Connected" : "Disconnected"}
                  </span>
                </div>
                <div className="min-w-0 text-[#a9bed8]">
                  <span>{connected ? status?.account_label || "Connected account" : "No account connected"}</span>
                  {connected && watchMode ? (
                    <span className="ml-2 settings-status-muted">{watchMode}</span>
                  ) : null}
                </div>
                <div className="grid grid-cols-4 gap-2 text-[12px] text-[#a9bed8]">
                  <span>{status?.entities_ingested ?? 0} entities</span>
                  <span>{status?.events_24h ?? 0} events</span>
                  <span>{status?.writes_blocked_week ?? 0} blocked</span>
                  <span>{status?.last_sync_at || "never"}</span>
                </div>
                <div className="flex items-center justify-end gap-2">
                  {connected ? (
                    <>
                      <button
                        type="button"
                        className="settings-action-muted"
                        onClick={() => void testConnection(vendor.id)}
                        aria-label={`Test ${vendor.label}`}
                      >
                        Test
                      </button>
                      <button
                        type="button"
                        className="settings-action-muted"
                        onClick={() => void viewEvents(vendor.id)}
                        aria-label={`View ${vendor.label} Events`}
                      >
                        Events
                      </button>
                      <button
                        type="button"
                        className="settings-action"
                        onClick={() => void sync(vendor.id)}
                        aria-label={`Sync ${vendor.label}`}
                      >
                        Sync Now
                      </button>
                      <button
                        type="button"
                        className="settings-action-muted"
                        onClick={() => void disconnect(vendor.id)}
                        aria-label={`Disconnect ${vendor.label}`}
                      >
                        Disconnect
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className="settings-action"
                      onClick={() => void connect(vendor.id)}
                      aria-label={`Connect ${vendor.label}`}
                    >
                      Connect
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </section>
      {drawerVendor ? (
        <section className="settings-panel mt-4">
          <h3 className="settings-panel-title">Recent Events</h3>
          <div className="settings-panel-body space-y-2">
            {recentEvents.filter((event) => event.vendor === drawerVendor).map((event, index) => (
              <div key={`${event.vendor}-${event.event_type}-${event.external_id || index}`} className="text-[13px] text-[#c9ddf6]">
                {event.event_type} {event.external_id || ""}
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
