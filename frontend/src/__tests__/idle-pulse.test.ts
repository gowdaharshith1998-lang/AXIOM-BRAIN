import { describe, expect, it } from "vitest";

import { breath, phaseOffsetFromId } from "@/lib/idle-pulse";

describe("idle-pulse", () => {
  it("is deterministic for the same time and phase", () => {
    expect(breath(1234, 0.5)).toBe(breath(1234, 0.5));
  });

  it("stays inside the requested breath range", () => {
    for (let t = 0; t <= 10000; t += 125) {
      expect(breath(t)).toBeGreaterThanOrEqual(0.929);
      expect(breath(t)).toBeLessThanOrEqual(1.071);
    }
  });

  it("produces stable phase offsets in [0, 2pi)", () => {
    const phase = phaseOffsetFromId("entity-1");
    expect(phase).toBe(phaseOffsetFromId("entity-1"));
    expect(phase).toBeGreaterThanOrEqual(0);
    expect(phase).toBeLessThan(2 * Math.PI);
  });
});
