import { describe, expect, it } from "vitest";

import { computeClusterForceCentroids } from "@/lib/cluster-force-layout";
import type { ClusterId } from "@/lib/cluster-layout";
import type { Edge, Entity } from "@/state/brain.store";

describe("computeClusterForceCentroids", () => {
  it("is deterministic for identical inputs + seed", () => {
    const clusterIds = ["customers", "policies", "billing"] as const satisfies readonly ClusterId[];
    const entities: Entity[] = [
      { id: "a", type: "t", data: {}, source_id: null, created_at: "", updated_at: "", cluster_id: "customers" },
      { id: "b", type: "t", data: {}, source_id: null, created_at: "", updated_at: "", cluster_id: "policies" },
      { id: "c", type: "t", data: {}, source_id: null, created_at: "", updated_at: "", cluster_id: "billing" },
    ];
    const edges: Edge[] = [
      { id: "e1", source_id: "a", target_id: "b", relationship: "related", data: {}, created_at: "" },
      { id: "e2", source_id: "a", target_id: "b", relationship: "related", data: {}, created_at: "" },
      { id: "e3", source_id: "b", target_id: "c", relationship: "related", data: {}, created_at: "" },
    ];
    const entitiesById = new Map(entities.map((e) => [e.id, e]));

    const r1 = computeClusterForceCentroids({ clusterIds, entitiesById, edges, seed: 42 });
    const r2 = computeClusterForceCentroids({ clusterIds, entitiesById, edges, seed: 42 });

    for (const id of clusterIds) {
      const a = r1.centroids[id].toArray().map((v) => v.toFixed(6)).join(",");
      const b = r2.centroids[id].toArray().map((v) => v.toFixed(6)).join(",");
      expect(a).toBe(b);
    }
  });
});

