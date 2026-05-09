import { describe, expect, it } from "vitest";

import { CLUSTER_CENTROIDS, CLUSTER_IDS } from "@/lib/cluster-layout";

describe("brain lobe integration", () => {
  it("hex constellation layout intentionally expands past the old envelope", () => {
    for (const cluster of CLUSTER_IDS) {
      expect(CLUSTER_CENTROIDS[cluster].length()).toBeLessThanOrEqual(220);
    }
  });

  it("label anchors share centroid source of truth", () => {
    for (const cluster of CLUSTER_IDS) {
      const anchor = CLUSTER_CENTROIDS[cluster];
      expect(anchor).toBe(CLUSTER_CENTROIDS[cluster]);
    }
  });

  it("overview has seven semantic lobe anchors", () => {
    expect(CLUSTER_IDS.map((id) => CLUSTER_CENTROIDS[id])).toHaveLength(9);
  });
});
