import * as THREE from "three";

export const SPHERE_NODE_RADIUS = 0.55;
export const SPHERE_SEGMENTS = 8;

export function createSphereNodeGeometry(): THREE.SphereGeometry {
  return new THREE.SphereGeometry(SPHERE_NODE_RADIUS, SPHERE_SEGMENTS, SPHERE_SEGMENTS);
}
