import { describe, expect, it } from "vitest";

import { RollingFpsCounter } from "@/lib/fps";

describe("fps", () => {
  it("returns 0 until window filled", () => {
    const c = new RollingFpsCounter(3);
    expect(c.tick(0)).toBe(0);
    expect(c.tick(16)).toBe(0);
    expect(c.tick(32)).toBeGreaterThan(0);
  });
});
