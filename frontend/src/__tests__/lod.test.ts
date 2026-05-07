import * as THREE from "three";
import { describe, expect, it, vi } from "vitest";

import {
  BLOOM_FULL_STRENGTH,
  BLOOM_OVERVIEW_STRENGTH,
  bloomStrengthForDistance,
  nodeLodMode,
  shouldRenderEdge,
  swapMeshGeometry,
} from "@/lib/lod";

describe("overview LOD", () => {
  it("swaps to sprite above distance 180", () => {
    expect(nodeLodMode(180.001)).toBe("sprite");
  });

  it("uses full geometry at distance exactly 180 and below", () => {
    expect(nodeLodMode(180)).toBe("sphere");
    expect(nodeLodMode(179.9)).toBe("sphere");
  });

  it("renders every third edge above distance 180", () => {
    expect(shouldRenderEdge(0, 181)).toBe(true);
    expect(shouldRenderEdge(1, 181)).toBe(false);
    expect(shouldRenderEdge(2, 181)).toBe(false);
    expect(shouldRenderEdge(3, 181)).toBe(true);
  });

  it("renders all edges at default zoom", () => {
    expect(shouldRenderEdge(1, 180)).toBe(true);
    expect(shouldRenderEdge(2, 120)).toBe(true);
  });

  it("reduces bloom above distance 220", () => {
    expect(bloomStrengthForDistance(221)).toBe(BLOOM_OVERVIEW_STRENGTH);
    expect(bloomStrengthForDistance(220)).toBe(BLOOM_FULL_STRENGTH);
  });

  it("disposes old geometry on swap", () => {
    const oldGeom = new THREE.SphereGeometry(1);
    const nextGeom = new THREE.BoxGeometry(1);
    const mesh = new THREE.Mesh(oldGeom, new THREE.MeshBasicMaterial());
    const dispose = vi.spyOn(oldGeom, "dispose");
    swapMeshGeometry(mesh, nextGeom);
    expect(dispose).toHaveBeenCalledOnce();
    expect(mesh.geometry).toBe(nextGeom);
  });
});
