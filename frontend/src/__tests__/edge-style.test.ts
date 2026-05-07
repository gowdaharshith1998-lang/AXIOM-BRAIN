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
    const mat = createEdgeMaterialForClusters("billing_payments", "billing_payments", "#fff");
    expect(mat).toBeInstanceOf(THREE.LineBasicMaterial);
    expect(mat.opacity).toBe(1);
  });

  it("uses dashed low-opacity material across clusters", () => {
    const mat = createEdgeMaterialForClusters("billing_payments", "incidents_ops", "#fff");
    expect(mat).toBeInstanceOf(THREE.LineDashedMaterial);
    expect(mat.opacity).toBe(0.4);
  });

  it("swaps edge mode when cluster id changes", () => {
    expect(isCrossClusterEdge("billing_payments", "billing_payments")).toBe(false);
    expect(isCrossClusterEdge("billing_payments", "incidents_ops")).toBe(true);
    expect(edgeOpacityForClusters("billing_payments", "incidents_ops")).toBeLessThan(
      edgeOpacityForClusters("billing_payments", "billing_payments"),
    );
  });

  it("does not cap edge alpha in sphere mode", () => {
    expect(edgeAlphaForLod(1, "full", false, 0.12)).toBe(1);
    expect(edgeAlphaForLod(0.4, "full", false, 0.12)).toBe(0.4);
  });
});
