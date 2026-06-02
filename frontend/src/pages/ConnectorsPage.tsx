import { useEffect, useMemo, useState, type FormEvent } from "react";

import { requestRaw } from "@/lib/http";
import { wsConnect } from "@/lib/ws";
import {
  CONNECTOR_VENDORS,
  useConnectorsStore,
} from "@/state/connectors.store";

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

export function ConnectorsPage({ embedded = false }: { embedded?: boolean }) {
  const statuses = useConnectorsStore((s) => s.connectors);
  const fetchStatuses = useConnectorsStore((s) => s.fetchStatuses);
  const incrementConnectorEvents = useConnectorsStore((s) => s.incrementConnectorEvents);
  const [recentEvents, setRecentEvents] = useState<RecentEvent[]>([]);
  const [drawerVendor, setDrawerVendor] = useState<string | null>(null);
  const [actionMessages, setActionMessages] = useState<Record<string, string>>({});
  const [setupVendor, setSetupVendor] = useState<string | null>(null);
  const [setupForm, setSetupForm] = useState<SetupForm>(() => emptySetupForm("github"));
  const [setupSaving, setSetupSaving] = useState(false);
  const [setupError, setSetupError] = useState<string | null>(null);

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

  useEffect(() => {
    void fetchStatuses();
  }, [fetchStatuses]);

  useEffect(() => {
    const onOAuthMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return;
      const data = event.data as { type?: string; vendor?: string; ok?: boolean; detail?: string } | null;
      if (!data || data.type !== "axiom:connector-oauth" || !data.vendor) return;
      void fetchStatuses();
      setActionMessage(
        data.vendor,
        data.ok ? data.detail || "Connected" : data.detail || "Authorization failed",
      );
    };
    window.addEventListener("message", onOAuthMessage);
    return () => window.removeEventListener("message", onOAuthMessage);
  }, [fetchStatuses]);

  useEffect(() => {
    if (typeof WebSocket === "undefined") return;
    const socket = wsConnect("/ws/brain");
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
            incrementConnectorEvents(vendor);
          }
        }
      } catch {
        // ignore malformed websocket events
      }
    };
    return () => socket.close();
  }, [incrementConnectorEvents]);

  const byVendor = useMemo(
    () => new Map(statuses.map((status) => [status.vendor, status])),
    [statuses],
  );

  function openSetup(vendor: string) {
    setSetupVendor(vendor);
    setSetupForm(emptySetupForm(vendor));
    setSetupError(null);
    setSetupSaving(false);
  }

  async function startInstall(vendor: string): Promise<{ ok: boolean; error?: string }> {
    setActionMessage(vendor, "Connecting...");
    try {
      const response = await requestRaw(`/api/internal/connectors/${vendor}/install`, { method: "POST" });
      if (!response.ok) {
        const message = await responseMessage(response, "Connector install failed");
        setActionMessage(vendor, message);
        if (response.status === 409) openSetup(vendor);
        return { ok: false, error: message };
      }
      const payload = await response.json();
      if (typeof payload.authorize_url === "string") {
        const popup = window.open(payload.authorize_url, `axiom-${vendor}-oauth`, "width=720,height=780");
        if (!popup) {
          const message = "Popup blocked. Allow popups for this site, then try again.";
          setActionMessage(vendor, message);
          return { ok: false, error: message };
        }
        setActionMessage(vendor, "Complete authorization in the popup window");
        return { ok: true };
      }
      const message = "Authorize URL unavailable";
      setActionMessage(vendor, message);
      return { ok: false, error: message };
    } catch {
      const message = "Connector request failed";
      setActionMessage(vendor, message);
      return { ok: false, error: message };
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
    if (!setupVendor || setupSaving) return;
    const vendor = setupVendor;
    setSetupSaving(true);
    setSetupError(null);
    setActionMessage(vendor, "Saving connector setup...");
    try {
      const response = await requestRaw(`/api/internal/connectors/${vendor}/config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(setupForm),
      });
      if (!response.ok) {
        const message = await responseMessage(response, "Connector setup failed");
        setSetupError(message);
        setActionMessage(vendor, message);
        return;
      }
      await fetchStatuses();
      const install = await startInstall(vendor);
      if (install.ok) {
        setSetupVendor(null);
        return;
      }
      setSetupError(install.error || "Could not start authorization");
    } catch {
      const message = "Connector request failed";
      setSetupError(message);
      setActionMessage(vendor, message);
    } finally {
      setSetupSaving(false);
    }
  }

  async function sync(vendor: string) {
    setActionMessage(vendor, "Syncing...");
    try {
      const response = await requestRaw(`/api/internal/connectors/${vendor}/sync`, { method: "POST" });
      if (!response.ok) {
        setActionMessage(vendor, await responseMessage(response, "Connector sync failed"));
        return;
      }
      await fetchStatuses();
      setActionMessage(vendor, "Sync complete");
    } catch {
      setActionMessage(vendor, "Connector request failed");
    }
  }

  async function testConnection(vendor: string) {
    setActionMessage(vendor, "Testing...");
    try {
      const response = await requestRaw(`/api/internal/connectors/${vendor}/test`, { method: "POST" });
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
      const response = await requestRaw(`/api/internal/connectors/${vendor}/events`);
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
      const response = await requestRaw(`/api/internal/connectors/${vendor}`, { method: "DELETE" });
      if (!response.ok) {
        setActionMessage(vendor, await responseMessage(response, "Disconnect failed"));
        return;
      }
      await fetchStatuses();
      setActionMessage(vendor, "Disconnected");
    } catch {
      setActionMessage(vendor, "Connector request failed");
    }
  }

  const content = (
    <>
      <section className="settings-panel">
        <h3 className="settings-panel-title">Connectors</h3>
        <div className="settings-panel-body space-y-3">
          {CONNECTOR_VENDORS.map((vendor) => {
            const status = byVendor.get(vendor.id);
            const connected = status?.status === "connected";
            const configured = status?.configured !== false;
            const watchMode = status?.watch_mode === "polling" ? "Polling" : null;
            return (
              <div key={vendor.id} className="settings-connector-row">
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
                <div className="settings-connector-metrics">
                  <span>{status?.entities_ingested ?? 0} entities</span>
                  <span>{status?.events_24h ?? 0} events</span>
                  <span>{status?.writes_blocked_week ?? 0} blocked</span>
                  <span>{status?.last_sync_at || "never"}</span>
                </div>
                <div className="settings-connector-actions">
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
            {setupError ? (
              <div className="mt-4 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-[13px] text-red-100" role="alert">
                {setupError}
              </div>
            ) : null}
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
              <button type="button" className="settings-action-muted" disabled={setupSaving} onClick={() => setSetupVendor(null)}>
                Cancel
              </button>
              <button
                type="submit"
                className="settings-action"
                disabled={
                  setupSaving ||
                  !setupForm.oauth_client_id.trim() ||
                  !setupForm.oauth_client_secret.trim() ||
                  !setupForm.redirect_uri.trim()
                }
              >
                {setupSaving ? "Saving..." : "Save & Connect"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </>
  );

  return embedded ? content : <div className="settings-stage">{content}</div>;
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
  return CONNECTOR_VENDORS.find((item) => item.id === vendor)?.label ?? vendor;
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
