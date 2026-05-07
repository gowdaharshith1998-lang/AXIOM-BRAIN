import { CLUSTER_CENTROIDS, CLUSTER_COLORS, CLUSTER_IDS } from "@/lib/cluster-layout";
import { computeVisibleEntitySlots, countEntitiesByCluster } from "@/lib/hex-layout";
import type { Edge, Entity } from "@/state/brain.store";

export type ExportableBrainState = {
  entities: Map<string, Entity>;
  edges: Map<string, Edge>;
};

export function visibleExportData(state: ExportableBrainState) {
  const visibleIds = new Set(computeVisibleEntitySlots(state.entities.values(), CLUSTER_IDS).map((slot) => slot.entity.id));
  return {
    version: "0.1",
    timestamp: new Date().toISOString(),
    entities: Array.from(state.entities.values()).filter((entity) => visibleIds.has(entity.id)),
    edges: Array.from(state.edges.values()),
    clusters: CLUSTER_IDS.map((id) => ({
      id,
      color: CLUSTER_COLORS[id],
      centroid: CLUSTER_CENTROIDS[id].toArray(),
      count: countEntitiesByCluster(state.entities.values(), id),
    })),
  };
}

export function exportVisibleAsJson(state: ExportableBrainState): void {
  const data = visibleExportData(state);
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `axiom-brain-${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}
