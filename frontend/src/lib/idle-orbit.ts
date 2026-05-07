import * as THREE from "three";

export const IDLE_THRESHOLD_MS = 4000;
export const IDLE_ORBIT_DEGREES_PER_FRAME = 0.05;

export type OrbitLikeControls = {
  target: THREE.Vector3;
  update: () => void;
};

export class IdleOrbitController {
  enabled = true;
  private lastInputAt = 0;
  private lastUpdateAt: number | null = null;

  constructor(
    private readonly camera: THREE.PerspectiveCamera,
    private readonly controls: OrbitLikeControls,
  ) {}

  noteUserInput(nowMs = performance.now()): void {
    this.lastInputAt = nowMs;
    this.lastUpdateAt = nowMs;
  }

  update(nowMs: number): void {
    if (!this.enabled) return;
    const previous = this.lastUpdateAt ?? nowMs - 16.67;
    this.lastUpdateAt = nowMs;
    if (nowMs - this.lastInputAt < IDLE_THRESHOLD_MS) return;

    const dtScale = Math.max(0, nowMs - previous) / 16.67;
    const angle = THREE.MathUtils.degToRad(IDLE_ORBIT_DEGREES_PER_FRAME * dtScale);
    const offset = this.camera.position.clone().sub(this.controls.target);
    const distance = offset.length();
    offset.applyAxisAngle(new THREE.Vector3(0, 1, 0), angle).setLength(distance);
    this.camera.position.copy(this.controls.target).add(offset);
    this.controls.update();
  }
}
