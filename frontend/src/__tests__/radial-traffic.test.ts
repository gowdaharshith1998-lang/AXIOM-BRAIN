import * as THREE from "three";
import { describe, expect, it, vi } from "vitest";

import { CLUSTER_CENTROIDS, CLUSTER_COLORS } from "@/lib/cluster-layout";
import {
  radialTrafficColor,
  radialTrafficPositionAt,
  RadialTrafficController,
  type RadialTrafficDot,
} from "@/lib/radial-traffic";
import type { VisibleEntitySlot } from "@/lib/hex-layout";
import type { Entity } from "@/state/brain.store";

function slot(id: string): VisibleEntitySlot {
  const entity: Entity = {
    id,
    type: "thread",
    data: {},
    source_id: null,
    created_at: "t",
    updated_at: "t",
    cluster_id: "billing",
    composite_importance: 1,
  };
  return {
    entity,
    clusterId: "billing",
    position: CLUSTER_CENTROIDS.billing.clone().add(new THREE.Vector3(18, 0, 0)),
    ring: 1,
    slot: 0,
    hexRadius: 1.6,
  };
}

describe("RadialTrafficController", () => {
  it("spawns dots for each spoke", () => {
    const traffic = new RadialTrafficController([slot("a"), slot("b")]);
    for (let t = 0; t <= 4000; t += 100) traffic.update(t);
    expect(traffic.activeCount()).toBeGreaterThan(0);
    traffic.dispose();
  });

  it("dots travel hub to spoke", () => {
    const dot: RadialTrafficDot = {
      key: "a",
      source: new THREE.Vector3(0, 0, 0),
      target: new THREE.Vector3(10, 0, 0),
      color: new THREE.Color("#fff"),
      startedAt: 0,
      durationMs: 2000,
    };
    expect(radialTrafficPositionAt(dot, 1000).x).toBeCloseTo(5);
    expect(radialTrafficPositionAt(dot, 2500).x).toBeCloseTo(10);
  });

  it("dot color matches cluster", () => {
    expect(`#${radialTrafficColor(slot("a")).getHexString()}`).toBe(CLUSTER_COLORS.billing.toLowerCase());
  });

  it("disposes geometry and material", () => {
    const traffic = new RadialTrafficController([slot("a")]);
    const geometryDispose = vi.spyOn(traffic.points.geometry, "dispose");
    const material = traffic.points.material as THREE.PointsMaterial;
    const materialDispose = vi.spyOn(material, "dispose");
    traffic.dispose();
    expect(geometryDispose).toHaveBeenCalledOnce();
    expect(materialDispose).toHaveBeenCalledOnce();
  });

  it("supports slot replacement", () => {
    const traffic = new RadialTrafficController([slot("a")]);
    traffic.setSlots([slot("b"), slot("c")], 0);
    for (let t = 0; t <= 4000; t += 100) traffic.update(t);
    expect(traffic.activeCount()).toBeGreaterThan(0);
    traffic.dispose();
  });
});
