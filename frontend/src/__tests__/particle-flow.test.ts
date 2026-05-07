import * as THREE from "three";
import { describe, expect, it } from "vitest";

import {
  particleColorForClusters,
  particlePositionAt,
  ParticleFlowController,
  type FlowParticle,
} from "@/lib/particle-flow";

const edge = {
  key: "billing_payments:incidents_ops",
  sourceCluster: "billing_payments" as const,
  targetCluster: "incidents_ops" as const,
};

describe("ParticleFlowController", () => {
  it("spawns particles on inter-hub edges", () => {
    const flow = new ParticleFlowController([edge]);
    flow.update(1200);
    expect(flow.activeCount()).toBeGreaterThan(0);
    flow.dispose();
  });

  it("moves a particle along its traversal", () => {
    const particle: FlowParticle = {
      edgeKey: "x",
      source: new THREE.Vector3(0, 0, 0),
      target: new THREE.Vector3(10, 0, 0),
      color: new THREE.Color("#fff"),
      startedAt: 0,
      durationMs: 2000,
      burst: false,
      trail: false,
    };
    expect(particlePositionAt(particle, 1000).x).toBeCloseTo(5);
    expect(particlePositionAt(particle, 2500).x).toBeCloseTo(10);
  });

  it("lerps particle color between clusters", () => {
    const color = particleColorForClusters("billing_payments", "incidents_ops");
    expect(color.getHexString()).not.toBe(new THREE.Color("#ec4899").getHexString());
    expect(color.getHexString()).not.toBe(new THREE.Color("#ef4444").getHexString());
  });

  it("bursts three particles for a new edge event", () => {
    const flow = new ParticleFlowController([]);
    flow.burst(edge, 0);
    expect(flow.activeCount()).toBe(6);
    flow.dispose();
  });

  it("expires completed particles", () => {
    const flow = new ParticleFlowController([]);
    flow.burst(edge, 0);
    flow.update(5000);
    expect(flow.activeCount()).toBe(0);
    flow.dispose();
  });

  it("uses the faster inter-hub spawn cadence", () => {
    const edges = Array.from({ length: 7 }, (_, i) => ({
      key: `billing_payments:incidents_ops:${i}`,
      sourceCluster: "billing_payments" as const,
      targetCluster: "incidents_ops" as const,
    }));
    const flow = new ParticleFlowController(edges);
    for (let t = 0; t <= 5000; t += 100) flow.update(t);
    expect(flow.activeCount()).toBeGreaterThan(30);
    flow.dispose();
  });

  it("trail particles follow main particles", () => {
    const flow = new ParticleFlowController([]);
    flow.burst(edge, 0);
    const drawRange = flow.points.geometry.drawRange;
    flow.update(100);
    expect(drawRange.count).toBeLessThanOrEqual(flow.activeCount());
    expect(flow.activeCount()).toBeGreaterThan(3);
    flow.dispose();
  });
});
