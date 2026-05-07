import { describe, expect, it } from "vitest";

import { createSphereNodeGeometry, SPHERE_NODE_RADIUS, SPHERE_SEGMENTS } from "@/lib/sphere-geometry";

describe("createSphereNodeGeometry", () => {
  it("creates an eight segment sphere for spoke nodes", () => {
    const geometry = createSphereNodeGeometry();
    expect(geometry.parameters.widthSegments).toBe(SPHERE_SEGMENTS);
    expect(geometry.parameters.heightSegments).toBe(SPHERE_SEGMENTS);
  });

  it("uses the OMNIX spoke node radius", () => {
    const geometry = createSphereNodeGeometry();
    expect(geometry.parameters.radius).toBe(SPHERE_NODE_RADIUS);
  });
});
