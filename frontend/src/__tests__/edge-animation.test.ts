import * as THREE from "three";
import { describe, expect, it } from "vitest";

import { EDGE_DRAW_MS, edgeDrawEndpoint, isEdgeDrawActive } from "@/lib/edge-animation";

describe("new edge animation", () => {
  it("starts at the source endpoint", () => {
    const source = new THREE.Vector3(0, 0, 0);
    const target = new THREE.Vector3(10, 0, 0);
    expect(edgeDrawEndpoint(source, target, 0).x).toBe(0);
  });

  it("draws to target over four hundred ms", () => {
    const source = new THREE.Vector3(0, 0, 0);
    const target = new THREE.Vector3(10, 0, 0);
    expect(edgeDrawEndpoint(source, target, EDGE_DRAW_MS).x).toBe(10);
  });

  it("is active before the draw duration completes", () => {
    expect(isEdgeDrawActive(399)).toBe(true);
    expect(isEdgeDrawActive(400)).toBe(false);
  });
});
