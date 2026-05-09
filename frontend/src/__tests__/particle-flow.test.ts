import * as THREE from "three";
import { describe, expect, it } from "vitest";

import {
  particleColorForClusters,
  particlePositionAt,
  ParticleFlowController,
  type FlowParticle,
} from "@/lib/particle-flow";

const edge = {
  key: "billing:execution_context",
  sourceCluster: "billing" as const,
  targetCluster: "execution_context" as const,
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
    const color = particleColorForClusters("billing", "execution_context");
    expect(color.getHexString()).not.toBe(new THREE.Color("#4dd3b8").getHexString());
    expect(color.getHexString()).not.toBe(new THREE.Color("#2b7fff").getHexString());
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

  it("keeps persistent dotted streams active across conduits", () => {
    const edges = Array.from({ length: 7 }, (_, i) => ({
      key: `billing:execution_context:${i}`,
      sourceCluster: "billing" as const,
      targetCluster: "execution_context" as const,
    }));
    const flow = new ParticleFlowController(edges);
    for (let t = 0; t <= 5000; t += 100) flow.update(t);
    expect(flow.activeCount()).toBeGreaterThan(20);
    flow.dispose();
  });

  it("trail particles follow main particles", () => {
    const flow = new ParticleFlowController([]);
    flow.burst(edge, 0);
    flow.update(100);
    expect(flow.points.children.filter((child) => child.visible)).toHaveLength(flow.activeCount());
    expect(flow.activeCount()).toBeGreaterThan(3);
    flow.dispose();
  });

  it("pulse doubles conduit activity window", () => {
    const flow = new ParticleFlowController([edge]);
    flow.pulse(edge, 0);
    expect(flow.activeCount()).toBeGreaterThan(6);
    flow.dispose();
  });
});
