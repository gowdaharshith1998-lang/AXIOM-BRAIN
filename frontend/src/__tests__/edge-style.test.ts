import * as THREE from "three";
import { describe, expect, it } from "vitest";

import { createEdgeMaterialForClusters, edgeOpacityForClusters, isCrossClusterEdge } from "@/lib/edge-style";

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
});
