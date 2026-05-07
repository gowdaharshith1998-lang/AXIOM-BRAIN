import { describe, expect, it } from "vitest";

import { computeEdgeOpacity } from "@/lib/particles/edge-shimmer";

describe("edge shimmer", () => {
  it("stays within the calmer opacity band", () => {
    for (let t = 0; t <= 10_000; t += 125) {
      const opacity = computeEdgeOpacity(t, 0.37);
      expect(opacity).toBeGreaterThanOrEqual(0.2);
      expect(opacity).toBeLessThanOrEqual(0.32);
    }
  });
});
