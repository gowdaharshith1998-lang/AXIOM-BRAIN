import * as THREE from "three";
import { describe, expect, it } from "vitest";

import { AutoOrbitController } from "@/lib/auto-orbit";

describe("auto-orbit", () => {
  it("returns zero angular velocity for recent input", () => {
    const orbit = new AutoOrbitController();
    orbit.notifyInteraction(1000);
    expect(orbit.angularVelocity(5999)).toBe(0);
  });

  it("returns 0.04 rad/s after 5 seconds idle", () => {
    const orbit = new AutoOrbitController();
    orbit.notifyInteraction(1000);
    expect(orbit.angularVelocity(6000)).toBe(0.04);
  });

  it("rotates camera x/z when idle", () => {
    const orbit = new AutoOrbitController();
    orbit.notifyInteraction(0);
    const camera = new THREE.PerspectiveCamera();
    camera.position.set(0, 0, 10);
    orbit.applyToCamera(camera, 6000, 1000);
    expect(camera.position.x).not.toBe(0);
    expect(camera.position.z).not.toBe(10);
  });
});
