import { describe, expect, it, vi } from "vitest";

import { FPS_NODE_BUDGETS, FpsGuard } from "@/lib/fps-guard";

describe("fps-guard", () => {
  it("uses full multiplier at or above 55 fps", () => {
    const guard = new FpsGuard(3);
    expect(guard.sample(55, 0)).toBe("full");
    expect(guard.particleMultiplier()).toBe(1);
  });

  it("uses half multiplier from 40 to 54 fps", () => {
    const guard = new FpsGuard(3);
    expect(guard.sample(54, 0)).toBe("half");
    expect(guard.particleMultiplier()).toBe(0.5);
  });

  it("enters emergency immediately below 40 fps", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const guard = new FpsGuard(3);
    expect(guard.sample(39, 0)).toBe("emergency");
    expect(guard.particleMultiplier()).toBe(0);
    expect(warn).toHaveBeenCalledTimes(1);
    warn.mockRestore();
  });

  it("starts at the full sphere node budget", () => {
    const guard = new FpsGuard(3);
    expect(guard.nodeBudget()).toBe(FPS_NODE_BUDGETS[0]);
  });

  it("reduces node budget after three sustained seconds below 45 fps", () => {
    const guard = new FpsGuard(3);
    const callback = vi.fn();
    guard.onBudgetChange(callback);
    guard.sample(44, 0);
    guard.sample(44, 2999);
    expect(callback).not.toHaveBeenCalled();
    guard.sample(44, 3001);
    expect(callback).toHaveBeenCalledWith(56);
    expect(guard.nodeBudget()).toBe(56);
  });
});
