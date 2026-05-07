import { describe, expect, it } from "vitest";
import * as THREE from "three";

import { buildIntraClusterMeshGroup, computeIntraClusterEdges } from "@/lib/cluster-mesh";
import type { VisibleEntitySlot } from "@/lib/hex-layout";
import type { Entity } from "@/state/brain.store";

function slot(id: string, x: number, y = 0): VisibleEntitySlot {
  const entity: Entity = {
    id,
    type: "file",
    data: {},
    source_id: null,
    created_at: "t",
    updated_at: "t",
    cluster_id: "billing_payments",
    composite_importance: 1,
  };
  return {
    entity,
    clusterId: "billing_payments",
    position: new THREE.Vector3(x, y, 0),
    ring: 1,
    slot: 0,
  };
}

describe("computeIntraClusterEdges", () => {
  it("connects each node to nearest same-cluster neighbors", () => {
    const edges = computeIntraClusterEdges([slot("a", 0), slot("b", 1), slot("c", 5)], "billing_payments", 1);
    expect(edges).toContainEqual({ sourceId: "a", targetId: "b", cluster: "billing_payments" });
  });

  it("deduplicates reciprocal nearest-neighbor edges", () => {
    const edges = computeIntraClusterEdges([slot("a", 0), slot("b", 1)], "billing_payments", 4);
    expect(edges).toHaveLength(1);
  });

  it("respects max edges per node", () => {
    const edges = computeIntraClusterEdges([slot("a", 0), slot("b", 1), slot("c", 2), slot("d", 3)], "billing_payments", 1);
    expect(edges.length).toBeLessThanOrEqual(3);
  });

  it("builds a low-opacity line group behind sphere nodes", () => {
    const group = buildIntraClusterMeshGroup([slot("a", 0), slot("b", 1), slot("c", 2)]);
    expect(group.children.length).toBe(1);
    expect(group.renderOrder).toBe(-2);
    const line = group.children[0] as THREE.LineSegments;
    expect((line.material as THREE.LineBasicMaterial).opacity).toBe(0.18);
  });
});
