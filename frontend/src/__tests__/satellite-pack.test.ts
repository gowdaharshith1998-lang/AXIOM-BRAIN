import * as THREE from "three";
import { describe, expect, it } from "vitest";

import { packSatellites } from "@/lib/satellite-pack";

describe("packSatellites", () => {
  it("is deterministic for a fixed seed", () => {
    const centroid = new THREE.Vector3(10, -5, 2);
    const first = packSatellites({ centroid, count: 30, clusterRadius: 20, seed: 1337, baseHexRadius: 1.6 }).map(
      (p) => [p.ring, p.hexRadius, p.position.toArray()],
    );
    const second = packSatellites({ centroid, count: 30, clusterRadius: 20, seed: 1337, baseHexRadius: 1.6 }).map(
      (p) => [p.ring, p.hexRadius, p.position.toArray()],
    );
    expect(second).toEqual(first);
  });

  it("splits satellites into three rings with stable caps", () => {
    const centroid = new THREE.Vector3(0, 0, 0);
    const packed = packSatellites({ centroid, count: 40, clusterRadius: 20, seed: 1, baseHexRadius: 1.6 });
    const counts = packed.reduce(
      (acc, p) => {
        acc[p.ring]++;
        return acc;
      },
      { 0: 0, 1: 0, 2: 0 } as Record<0 | 1 | 2, number>,
    );
    expect(counts[0]).toBeGreaterThanOrEqual(8);
    expect(counts[0]).toBeLessThanOrEqual(12);
    expect(counts[0] + counts[1] + counts[2]).toBe(40);
  });

  it("keeps all satellites within the expected jittered radius bound", () => {
    const centroid = new THREE.Vector3(0, 0, 0);
    const clusterRadius = 28;
    const packed = packSatellites({ centroid, count: 60, clusterRadius, seed: 42, baseHexRadius: 1.6 });
    const maxDistance = Math.max(...packed.map((p) => p.position.length()));
    expect(maxDistance).toBeLessThanOrEqual(clusterRadius * 1.08);
  });
});
