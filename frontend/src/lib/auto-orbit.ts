import * as THREE from "three";

const IDLE_THRESHOLD_MS = 5000;
const ORBIT_ANGULAR_VELOCITY = 0.04;

export class AutoOrbitController {
  private lastInteractionMs = 0;

  notifyInteraction(now = performance.now()): void {
    this.lastInteractionMs = now;
  }

  angularVelocity(now: number): number {
    return now - this.lastInteractionMs >= IDLE_THRESHOLD_MS ? ORBIT_ANGULAR_VELOCITY : 0;
  }

  applyToCamera(camera: THREE.PerspectiveCamera, now: number, dtMs: number): void {
    const velocity = this.angularVelocity(now);
    if (velocity === 0) return;

    const angle = velocity * (dtMs / 1000);
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    const { x, z } = camera.position;

    camera.position.x = x * cos - z * sin;
    camera.position.z = x * sin + z * cos;
  }
}
