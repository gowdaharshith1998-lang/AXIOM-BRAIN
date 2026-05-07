import * as THREE from "three";
import { describe, expect, it } from "vitest";

import {
  CLUSTER_AURA_RADIUS,
  auraOpacityAt,
  auraRadiusAt,
  auraScaleAt,
  clusterAuraPeriod,
  clusterAuraPhase,
  createClusterAuras,
  setAurasVisible,
  updateClusterAuras,
} from "@/components/ClusterAura";
import { CLUSTER_CENTROIDS, CLUSTER_COLORS, CLUSTER_IDS } from "@/lib/cluster-layout";

describe("cluster auras", () => {
  it("renders seven auras", () => {
    expect(createClusterAuras()).toHaveLength(7);
  });

  it("matches aura color to cluster id", () => {
    const auras = createClusterAuras();
    for (const aura of auras) {
      const cluster = aura.userData.cluster as keyof typeof CLUSTER_COLORS;
      expect(`#${aura.material.color.getHexString()}`).toBe(CLUSTER_COLORS[cluster]);
    }
  });

  it("positions each aura at the cluster centroid", () => {
    const auras = createClusterAuras();
    for (const aura of auras) {
      const cluster = aura.userData.cluster as keyof typeof CLUSTER_CENTROIDS;
      expect(aura.position.distanceTo(CLUSTER_CENTROIDS[cluster])).toBeLessThan(0.001);
    }
  });

  it("pulses with idle breathing", () => {
    expect(auraRadiusAt(1000)).not.toBe(CLUSTER_AURA_RADIUS);
    const auras = createClusterAuras();
    updateClusterAuras(auras, 1000);
    expect(auras[0].scale.x).not.toBe(1);
  });

  it("has one aura per canonical cluster", () => {
    const seen = new Set(createClusterAuras().map((aura) => aura.userData.cluster));
    expect(seen).toEqual(new Set(CLUSTER_IDS));
  });

  it("uses normal blending", () => {
    const [aura] = createClusterAuras();
    expect(aura.material.blending).toBe(THREE.NormalBlending);
  });

  it("keeps aura opacity subtle", () => {
    const [aura] = createClusterAuras();
    expect(aura.material.opacity).toBeLessThanOrEqual(0.06);
  });

  it("toggles visibility for all seven auras", () => {
    const auras = createClusterAuras();
    setAurasVisible(auras, false);
    expect(auras.every((aura) => aura.visible === false)).toBe(true);
    setAurasVisible(auras, true);
    expect(auras.every((aura) => aura.visible === true)).toBe(true);
  });

  it("gives each cluster a distinct pulse phase", () => {
    const phases = CLUSTER_IDS.map((_, index) => clusterAuraPhase(index));
    expect(new Set(phases).size).toBe(CLUSTER_IDS.length);
  });

  it("gives each cluster a distinct breathing period", () => {
    const periods = CLUSTER_IDS.map((_, index) => clusterAuraPeriod(index));
    expect(new Set(periods).size).toBe(CLUSTER_IDS.length);
    expect(Math.min(...periods)).toBe(5000);
    expect(Math.max(...periods)).toBe(8000);
  });

  it("updates scale and opacity asynchronously by index", () => {
    expect(auraScaleAt(0, 1600)).not.toBe(auraScaleAt(1, 1600));
    expect(auraOpacityAt(0, 1600)).not.toBe(auraOpacityAt(1, 1600));
  });
});
