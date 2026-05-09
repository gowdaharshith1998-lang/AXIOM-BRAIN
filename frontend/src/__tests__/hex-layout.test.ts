import * as THREE from "three";
import { describe, expect, it } from "vitest";

import { CLUSTER_CENTROIDS, CLUSTER_IDS } from "@/lib/cluster-layout";
import { CLUSTER_RADIUS } from "@/lib/cluster-layout";
import {
  CLUSTER_RING_STEP,
  CLUSTER_VISIBLE_SLOTS,
  computeInterHubEdges,
  computeStarburstPositions,
  computeVisibleEntitySlots,
  HEX_CLUSTER_CENTROIDS,
  MAX_VISIBLE_PER_CLUSTER,
} from "@/lib/hex-layout";
import { HEX_NODE_RADIUS } from "@/lib/hex-geometry";
import type { Edge, Entity } from "@/state/brain.store";

function entity(id: string, cluster_id: string, composite_importance: number): Entity {
  return {
    id,
    type: "thread",
    data: {},
    source_id: null,
    created_at: "t",
    updated_at: "t",
    cluster_id,
    composite_importance,
  };
}

describe("hex cluster centroids", () => {
  it("places super-cluster hubs at distinct positions", () => {
    expect(Object.keys(HEX_CLUSTER_CENTROIDS)).toHaveLength(10);
    const unique = new Set(Object.values(HEX_CLUSTER_CENTROIDS).map((p) => p.toArray().join(",")));
    expect(unique.size).toBe(10);
  });

  it("keeps hub pairwise distance above the compact reference minimum", () => {
    const hubs = CLUSTER_IDS.map((id) => CLUSTER_CENTROIDS[id]);
    for (let i = 0; i < hubs.length; i++) {
      for (let j = i + 1; j < hubs.length; j++) {
        expect(hubs[i].distanceTo(hubs[j])).toBeGreaterThan(24);
      }
    }
  });

  it("frames all hubs from the default camera", () => {
    const camera = new THREE.PerspectiveCamera(60, 16 / 9, 1, 4000);
    camera.position.set(0, 0, 280);
    camera.lookAt(0, 0, 0);
    camera.updateMatrixWorld();
    camera.updateProjectionMatrix();
    for (const hub of Object.values(CLUSTER_CENTROIDS)) {
      const ndc = hub.clone().project(camera);
      expect(ndc.x).toBeGreaterThanOrEqual(-1);
      expect(ndc.x).toBeLessThanOrEqual(1);
      expect(ndc.y).toBeGreaterThanOrEqual(-1);
      expect(ndc.y).toBeLessThanOrEqual(1);
    }
  });
});

describe("computeStarburstPositions", () => {
  it("positions the top eighty entities per cluster", () => {
    const entities = Array.from({ length: 96 }, (_, i) => entity(`e${i}`, "billing", 1 - i / 100));
    const positions = computeStarburstPositions(entities);
    expect(positions.size).toBe(MAX_VISIBLE_PER_CLUSTER);
    expect(positions.has("e0")).toBe(true);
    expect(positions.has("e79")).toBe(true);
  });

  it("omits low-importance entities", () => {
    const entities = Array.from({ length: 96 }, (_, i) => entity(`e${i}`, "billing", 1 - i / 100));
    const positions = computeStarburstPositions(entities);
    expect(positions.has("e95")).toBe(false);
  });

  it("is deterministic", () => {
    const entities = Array.from({ length: 10 }, (_, i) => entity(`e${i}`, "company_knowledge", i / 10));
    const first = Array.from(computeStarburstPositions(entities).entries()).map(([id, p]) => [id, p.toArray()]);
    const second = Array.from(computeStarburstPositions(entities).entries()).map(([id, p]) => [id, p.toArray()]);
    expect(second).toEqual(first);
  });
});

describe("visible slots and inter-hub edges", () => {
  it("caps visible entities to eighty per cluster", () => {
    const entities = CLUSTER_IDS.flatMap((cluster) =>
      Array.from({ length: 96 }, (_, i) => entity(`${cluster}-${i}`, cluster, 1 - i / 100)),
    );
    const slots = computeVisibleEntitySlots(entities, CLUSTER_IDS);
    expect(slots).toHaveLength(CLUSTER_IDS.length * MAX_VISIBLE_PER_CLUSTER);
  });

  it("uses the OMNIX dense five-ring slot budget", () => {
    expect(CLUSTER_VISIBLE_SLOTS).toEqual([8, 12, 16, 20, 24]);
    expect(MAX_VISIBLE_PER_CLUSTER).toBe(80);
    expect(CLUSTER_RING_STEP).toBe(6);
  });

  it("honors a reduced visible node budget", () => {
    const entities = Array.from({ length: 90 }, (_, i) => entity(`budget-${i}`, "billing", 1 - i / 100));
    const slots = computeVisibleEntitySlots(entities, CLUSTER_IDS, 40);
    expect(slots).toHaveLength(40);
    expect(slots.at(-1)?.entity.id).toBe("budget-39");
  });

  it("assigns per-ring hex radii and stays within cluster radius bounds", () => {
    const entities = Array.from({ length: 80 }, (_, i) => entity(`k-${i}`, "company_knowledge", 1 - i / 100));
    const slots = computeVisibleEntitySlots(entities, ["company_knowledge"]);
    const allowed = new Set([HEX_NODE_RADIUS * 1.4, HEX_NODE_RADIUS * 1.0, HEX_NODE_RADIUS * 0.7]);
    for (const slot of slots) {
      expect(allowed.has(slot.hexRadius)).toBe(true);
      expect(slot.position.distanceTo(CLUSTER_CENTROIDS.company_knowledge)).toBeLessThanOrEqual(
        CLUSTER_RADIUS.company_knowledge * 1.08,
      );
    }
  });

  it("creates cross-cluster hub edges only for connected pairs", () => {
    const entities = new Map<string, Entity>([
      ["a", entity("a", "billing", 1)],
      ["b", entity("b", "execution_context", 1)],
      ["c", entity("c", "execution_context", 1)],
    ]);
    const edges: Edge[] = [
      { id: "same", source_id: "b", target_id: "c", relationship: "mentions", data: {}, created_at: "t" },
      { id: "cross", source_id: "a", target_id: "b", relationship: "mentions", data: {}, created_at: "t" },
    ];
    expect(computeInterHubEdges(edges, entities)).toEqual([
      { key: "billing:execution_context", sourceCluster: "billing", targetCluster: "execution_context", weight: 1 },
    ]);
  });

  it("never exceeds ten choose two inter-hub edges", () => {
    const entities = new Map(CLUSTER_IDS.map((cluster) => [cluster, entity(cluster, cluster, 1)]));
    const edges: Edge[] = [];
    for (const source of CLUSTER_IDS) {
      for (const target of CLUSTER_IDS) {
        if (source !== target) {
          edges.push({ id: `${source}:${target}`, source_id: source, target_id: target, relationship: "x", data: {}, created_at: "t" });
        }
      }
    }
    expect(computeInterHubEdges(edges, entities)).toHaveLength(45);
  });
});
