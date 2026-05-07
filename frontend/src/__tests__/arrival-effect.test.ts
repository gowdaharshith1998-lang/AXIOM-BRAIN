import * as THREE from "three";
import { describe, expect, it } from "vitest";

import {
  ARRIVAL_EFFECT_MS,
  arrivalColorForCluster,
  arrivalPulseState,
  arrivalSpiralParticles,
} from "@/components/ArrivalEffect";

describe("arrival effect", () => {
  it("spawns with the entity cluster color", () => {
    expect(arrivalColorForCluster("engineering_code")).toBe("#84cc16");
  });

  it("falls back to purple for unknown clusters", () => {
    expect(arrivalColorForCluster(null)).toBe("#a855f7");
  });

  it("expands and fades the pulse over six hundred ms", () => {
    const start = arrivalPulseState(0);
    const end = arrivalPulseState(600);
    expect(start.radius).toBe(2);
    expect(start.opacity).toBe(1);
    expect(end.radius).toBe(12);
    expect(end.opacity).toBe(0);
  });

  it("removes after one thousand ms", () => {
    expect(arrivalPulseState(ARRIVAL_EFFECT_MS + 1).alive).toBe(false);
  });

  it("emits eight spiral particles around the entity position", () => {
    const origin = new THREE.Vector3(1, 2, 3);
    const particles = arrivalSpiralParticles(400, origin);
    expect(particles).toHaveLength(8);
    expect(particles[0].position.distanceTo(origin)).toBeGreaterThan(4);
  });
});
