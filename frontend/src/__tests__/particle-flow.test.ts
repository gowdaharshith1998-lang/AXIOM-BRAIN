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
    expect(flow.activeCount()).toBe(3);
    flow.dispose();
  });

  it("expires completed particles", () => {
    const flow = new ParticleFlowController([]);
    flow.burst(edge, 0);
    flow.update(5000);
    expect(flow.activeCount()).toBe(0);
    flow.dispose();
  });
});
