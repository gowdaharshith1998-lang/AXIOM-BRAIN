import { describe, expect, it, vi } from "vitest";

import { FpsGuard } from "@/lib/fps-guard";

describe("fps-guard", () => {
  it("uses full multiplier at or above 58 fps", () => {
    const guard = new FpsGuard(3);
    expect(guard.sample(60, 0)).toBe("full");
    expect(guard.particleMultiplier()).toBe(1);
  });

  it("uses half multiplier from 50 to 57 fps", () => {
    const guard = new FpsGuard(3);
    expect(guard.sample(55, 0)).toBe("half");
    expect(guard.particleMultiplier()).toBe(0.5);
  });

  it("enters emergency after 5 seconds below 50 fps", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const guard = new FpsGuard(3);
    expect(guard.sample(45, 0)).toBe("half");
    expect(guard.sample(45, 4999)).toBe("half");
    expect(guard.sample(45, 5000)).toBe("emergency");
    expect(guard.particleMultiplier()).toBe(0.25);
    expect(warn).toHaveBeenCalledTimes(1);
    warn.mockRestore();
  });
});
