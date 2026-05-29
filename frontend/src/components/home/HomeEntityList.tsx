import { useMemo } from "react";

import { vendorFromSourceId } from "@/lib/source-vendor";
import { useBrainStore, type Entity } from "@/state/brain.store";

function titleForEntity(entity: Entity): string {
  for (const key of ["title", "name", "subject", "label", "file_path"]) {
    const value = entity.data?.[key];
    if (typeof value === "string" && value.trim()) {
      return key === "file_path" ? (value.split("/").pop() ?? value) : value;
    }
  }
  return entity.id;
}

function sourceLabel(entity: Entity): string {
  const vendor = vendorFromSourceId(entity.source_id);
  if (!vendor) return "Unknown";
  return vendor.charAt(0).toUpperCase() + vendor.slice(1);
}

export function HomeEntityList() {
  const entities = useBrainStore((s) => s.entities);
  const select = useBrainStore((s) => s.select);

  const rows = useMemo(
    () =>
      Array.from(entities.values())
        .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
        .slice(0, 20),
    [entities],
  );

  return (
    <section className="rounded-xl border border-[#1a2f4a] bg-[#06101f]/50">
      <div className="border-b border-[#1a2f4a] px-4 py-3">
        <h2 className="text-[13px] font-semibold uppercase tracking-[0.14em] text-[#7fa2c8]">Recently updated</h2>
      </div>
      {rows.length === 0 ? (
        <div className="px-4 py-6 text-sm text-[#8ba8cb]">No entities ingested yet.</div>
      ) : (
        <div className="divide-y divide-[#132339]">
          {rows.map((entity) => (
            <button
              key={entity.id}
              type="button"
              className="flex w-full items-center gap-4 px-4 py-3 text-left transition hover:bg-[#0b1a2e]"
              onClick={() => select(entity.id)}
            >
              <span className="w-20 shrink-0 text-[11px] uppercase tracking-[0.1em] text-[#7fa2c8]">{sourceLabel(entity)}</span>
              <span className="min-w-0 flex-1 truncate text-sm text-[#eef5ff]">{titleForEntity(entity)}</span>
              <span className="shrink-0 text-[11px] text-[#8ba8cb]">
                {new Date(entity.updated_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
              </span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
