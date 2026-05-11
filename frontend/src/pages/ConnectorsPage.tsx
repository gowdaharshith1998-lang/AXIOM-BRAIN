import { useEffect, useMemo, useState, type FormEvent } from "react";

type ConnectorStatus = {
  vendor: string;
  status: "connected" | "disconnected" | "error";
  configured?: boolean;
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

type SetupForm = {
  oauth_client_id: string;
  oauth_client_secret: string;
  redirect_uri: string;
  webhook_secret: string;
  workspace_id: string;
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
  const [actionMessages, setActionMessages] = useState<Record<string, string>>({});
  const [setupVendor, setSetupVendor] = useState<string | null>(null);
  const [setupForm, setSetupForm] = useState<SetupForm>(() => emptySetupForm("github"));

  function setActionMessage(vendor: string, message: string) {
    setActionMessages((existing) => ({ ...existing, [vendor]: message }));
  }

  async function responseMessage(response: Response, fallback: string) {
    try {
      const payload = await response.json();
      return String(payload.detail || payload.error || fallback);
    } catch {
      return fallback;
    }
  }

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

  function openSetup(vendor: string) {
    setSetupVendor(vendor);
    setSetupForm(emptySetupForm(vendor));
  }

  async function startInstall(vendor: string) {
    setActionMessage(vendor, "Connecting...");
    try {
      const response = await fetch(`/api/internal/connectors/${vendor}/install`, { method: "POST" });
      if (!response.ok) {
        const message = await responseMessage(response, "Connector install failed");
        setActionMessage(vendor, message);
        if (response.status === 409) openSetup(vendor);
        return;
      }
      const payload = await response.json();
      if (typeof payload.authorize_url === "string") {
        window.open(payload.authorize_url, `axiom-${vendor}-oauth`, "width=720,height=780");
        setActionMessage(vendor, "Opening authorization");
        return;
      }
      setActionMessage(vendor, "Authorize URL unavailable");
    } catch {
      setActionMessage(vendor, "Connector request failed");
    }
  }

  async function connect(vendor: string) {
    const status = byVendor.get(vendor);
    if (status?.configured === false) {
      setActionMessage(vendor, "Connector setup required");
      openSetup(vendor);
      return;
    }
    await startInstall(vendor);
  }

  async function saveSetup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!setupVendor) return;
    const vendor = setupVendor;
    setActionMessage(vendor, "Saving connector setup...");
    try {
      const response = await fetch(`/api/internal/connectors/${vendor}/config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(setupForm),
      });
      if (!response.ok) {
        setActionMessage(vendor, await responseMessage(response, "Connector setup failed"));
        return;
      }
      await load();
      setSetupVendor(null);
      setActionMessage(vendor, "Connector setup saved");
      await startInstall(vendor);
    } catch {
      setActionMessage(vendor, "Connector request failed");
    }
  }

  async function sync(vendor: string) {
    setActionMessage(vendor, "Syncing...");
    try {
      const response = await fetch(`/api/internal/connectors/${vendor}/sync`, { method: "POST" });
      if (!response.ok) {
        setActionMessage(vendor, await responseMessage(response, "Connector sync failed"));
        return;
      }
      await load();
      setActionMessage(vendor, "Sync complete");
    } catch {
      setActionMessage(vendor, "Connector request failed");
    }
  }

  async function testConnection(vendor: string) {
    setActionMessage(vendor, "Testing...");
    try {
      const response = await fetch(`/api/internal/connectors/${vendor}/test`, { method: "POST" });
      if (!response.ok) {
        setActionMessage(vendor, await responseMessage(response, "Connection test failed"));
        return;
      }
      const payload = await response.json();
      setActionMessage(vendor, payload.ok ? "Connection OK" : `Connection ${payload.status || "failed"}`);
    } catch {
      setActionMessage(vendor, "Connector request failed");
    }
  }

  async function viewEvents(vendor: string) {
    setDrawerVendor(vendor);
    setActionMessage(vendor, "Loading events...");
    try {
      const response = await fetch(`/api/internal/connectors/${vendor}/events`);
      if (!response.ok) {
        setActionMessage(vendor, await responseMessage(response, "Could not load events"));
        return;
      }
      const payload = await response.json();
      if (Array.isArray(payload.events)) {
        setRecentEvents((existing) => [...payload.events, ...existing].slice(0, 50));
        setActionMessage(vendor, `${payload.events.length} recent events`);
      }
    } catch {
      setActionMessage(vendor, "Connector request failed");
    }
  }

  async function disconnect(vendor: string) {
    setActionMessage(vendor, "Disconnecting...");
    try {
      const response = await fetch(`/api/internal/connectors/${vendor}`, { method: "DELETE" });
      if (!response.ok) {
        setActionMessage(vendor, await responseMessage(response, "Disconnect failed"));
        return;
      }
      await load();
      setActionMessage(vendor, "Disconnected");
    } catch {
      setActionMessage(vendor, "Connector request failed");
    }
  }

  return (
    <div className="settings-stage">
      <section className="settings-panel">
        <h3 className="settings-panel-title">Connectors</h3>
        <div className="settings-panel-body space-y-3">
          {vendors.map((vendor) => {
            const status = byVendor.get(vendor.id);
            const connected = status?.status === "connected";
            const configured = status?.configured !== false;
            const watchMode = status?.watch_mode === "polling" ? "Polling" : null;
            return (
              <div
                key={vendor.id}
                className="grid grid-cols-[110px_120px_minmax(160px,1fr)_minmax(180px,240px)_auto] items-center gap-3 border-b border-[#173657] py-3 text-[13px]"
              >
                <div className="text-[15px] font-semibold text-[#e8f2ff]">{vendor.label}</div>
                <div>
                  <span className={connected ? "settings-status-good" : "settings-status-muted"}>
                    {connected ? "Connected" : "Disconnected"}
                  </span>
                </div>
                <div className="min-w-0 text-[#a9bed8]">
                  <span>{connected ? status?.account_label || "Connected account" : configured ? "No account connected" : "Setup required"}</span>
                  {connected && watchMode ? (
                    <span className="ml-2 settings-status-muted">{watchMode}</span>
                  ) : null}
                  {actionMessages[vendor.id] ? (
                    <div className="mt-1 truncate text-[12px] text-[#f6b770]" role="status">
                      {actionMessages[vendor.id]}
                    </div>
                  ) : null}
                </div>
                <div className="grid grid-cols-4 gap-2 text-[12px] text-[#a9bed8]">
                  <span>{status?.entities_ingested ?? 0} entities</span>
                  <span>{status?.events_24h ?? 0} events</span>
                  <span>{status?.writes_blocked_week ?? 0} blocked</span>
                  <span>{status?.last_sync_at || "never"}</span>
                </div>
                <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
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
      {setupVendor ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/72 px-4 backdrop-blur-sm">
          <form
            className="w-full max-w-lg rounded-xl border border-[#1a3550]/80 bg-[#06101b]/95 p-6 shadow-[0_0_60px_rgba(0,0,0,0.55)]"
            onSubmit={(event) => void saveSetup(event)}
            role="dialog"
            aria-modal="true"
            aria-label={`Set up ${labelFor(setupVendor)} connector`}
          >
            <h3 className="settings-panel-title">Set up {labelFor(setupVendor)}</h3>
            <p className="mt-2 text-[13px] text-[#9aa8c4]">
              Add the OAuth app credentials, then AXIOM will open the provider authorization flow.
            </p>
            <div className="mt-5 space-y-3">
              <ConnectorSetupField
                label="OAuth client ID"
                value={setupForm.oauth_client_id}
                onChange={(value) => setSetupForm((form) => ({ ...form, oauth_client_id: value }))}
              />
              <ConnectorSetupField
                label="OAuth client secret"
                type="password"
                value={setupForm.oauth_client_secret}
                onChange={(value) => setSetupForm((form) => ({ ...form, oauth_client_secret: value }))}
              />
              <ConnectorSetupField
                label="Redirect URI"
                value={setupForm.redirect_uri}
                onChange={(value) => setSetupForm((form) => ({ ...form, redirect_uri: value }))}
              />
              <ConnectorSetupField
                label={setupVendor === "slack" ? "Signing secret" : "Webhook secret"}
                type="password"
                value={setupForm.webhook_secret}
                onChange={(value) => setSetupForm((form) => ({ ...form, webhook_secret: value }))}
              />
              <ConnectorSetupField
                label="Workspace ID"
                value={setupForm.workspace_id}
                onChange={(value) => setSetupForm((form) => ({ ...form, workspace_id: value }))}
              />
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button type="button" className="settings-action-muted" onClick={() => setSetupVendor(null)}>
                Cancel
              </button>
              <button
                type="submit"
                className="settings-action"
                disabled={!setupForm.oauth_client_id.trim() || !setupForm.oauth_client_secret.trim() || !setupForm.redirect_uri.trim()}
              >
                Save & Connect
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}

function emptySetupForm(vendor: string): SetupForm {
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  return {
    oauth_client_id: "",
    oauth_client_secret: "",
    redirect_uri: `${origin}/api/internal/connectors/${vendor}/callback`,
    webhook_secret: "",
    workspace_id: "",
  };
}

function labelFor(vendor: string): string {
  return vendors.find((item) => item.id === vendor)?.label ?? vendor;
}

function ConnectorSetupField({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
}) {
  return (
    <label className="block text-[13px] text-[#a9bed8]">
      <span className="mb-1 block">{label}</span>
      <input
        className="h-[38px] w-full rounded-md border border-[#223b5c] bg-[#071225] px-3 text-[#e6f0ff] outline-none focus:border-[#2389ff]"
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
