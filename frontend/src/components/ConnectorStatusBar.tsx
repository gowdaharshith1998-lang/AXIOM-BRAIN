import { useState } from "react";
import { Link } from "react-router-dom";

import { integrationPath } from "@/lib/source-vendor";
import {
  CONNECTOR_VENDORS,
  useConnectorsStore,
  type ConnectorStatus,
} from "@/state/connectors.store";

function formatLastSync(value: string | null | undefined): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const diffMs = Date.now() - parsed.getTime();
  if (diffMs < 60_000) return "just now";
  if (diffMs < 3_600_000) return `${Math.floor(diffMs / 60_000)}m ago`;
  if (diffMs < 86_400_000) return `${Math.floor(diffMs / 3_600_000)}h ago`;
  return parsed.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function ConnectorChip({ row }: { row: ConnectorStatus | undefined }) {
  const vendor = CONNECTOR_VENDORS.find((v) => v.id === row?.vendor);
  const label = vendor?.label ?? row?.vendor ?? "—";
  const connected = row?.status === "connected";
  const lastSync = formatLastSync(row?.last_sync_at);
  const needsConnect = !lastSync;
  const vendorId = vendor?.id ?? row?.vendor;

  const chipClass = needsConnect
    ? "border-[#1a2f4a]/70 bg-[#06101f]/40 text-[#8ba8cb]"
    : "border-[#1a2f4a] bg-[#06101f]/80 text-[#dce8ff]";

  const content = (
    <>
      <span
        className={`h-2 w-2 shrink-0 rounded-full ${connected && lastSync ? "bg-[#16f0a9] shadow-[0_0_8px_#16f0a9]" : "bg-[#5f728f]"}`}
        aria-hidden
      />
      <span className={`truncate text-[11px] font-medium ${needsConnect ? "text-[#8ba8cb]" : "text-[#dce8ff]"}`}>{label}</span>
      {lastSync ? <span className="shrink-0 text-[10px] text-[#7fa2c8]">{lastSync}</span> : null}
      {needsConnect && vendorId ? (
        <span className="shrink-0 text-[10px] text-[#7fa2c8]">Connect</span>
      ) : null}
    </>
  );

  if (needsConnect && vendorId) {
    return (
      <Link
        to={integrationPath(vendorId as (typeof CONNECTOR_VENDORS)[number]["id"])}
        className={`flex min-w-0 items-center gap-2 rounded-md border px-2.5 py-1 transition hover:border-[#2f8cff]/60 hover:bg-[#0b1a2e] ${chipClass}`}
        title={`Connect ${label}`}
        aria-label={`Connect ${label}`}
      >
        {content}
      </Link>
    );
  }

  return (
    <div
      className={`flex min-w-0 items-center gap-2 rounded-md border px-2.5 py-1 ${chipClass}`}
      title={connected ? `${label}: last sync ${lastSync}` : `${label}: disconnected`}
    >
      {content}
    </div>
  );
}

export function ConnectorStatusBar() {
  const connectors = useConnectorsStore((s) => s.connectors);
  const loading = useConnectorsStore((s) => s.loading);
  const syncingAll = useConnectorsStore((s) => s.syncingAll);
  const syncAll = useConnectorsStore((s) => s.syncAll);
  const [message, setMessage] = useState<string | null>(null);

  const byVendor = new Map(connectors.map((row) => [row.vendor, row]));

  async function onResync() {
    setMessage(null);
    const result = await syncAll();
    setMessage(result.ok ? "Sync started" : result.message ?? "Sync failed");
  }

  return (
    <div
      className="pointer-events-auto fixed left-[228px] right-0 top-0 z-20 border-b border-[#132339] bg-[#040b16]/88 px-4 py-2 backdrop-blur-md"
      role="region"
      aria-label="Connector status"
    >
      <div className="flex flex-nowrap items-center gap-2">
        <span className="shrink-0 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#7fa2c8]">
          Sources
        </span>
        {loading && connectors.length === 0 ? (
          <span className="shrink-0 text-[10px] text-[#7fa2c8]">Checking connectors…</span>
        ) : null}
        <div className="flex min-w-0 flex-1 flex-nowrap items-center gap-2 overflow-x-auto">
          {CONNECTOR_VENDORS.map((vendor) => (
            <ConnectorChip key={vendor.id} row={byVendor.get(vendor.id)} />
          ))}
        </div>
        <button
          type="button"
          className="ml-auto shrink-0 rounded-md border border-[#1d3452] bg-[#0b1a2e] px-3 py-1 text-[11px] font-medium text-[#9bc9ff] transition hover:border-[#2f8cff] hover:text-[#eef5ff] disabled:opacity-50"
          onClick={() => void onResync()}
          disabled={syncingAll || loading}
        >
          {syncingAll ? "Re-syncing…" : "Re-sync"}
        </button>
      </div>
      {message ? (
        <p className="mt-1 text-[10px] text-[#8ba8cb]" role="status">
          {message}
        </p>
      ) : null}
    </div>
  );
}
