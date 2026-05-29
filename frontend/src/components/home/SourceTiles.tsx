import { Link } from "react-router-dom";

import { SourceIcon } from "@/components/graph/SourceIcons";
import {
  integrationPath,
  SOURCE_VENDOR_COLOURS,
  SOURCE_VENDOR_LABELS,
  SOURCE_VENDOR_ORDER,
  vendorFromSourceId,
  type SourceVendorId,
} from "@/lib/source-vendor";
import { CONNECTOR_VENDORS, useConnectorsStore } from "@/state/connectors.store";
import { useBrainStore } from "@/state/brain.store";

function formatLastSync(value: string | null | undefined): string {
  if (!value) return "Not synced";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const diffMs = Date.now() - parsed.getTime();
  if (diffMs < 60_000) return "just now";
  if (diffMs < 3_600_000) return `${Math.floor(diffMs / 60_000)}m ago`;
  if (diffMs < 86_400_000) return `${Math.floor(diffMs / 3_600_000)}h ago`;
  return parsed.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function entityCountForVendor(vendor: SourceVendorId, entities: ReturnType<typeof useBrainStore.getState>["entities"]): number {
  let count = 0;
  for (const entity of entities.values()) {
    if (vendorFromSourceId(entity.source_id) === vendor) count++;
  }
  return count;
}

export function SourceTiles() {
  const entities = useBrainStore((s) => s.entities);
  const connectors = useConnectorsStore((s) => s.connectors);
  const byVendor = new Map(connectors.map((row) => [row.vendor, row]));

  return (
    <div className="grid grid-cols-5 gap-3">
      {SOURCE_VENDOR_ORDER.map((vendor) => {
        const status = byVendor.get(vendor);
        const connected = status?.status === "connected";
        const entityCount = entityCountForVendor(vendor, entities);
        const label = CONNECTOR_VENDORS.find((row) => row.id === vendor)?.label ?? SOURCE_VENDOR_LABELS[vendor];
        const colour = SOURCE_VENDOR_COLOURS[vendor];

        return (
          <Link
            key={vendor}
            to={connected ? integrationPath(vendor) : integrationPath(vendor)}
            className="group rounded-xl border border-[#1a2f4a] bg-[#06101f]/70 p-4 transition hover:border-[#2f8cff]/50 hover:bg-[#0b1a2e]"
          >
            <div className="flex items-center justify-between gap-2">
              <span style={{ color: colour }} aria-hidden>
                <SourceIcon vendor={vendor} className="h-5 w-5" />
              </span>
              <span
                className={`h-2 w-2 rounded-full ${connected ? "bg-[#16f0a9] shadow-[0_0_8px_#16f0a9]" : "bg-[#5f728f]"}`}
                aria-hidden
              />
            </div>
            <div className="mt-3 text-[15px] font-medium text-[#eef5ff]">{label}</div>
            <div className="mt-1 text-[12px] text-[#7fa2c8]">
              {entityCount.toLocaleString()} {entityCount === 1 ? "entity" : "entities"}
            </div>
            <div className="mt-2 text-[11px] text-[#8ba8cb]">
              {connected ? `Last sync ${formatLastSync(status?.last_sync_at)}` : "Not connected"}
            </div>
          </Link>
        );
      })}
    </div>
  );
}
