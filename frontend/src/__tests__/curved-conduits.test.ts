import * as THREE from "three";
import { describe, expect, it } from "vitest";

import {
  buildCurvedConduit,
  conduitPathsForEdges,
  createConduitLine,
  pointAtPathT,
  tangentAngleAtPathT,
} from "@/lib/curved-conduits";
import { ParticleFlowController } from "@/lib/particle-flow";

const edge = {
  key: "billing:execution_context",
  sourceCluster: "billing" as const,
  targetCluster: "execution_context" as const,
};

describe("curved conduits", () => {
  it("bezier passes through endpoints", () => {
    const source = new THREE.Vector3(0, 0, 0);
    const target = new THREE.Vector3(10, 0, 0);
    const path = buildCurvedConduit(source, target);
    expect(path[0]).toEqual(source);
    expect(path.at(-1)).toEqual(target);
  });

  it("bezier arcs in z", () => {
    const path = buildCurvedConduit(new THREE.Vector3(0, 0, 0), new THREE.Vector3(10, 0, 0));
    expect(Math.max(...path.map((point) => point.z))).toBeGreaterThan(0);
  });

  it("samples points along the path", () => {
    const path = buildCurvedConduit(new THREE.Vector3(0, 0, 0), new THREE.Vector3(10, 0, 0));
    expect(pointAtPathT(path, 0.5).x).toBeCloseTo(5);
  });

  it("chevron tangent aligns with path direction", () => {
    const path = buildCurvedConduit(new THREE.Vector3(0, 0, 0), new THREE.Vector3(10, 0, 0));
    expect(Math.abs(tangentAngleAtPathT(path, 0.5))).toBeLessThan(0.2);
  });

  it("creates a vertex-colored conduit line", () => {
    const [path] = conduitPathsForEdges([edge]);
    const line = createConduitLine(path);
    expect(line.geometry.getAttribute("color").count).toBe(path.points.length);
    expect((line.material as THREE.LineBasicMaterial).opacity).toBe(0.045);
  });

  it("keeps chevron count within max particles", () => {
    const flow = new ParticleFlowController(conduitPathsForEdges([edge]), 8);
    for (let t = 0; t < 5000; t += 50) flow.update(t);
    expect(flow.activeCount()).toBeLessThanOrEqual(8);
    flow.dispose();
  });

  it("conduit pulse spawns immediate chevrons", () => {
    const flow = new ParticleFlowController(conduitPathsForEdges([edge]));
    flow.pulse(edge, 0);
    expect(flow.activeCount()).toBeGreaterThan(6);
    flow.dispose();
  });
});
