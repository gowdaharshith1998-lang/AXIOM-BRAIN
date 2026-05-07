import { CLUSTER_IDS, isClusterId } from "@/lib/cluster-layout";
import { useBrainStore } from "@/state/brain.store";
import type { Edge, Entity } from "@/state/brain.store";

export function computeCrossClusterCount(edges: Iterable<Edge>, entities: Map<string, Entity>): number {
  let count = 0;
  for (const edge of edges) {
    const source = entities.get(edge.source_id)?.cluster_id;
    const target = entities.get(edge.target_id)?.cluster_id;
    if (isClusterId(source) && isClusterId(target) && source !== target) count++;
  }
  return count;
}

export function healthColor(percent: number): string {
  if (percent > 90) return "#22c55e";
  if (percent >= 70) return "#eab308";
  return "#ef4444";
}

export function computeHealthPercent(connectionStatus: string, totalEntities: number, lowConfidenceCount = 0): number {
  const offlinePenalty = connectionStatus === "offline" ? 0.3 : connectionStatus === "syncing" ? 0.08 : 0.02;
  const confidencePenalty = totalEntities > 0 ? 0.2 * Math.min(1, lowConfidenceCount / totalEntities) : 0;
  return Math.round(Math.max(0, Math.min(1, 1 - offlinePenalty - confidencePenalty)) * 100);
}

function displayName(entity: Entity): string {
  const data = entity.data ?? {};
  return (
    (typeof data.name === "string" && data.name) ||
    (typeof data.title === "string" && data.title) ||
    (typeof data.subject === "string" && data.subject) ||
    entity.id
  );
}

export function HUD() {
  const entities = useBrainStore((s) => s.entities);
  const edges = useBrainStore((s) => s.edges);
  const selectedId = useBrainStore((s) => s.selectedId);
  const connectionStatus = useBrainStore((s) => s.connectionStatus);
  const selected = selectedId ? entities.get(selectedId) : null;
  const crossCluster = computeCrossClusterCount(edges.values(), entities);
  const health = computeHealthPercent(connectionStatus, entities.size);
  const color = healthColor(health);
  const statusLabel =
    connectionStatus === "syncing" ? "syncing" : connectionStatus === "offline" ? "offline" : "live";
  const statusColor =
    connectionStatus === "syncing" ? "#eab308" : connectionStatus === "offline" ? "#ef4444" : "#22c55e";

  const resetView = () => {
    window.dispatchEvent(new Event("axiom:reset-view"));
  };

  const rows = [
    ["Entities", entities.size],
    ["Edges", edges.size],
    ["Agents", 0],
    ["Receipts", 0],
    ["Low-confidence", "--"],
    ["Cross-cluster", crossCluster],
  ] as const;

  return (
    <>
      <aside className="pointer-events-none fixed right-4 top-4 z-20 w-[280px] rounded-lg border border-white/10 bg-[#0a0c14]/70 p-4 font-mono text-xs text-white shadow-2xl backdrop-blur">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2 font-semibold tracking-[0.18em] text-white/90">
            <span className="animate-pulse text-[#eab308]">⚡</span>
            <span>BRAIN</span>
          </div>
          <div className="flex items-center gap-1.5 uppercase text-white/60">
            <span
              className={`h-2 w-2 rounded-full ${connectionStatus === "live" ? "animate-pulse" : ""}`}
              style={{ backgroundColor: statusColor }}
              aria-hidden="true"
            />
            <span>{statusLabel}</span>
          </div>
        </div>

        <div className="space-y-2">
          {rows.map(([label, value]) => (
            <div key={label} className="flex items-center justify-between">
              <span className="text-white/55">{label}</span>
              <span className="text-white">{value}</span>
            </div>
          ))}
        </div>

        <div className="mt-4">
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-white/55">HEALTH</span>
            <span style={{ color }}>{health}%</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
            <div className="h-full rounded-full transition-[width]" style={{ width: `${health}%`, backgroundColor: color }} />
          </div>
        </div>

        {selected && (
          <div className="mt-4 border-t border-white/10 pt-3">
            <div className="mb-1 text-[10px] uppercase tracking-[0.18em] text-white/40">Selected</div>
            <div className="truncate text-white/85">
              {selected.type} · {displayName(selected).slice(0, 28)}
            </div>
          </div>
        )}
      </aside>

      <button
        type="button"
        onClick={resetView}
        className="fixed left-4 top-4 z-20 rounded-md border border-white/10 bg-black/45 px-3 py-1.5 font-mono text-xs text-white/75 shadow-lg backdrop-blur transition hover:border-white/25 hover:bg-black/70 hover:text-white focus:outline-none focus:ring-2 focus:ring-white/40"
      >
        ⟲ Reset View
      </button>
      <div className="sr-only" aria-hidden="true">
        {CLUSTER_IDS.length}
      </div>
    </>
  );
}
