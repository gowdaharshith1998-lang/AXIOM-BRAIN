import { describe, expect, it } from "vitest";

import {
  CLUSTER_CENTROIDS,
  CLUSTER_CENTROID_RADIUS,
  CLUSTER_COLORS,
  CLUSTER_IDS,
  CLUSTER_LABELS,
  clusterGravityForce,
  fibonacciSpherePoints,
  isClusterId,
} from "@/lib/cluster-layout";

describe("fibonacciSpherePoints", () => {
  it("distributes n points on a sphere with the requested radius", () => {
    const points = fibonacciSpherePoints(7, 100);
    expect(points).toHaveLength(7);
    for (const point of points) {
      expect(point.length()).toBeCloseTo(100, 3);
    }
  });

  it("places points at distinct positions", () => {
    const points = fibonacciSpherePoints(7, 100);
    const seen = new Set<string>();
    for (const point of points) {
      seen.add(`${point.x.toFixed(3)},${point.y.toFixed(3)},${point.z.toFixed(3)}`);
    }
    expect(seen.size).toBe(7);
  });

  it("spreads points across the sphere (covers all octants of y)", () => {
    // For n=7 the golden-angle distribution spans y from 1 down to -1.
    const points = fibonacciSpherePoints(7, 100);
    const ys = points.map((p) => p.y / 100).sort((a, b) => a - b);
    expect(ys[0]).toBeLessThan(-0.5);
    expect(ys[ys.length - 1]).toBeGreaterThan(0.5);
  });

  it("returns an empty array for non-positive n", () => {
    expect(fibonacciSpherePoints(0, 100)).toEqual([]);
  });
});

describe("CLUSTER_CENTROIDS", () => {
  it("provides one centroid per cluster id", () => {
    for (const id of CLUSTER_IDS) {
      expect(CLUSTER_CENTROIDS[id]).toBeDefined();
      expect(CLUSTER_CENTROIDS[id].length()).toBeCloseTo(CLUSTER_CENTROID_RADIUS, 3);
    }
  });

  it("provides a label and a color for each cluster", () => {
    for (const id of CLUSTER_IDS) {
      expect(CLUSTER_LABELS[id]).toBeTruthy();
      expect(CLUSTER_COLORS[id]).toMatch(/^#[0-9A-Fa-f]{6}$/);
    }
  });

  it("rejects non-cluster strings via isClusterId", () => {
    expect(isClusterId("billing_payments")).toBe(true);
    expect(isClusterId("not_a_cluster")).toBe(false);
    expect(isClusterId(null)).toBe(false);
    expect(isClusterId(undefined)).toBe(false);
  });
});

describe("clusterGravityForce", () => {
  it("pulls a classified node toward its cluster centroid", () => {
    const node = {
      cluster_id: "billing_payments",
      x: 0,
      y: 0,
      z: 0,
      vx: 0,
      vy: 0,
      vz: 0,
    };
    const force = clusterGravityForce(0.5);
    force.initialize([node]);
    force(1.0);

    const centroid = CLUSTER_CENTROIDS.billing_payments;
    expect(Math.sign(node.vx!)).toBe(Math.sign(centroid.x) || 0);
    expect(Math.sign(node.vy!)).toBe(Math.sign(centroid.y) || 0);
    expect(Math.sign(node.vz!)).toBe(Math.sign(centroid.z) || 0);
    // The velocity nudge magnitude should be (centroid - pos) * strength * alpha.
    expect(node.vx).toBeCloseTo(centroid.x * 0.5, 6);
    expect(node.vy).toBeCloseTo(centroid.y * 0.5, 6);
    expect(node.vz).toBeCloseTo(centroid.z * 0.5, 6);
  });

  it("scales the velocity nudge by the simulation alpha", () => {
    const node = {
      cluster_id: "growth_product",
      x: 0,
      y: 0,
      z: 0,
      vx: 0,
      vy: 0,
      vz: 0,
    };
    const force = clusterGravityForce(1.0);
    force.initialize([node]);
    force(0.1);
    const centroid = CLUSTER_CENTROIDS.growth_product;
    expect(node.vx).toBeCloseTo(centroid.x * 0.1, 6);
  });

  it("leaves unclassified nodes unaffected", () => {
    const node = {
      cluster_id: null,
      x: 10,
      y: -5,
      z: 3,
      vx: 0,
      vy: 0,
      vz: 0,
    };
    const force = clusterGravityForce(1.0);
    force.initialize([node]);
    force(1.0);
    expect(node.vx).toBe(0);
    expect(node.vy).toBe(0);
    expect(node.vz).toBe(0);
  });

  it("ignores unknown cluster ids without crashing", () => {
    const node = {
      cluster_id: "not_a_cluster",
      x: 1,
      y: 2,
      z: 3,
      vx: 0,
      vy: 0,
      vz: 0,
    };
    const force = clusterGravityForce(1.0);
    force.initialize([node]);
    force(1.0);
    expect(node.vx).toBe(0);
    expect(node.vy).toBe(0);
    expect(node.vz).toBe(0);
  });

  it("supports d3 force.strength() get/set conventions", () => {
    const force = clusterGravityForce(0.05);
    expect(force.strength()).toBe(0.05);
    const returned = force.strength(0.2);
    expect(returned).toBe(force);
    expect(force.strength()).toBe(0.2);
  });
});
