import * as THREE from "three";
import { describe, expect, it, vi } from "vitest";

import {
  BLOOM_FULL_STRENGTH,
  BLOOM_OVERVIEW_STRENGTH,
  bloomStrengthForDistance,
  createNodeSpriteMaterial,
  nodeLodMode,
  shouldRenderEdge,
  swapMeshGeometry,
} from "@/lib/lod";

describe("overview LOD", () => {
  it("swaps to sprite above distance 280", () => {
    expect(nodeLodMode(280.001)).toBe("sprite");
  });

  it("uses full geometry at distance exactly 280 and below", () => {
    expect(nodeLodMode(280)).toBe("sphere");
    expect(nodeLodMode(220)).toBe("sphere");
  });

  it("renders every third edge above distance 320", () => {
    expect(shouldRenderEdge(0, 321)).toBe(true);
    expect(shouldRenderEdge(1, 321)).toBe(false);
    expect(shouldRenderEdge(2, 321)).toBe(false);
    expect(shouldRenderEdge(3, 321)).toBe(true);
    expect(shouldRenderEdge(1, 280)).toBe(true);
  });

  it("renders all edges at default zoom", () => {
    expect(shouldRenderEdge(1, 224)).toBe(true);
    expect(shouldRenderEdge(2, 224)).toBe(true);
  });

  it("reduces bloom above distance 280", () => {
    expect(BLOOM_FULL_STRENGTH).toBe(0.25);
    expect(bloomStrengthForDistance(281)).toBe(BLOOM_OVERVIEW_STRENGTH);
    expect(bloomStrengthForDistance(280)).toBe(BLOOM_FULL_STRENGTH);
  });

  it("keeps overview bloom below full bloom", () => {
    expect(BLOOM_OVERVIEW_STRENGTH).toBeLessThan(BLOOM_FULL_STRENGTH);
  });

  it("uses normal blending for sprite materials", () => {
    const gradient = { addColorStop: vi.fn() };
    const getContext = vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      createRadialGradient: vi.fn(() => gradient),
      fillRect: vi.fn(),
      fillStyle: "",
    } as unknown as CanvasRenderingContext2D);
    const mat = createNodeSpriteMaterial("#ff0000");
    expect(mat.blending).toBe(THREE.NormalBlending);
    expect(mat.opacity).toBe(0.6);
    mat.dispose();
    getContext.mockRestore();
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
