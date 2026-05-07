import * as THREE from "three";
import { describe, expect, it, vi } from "vitest";

import { IDLE_THRESHOLD_MS, IdleOrbitController, type OrbitLikeControls } from "@/lib/idle-orbit";

function setup() {
  const camera = new THREE.PerspectiveCamera(60, 1, 1, 4000);
  camera.position.set(0, 20, 280);
  const controls: OrbitLikeControls = {
    target: new THREE.Vector3(0, 0, 0),
    update: vi.fn(),
  };
  return { camera, controls, orbit: new IdleOrbitController(camera, controls) };
}

describe("IdleOrbitController", () => {
  it("does not start before the idle threshold", () => {
    const { camera, orbit } = setup();
    const before = camera.position.clone();
    orbit.update(IDLE_THRESHOLD_MS - 1);
    expect(camera.position.distanceTo(before)).toBeLessThan(0.001);
  });

  it("starts after four seconds of no input", () => {
    const { camera, orbit } = setup();
    const before = camera.position.clone();
    orbit.update(IDLE_THRESHOLD_MS + 100);
    expect(camera.position.distanceTo(before)).toBeGreaterThan(0.001);
  });

  it("stops immediately on input", () => {
    const { camera, orbit } = setup();
    orbit.update(IDLE_THRESHOLD_MS + 100);
    orbit.noteUserInput(IDLE_THRESHOLD_MS + 120);
    const before = camera.position.clone();
    orbit.update(IDLE_THRESHOLD_MS + 121);
    expect(camera.position.distanceTo(before)).toBeLessThan(0.001);
  });

  it("preserves camera distance from target", () => {
    const { camera, controls, orbit } = setup();
    const distance = camera.position.distanceTo(controls.target);
    orbit.update(IDLE_THRESHOLD_MS + 100);
    expect(camera.position.distanceTo(controls.target)).toBeCloseTo(distance, 6);
  });

  it("resumes after another idle interval", () => {
    const { camera, orbit } = setup();
    orbit.noteUserInput(5000);
    orbit.update(8999);
    const before = camera.position.clone();
    orbit.update(9100);
    expect(camera.position.distanceTo(before)).toBeGreaterThan(0.001);
  });
});
