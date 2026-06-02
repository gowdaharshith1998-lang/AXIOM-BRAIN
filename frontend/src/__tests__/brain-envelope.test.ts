import { describe, expect, it } from "vitest";

import { envelopePosition } from "@/lib/brain-envelope";

describe("brain-envelope", () => {
  it("is deterministic per id", () => {
    expect(envelopePosition("a")).toEqual(envelopePosition("a"));
    expect(envelopePosition("b")).toEqual(envelopePosition("b"));
  });

  it("different ids produce different positions (probabilistic)", () => {
    expect(envelopePosition("a")).not.toEqual(envelopePosition("a-2"));
  });

  it("positions are bounded roughly within envelope extents", () => {
    const [x, y, z] = envelopePosition("ent_test");
    expect(Math.abs(x)).toBeLessThanOrEqual(100);
    expect(Math.abs(y)).toBeLessThanOrEqual(70);
    expect(Math.abs(z)).toBeLessThanOrEqual(80);
  });
});
