import { describe, expect, it } from "vitest";

import { resolveLabelCollisions } from "@/lib/cluster-label-collision";

describe("cluster label collision", () => {
  it("resolves overlapping labels within four iterations", () => {
    const labels = resolveLabelCollisions([
      { id: "a", x: 0, y: 0, width: 100, height: 20 },
      { id: "b", x: 5, y: 0, width: 100, height: 20 },
    ]);
    expect(Math.abs(labels[0].x - labels[1].x)).toBeGreaterThan(5);
  });

  it("caps offset at twelve px per frame per pass", () => {
    const labels = resolveLabelCollisions(
      [
        { id: "a", x: 0, y: 0, width: 100, height: 20 },
        { id: "b", x: 1, y: 0, width: 100, height: 20 },
      ],
      1,
      12,
    );
    expect(Math.abs(labels[0].dx ?? 0)).toBeLessThanOrEqual(12);
  });

  it("does not move non-overlapping labels", () => {
    const labels = resolveLabelCollisions([
      { id: "a", x: 0, y: 0, width: 10, height: 10 },
      { id: "b", x: 40, y: 0, width: 10, height: 10 },
    ]);
    expect(labels[0].dx).toBe(0);
    expect(labels[1].dx).toBe(0);
  });
});
