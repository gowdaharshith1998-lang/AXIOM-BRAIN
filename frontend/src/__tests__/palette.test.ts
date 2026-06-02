import { describe, expect, it } from "vitest";

import { FALLBACK_COLOR, PALETTE, colorForType } from "@/lib/palette";

describe("palette", () => {
  it("has exactly 7 entries with distinct hex values", () => {
    const entries = Object.entries(PALETTE);
    expect(entries).toHaveLength(7);
    const values = entries.map(([, v]) => v);
    expect(new Set(values).size).toBe(7);
    for (const v of values) {
      expect(v).toMatch(/^#[0-9A-Fa-f]{6}$/);
    }
  });

  it("fallback is distinct", () => {
    expect(FALLBACK_COLOR).toMatch(/^#[0-9A-Fa-f]{6}$/);
    expect(Object.values(PALETTE)).not.toContain(FALLBACK_COLOR);
  });

  it("colorForType returns fallback for unknown type", () => {
    expect(colorForType("unknown_type")).toBe(FALLBACK_COLOR);
  });
});
