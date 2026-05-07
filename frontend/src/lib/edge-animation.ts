import * as THREE from "three";

export const EDGE_DRAW_MS = 400;

export function easeOutCubic(t: number): number {
  const clamped = Math.min(1, Math.max(0, t));
  return 1 - Math.pow(1 - clamped, 3);
}

export function edgeDrawEndpoint(source: THREE.Vector3, target: THREE.Vector3, ageMs: number): THREE.Vector3 {
  return source.clone().lerp(target, easeOutCubic(ageMs / EDGE_DRAW_MS));
}

export function isEdgeDrawActive(ageMs: number): boolean {
  return ageMs < EDGE_DRAW_MS;
}
