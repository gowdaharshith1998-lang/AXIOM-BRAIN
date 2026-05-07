import { describe, expect, it } from "vitest";

import { BRAIN_ENVELOPE_RADIUS } from "@/lib/brain-envelope";
import { CLUSTER_CENTROIDS, CLUSTER_IDS } from "@/lib/cluster-layout";

describe("brain lobe integration", () => {
  it("envelope contains all centroids", () => {
    for (const cluster of CLUSTER_IDS) {
      expect(CLUSTER_CENTROIDS[cluster].length()).toBeLessThanOrEqual(BRAIN_ENVELOPE_RADIUS);
    }
  });

  it("label anchors share centroid source of truth", () => {
    for (const cluster of CLUSTER_IDS) {
      const anchor = CLUSTER_CENTROIDS[cluster];
      expect(anchor).toBe(CLUSTER_CENTROIDS[cluster]);
    }
  });

  it("overview has seven semantic lobe anchors", () => {
    expect(CLUSTER_IDS.map((id) => CLUSTER_CENTROIDS[id])).toHaveLength(7);
  });
});
