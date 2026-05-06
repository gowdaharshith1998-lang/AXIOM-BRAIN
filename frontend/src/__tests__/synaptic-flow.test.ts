import * as THREE from "three";
import { describe, expect, it } from "vitest";

import {
  createSynapticFlow,
  disposeSynapticFlow,
  particleCountForFps,
  particlePositionAtT,
  wrapParticleT,
  type SynapticFlowEdge,
} from "@/lib/particles/synaptic-flow";

const edge: SynapticFlowEdge = {
  id: "edge-1",
  sourceId: "source",
  targetId: "target",
  relationship: "CODE_RESOLVES_TICKET",
};

describe("synaptic-flow", () => {
  it("uses three particles per edge in full FPS state", () => {
    expect(particleCountForFps(4, "full")).toBe(12);
  });

  it("uses two particles per edge in half FPS state", () => {
    expect(particleCountForFps(4, "half")).toBe(8);
  });

  it("drops particles in emergency FPS state", () => {
    expect(particleCountForFps(4, "emergency")).toBe(0);
  });

  it("places a particle at the edge midpoint when t is 0.5", () => {
    const midpoint = particlePositionAtT(new THREE.Vector3(0, 0, 0), new THREE.Vector3(10, 4, 2), 0.5);
    expect(midpoint.x).toBe(5);
    expect(midpoint.y).toBe(2);
    expect(midpoint.z).toBe(1);
  });

  it("wraps particles from the target back to the source", () => {
    expect(wrapParticleT(1)).toBe(0);
    expect(wrapParticleT(1.25)).toBe(0.25);
  });

  it("rebuilds particle count when FPS state changes", () => {
    const scene = new THREE.Scene();
    const flow = createSynapticFlow(scene, [edge], new Map([[edge.id, 0]]), () => ({
      source: new THREE.Vector3(0, 0, 0),
      target: new THREE.Vector3(10, 0, 0),
    }));

    expect(flow.particleCount()).toBe(3);
    flow.updateSynapticFlow(0, 16, "half");
    expect(flow.particleCount()).toBe(2);
    flow.updateSynapticFlow(16, 16, "emergency");
    expect(flow.particleCount()).toBe(0);

    disposeSynapticFlow();
  });
});
