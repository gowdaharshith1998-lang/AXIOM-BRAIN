import { describe, expect, it } from "vitest";

import {
  hashStringToFloat,
  hubEmissiveIntensityAt,
  shimmerEmissiveMultiplier,
  shimmerScale,
} from "@/lib/spoke-shimmer";

describe("spoke shimmer", () => {
  it("keeps shimmer scale inside a subtle band", () => {
    for (let t = 0; t <= 10_000; t += 500) {
      expect(shimmerScale(0.42, t)).toBeGreaterThanOrEqual(0.88);
      expect(shimmerScale(0.42, t)).toBeLessThanOrEqual(1.12);
    }
  });

  it("uses distinct curves for distinct seeds", () => {
    expect(shimmerScale(0.1, 1234)).not.toBe(shimmerScale(0.9, 1234));
  });

  it("is deterministic for the same seed and time", () => {
    expect(shimmerScale(0.35, 4567)).toBe(shimmerScale(0.35, 4567));
    expect(hashStringToFloat("entity-1")).toBe(hashStringToFloat("entity-1"));
  });

  it("keeps emissive multiplier in a controlled band", () => {
    expect(shimmerEmissiveMultiplier(0.5, 2000)).toBeGreaterThanOrEqual(0.82);
    expect(shimmerEmissiveMultiplier(0.5, 2000)).toBeLessThanOrEqual(1.18);
  });

  it("modulates hub emissive intensity over time", () => {
    expect(Math.abs(hubEmissiveIntensityAt(1.4, 2, 0) - hubEmissiveIntensityAt(1.4, 2, 1500))).toBeGreaterThan(0.05);
  });
});
