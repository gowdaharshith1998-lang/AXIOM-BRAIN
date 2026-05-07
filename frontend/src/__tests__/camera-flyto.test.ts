import * as THREE from "three";
import { afterEach, describe, expect, it, vi } from "vitest";

import { easeInOutCubic, flyToEntity, type FlyToControls } from "@/lib/camera-flyto";

function installRaf() {
  let callbacks: FrameRequestCallback[] = [];
  const request = vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
    callbacks.push(cb);
    return callbacks.length;
  });
  const cancel = vi.spyOn(window, "cancelAnimationFrame").mockImplementation((id) => {
    callbacks[id - 1] = () => undefined;
  });
  return {
    request,
    cancel,
    flush: (time: number) => {
      const pending = callbacks;
      callbacks = [];
      for (const cb of pending) cb(time);
    },
  };
}

describe("camera fly-to", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("uses smooth ease-in-out cubic endpoints", () => {
    expect(easeInOutCubic(0)).toBe(0);
    expect(easeInOutCubic(0.5)).toBe(0.5);
    expect(easeInOutCubic(1)).toBe(1);
  });

  it("moves camera to 80 units from target along current view direction", () => {
    const raf = installRaf();
    vi.spyOn(performance, "now").mockReturnValue(0);
    const camera = new THREE.PerspectiveCamera();
    camera.position.set(0, 0, 200);
    const controls: FlyToControls = { target: new THREE.Vector3(0, 0, 0), update: vi.fn() };

    flyToEntity(camera, controls, new THREE.Vector3(10, 20, 30), 1200);
    raf.flush(1200);

    expect(camera.position.toArray()).toEqual([10, 20, 110]);
    expect(controls.target.toArray()).toEqual([10, 20, 30]);
    expect(controls.update).toHaveBeenCalled();
  });

  it("can complete immediately for zero-duration flights", () => {
    installRaf();
    vi.spyOn(performance, "now").mockReturnValue(0);
    const camera = new THREE.PerspectiveCamera();
    camera.position.set(0, 0, 100);
    const controls: FlyToControls = { target: new THREE.Vector3(0, 0, 0) };

    flyToEntity(camera, controls, new THREE.Vector3(5, 0, 0), 0);

    expect(camera.position.toArray()).toEqual([5, 0, 80]);
    expect(controls.target.toArray()).toEqual([5, 0, 0]);
  });

  it("cancels previous flight when a new one starts", () => {
    const raf = installRaf();
    vi.spyOn(performance, "now").mockReturnValue(0);
    const camera = new THREE.PerspectiveCamera();
    camera.position.set(0, 0, 200);
    const controls: FlyToControls = { target: new THREE.Vector3(0, 0, 0) };

    flyToEntity(camera, controls, new THREE.Vector3(0, 0, 0), 1200);
    flyToEntity(camera, controls, new THREE.Vector3(20, 0, 0), 1200);
    raf.flush(1200);

    expect(raf.cancel).toHaveBeenCalled();
    expect(controls.target.toArray()).toEqual([20, 0, 0]);
  });
});
