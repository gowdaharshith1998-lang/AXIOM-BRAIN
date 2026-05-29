import { useEffect } from "react";

import { useBrainStore } from "@/state/brain.store";

function connectionCounts(edges: ReturnType<typeof useBrainStore.getState>["edges"]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const edge of edges.values()) {
    counts.set(edge.source_id, (counts.get(edge.source_id) ?? 0) + 1);
    counts.set(edge.target_id, (counts.get(edge.target_id) ?? 0) + 1);
  }
  return counts;
}

export function useDatasetLineageProbe() {
  const entities = useBrainStore((s) => s.entities);
  const edges = useBrainStore((s) => s.edges);
  const datasetHasLineage = useBrainStore((s) => s.datasetHasLineage);
  const setDatasetHasLineage = useBrainStore((s) => s.setDatasetHasLineage);

  useEffect(() => {
    if (datasetHasLineage || entities.size === 0) return;

    let cancelled = false;
    const counts = connectionCounts(edges);
    const candidates = Array.from(entities.values())
      .sort((a, b) => (counts.get(b.id) ?? 0) - (counts.get(a.id) ?? 0))
      .slice(0, 5);

    void (async () => {
      for (const entity of candidates) {
        try {
          const response = await fetch(`/api/entities/${encodeURIComponent(entity.id)}/lineage?depth=1`);
          if (!response.ok) continue;
          const payload = (await response.json()) as { nodes?: unknown[] };
          if (!cancelled && Array.isArray(payload.nodes) && payload.nodes.length > 0) {
            setDatasetHasLineage(true);
            return;
          }
        } catch {
          // ignore probe failures
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [datasetHasLineage, entities, edges, setDatasetHasLineage]);
}
