import { useEffect, useMemo, useState } from "react";

type ConnectorStatus = {
  vendor: string;
  status: "connected" | "disconnected" | "error";
  account_label?: string | null;
  last_sync_at?: string | null;
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

  async function load() {
    const response = await fetch("/api/internal/connectors/status");
    if (!response.ok) return;
    const payload = await response.json();
    setStatuses(Array.isArray(payload.connectors) ? payload.connectors : []);
  }

  useEffect(() => {
    void load();
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

  return (
    <div className="settings-stage">
      <section className="settings-panel">
        <h3 className="settings-panel-title">Connectors</h3>
        <div className="settings-panel-body space-y-3">
          {vendors.map((vendor) => {
            const status = byVendor.get(vendor.id);
            const connected = status?.status === "connected";
            const watchMode = vendor.id === "notion" ? "Polling" : null;
            return (
              <div
                key={vendor.id}
                className="grid grid-cols-[160px_150px_1fr_240px] items-center gap-3 border-b border-[#173657] py-3 text-[13px]"
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
                <div className="flex items-center justify-end gap-2">
                  {connected ? (
                    <>
                      <button
                        type="button"
                        className="settings-action"
                        onClick={() => void sync(vendor.id)}
                        aria-label={`Sync ${vendor.label}`}
                      >
                        Sync Now
                      </button>
                      <button type="button" className="settings-action-muted">
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
    </div>
  );
}
