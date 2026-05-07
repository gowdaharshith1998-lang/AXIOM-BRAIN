import * as THREE from "three";

export type FlyToControls = {
  target: THREE.Vector3;
  update?: () => void;
};

type ActiveFlight = {
  cancelled: boolean;
  rafId: number | null;
};

let activeFlight: ActiveFlight | null = null;

export function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

export function flyToEntity(
  camera: THREE.PerspectiveCamera,
  controls: FlyToControls,
  targetPos: THREE.Vector3,
  durationMs = 1200,
): () => void {
  if (activeFlight) {
    activeFlight.cancelled = true;
    if (activeFlight.rafId !== null) window.cancelAnimationFrame(activeFlight.rafId);
  }

  const flight: ActiveFlight = { cancelled: false, rafId: null };
  activeFlight = flight;

  const fromPosition = camera.position.clone();
  const fromTarget = controls.target.clone();
  const viewDirection = camera.position.clone().sub(controls.target);
  if (viewDirection.lengthSq() < 0.001) viewDirection.set(0, 0.25, 1);
  viewDirection.normalize();

  const toTarget = targetPos.clone();
  const toPosition = targetPos.clone().add(viewDirection.multiplyScalar(80));
  const startedAt = performance.now();
  const duration = Math.max(durationMs, 0);

  const apply = (progress: number) => {
    const eased = easeInOutCubic(progress);
    camera.position.lerpVectors(fromPosition, toPosition, eased);
    controls.target.lerpVectors(fromTarget, toTarget, eased);
    controls.update?.();
  };

  if (duration === 0) {
    apply(1);
    activeFlight = activeFlight === flight ? null : activeFlight;
    return () => undefined;
  }

  const tick = (now: number) => {
    if (flight.cancelled) return;
    const progress = Math.min(1, (now - startedAt) / duration);
    apply(progress);
    if (progress < 1) {
      flight.rafId = window.requestAnimationFrame(tick);
      return;
    }
    activeFlight = activeFlight === flight ? null : activeFlight;
  };

  flight.rafId = window.requestAnimationFrame(tick);

  return () => {
    flight.cancelled = true;
    if (flight.rafId !== null) window.cancelAnimationFrame(flight.rafId);
    if (activeFlight === flight) activeFlight = null;
  };
}
