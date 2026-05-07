import { describe, expect, it } from "vitest";

import { createHexPrismGeometry, HEX_HEIGHT, HEX_NODE_RADIUS } from "@/lib/hex-geometry";

describe("createHexPrismGeometry", () => {
  it("creates a six-sided prism", () => {
    const geometry = createHexPrismGeometry();
    expect(geometry.parameters.radialSegments).toBe(6);
  });

  it("uses the requested dimensions", () => {
    const geometry = createHexPrismGeometry(HEX_NODE_RADIUS, HEX_HEIGHT);
    expect(geometry.parameters.radiusTop).toBe(HEX_NODE_RADIUS);
    expect(geometry.parameters.radiusBottom).toBe(HEX_NODE_RADIUS);
    expect(geometry.parameters.height).toBe(HEX_HEIGHT);
  });
});
