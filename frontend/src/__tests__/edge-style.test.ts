import * as THREE from "three";
import { describe, expect, it } from "vitest";

import {
  createEdgeMaterialForClusters,
  edgeAlphaForLod,
  edgeOpacityForClusters,
  isCrossClusterEdge,
} from "@/lib/edge-style";

describe("edge cluster styling", () => {
  it("uses solid full-opacity material inside a cluster", () => {
    const mat = createEdgeMaterialForClusters("billing", "billing", "#fff");
    expect(mat).toBeInstanceOf(THREE.LineBasicMaterial);
    expect(mat.opacity).toBe(1);
  });

  it("uses dashed low-opacity material across clusters", () => {
    const mat = createEdgeMaterialForClusters("billing", "execution_context", "#fff");
    expect(mat).toBeInstanceOf(THREE.LineDashedMaterial);
    expect(mat.opacity).toBe(0.25);
  });

  it("swaps edge mode when cluster id changes", () => {
    expect(isCrossClusterEdge("billing", "billing")).toBe(false);
    expect(isCrossClusterEdge("billing", "execution_context")).toBe(true);
    expect(edgeOpacityForClusters("billing", "execution_context")).toBeLessThan(
      edgeOpacityForClusters("billing", "billing"),
    );
  });

  it("does not cap edge alpha in sphere mode", () => {
    expect(edgeAlphaForLod(1, "full", false, 0.12)).toBe(1);
    expect(edgeAlphaForLod(0.4, "full", false, 0.12)).toBe(0.4);
  });
});
