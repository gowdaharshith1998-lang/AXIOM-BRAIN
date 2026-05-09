import * as THREE from "three";

export const HEX_HUB_RADIUS = 5.2;
export const HEX_NODE_RADIUS = 2.15;
export const HEX_HEIGHT = 0.42;

export function createHexPrismGeometry(
  radius: number = 1,
  height: number = 0.4,
): THREE.CylinderGeometry {
  const geo = new THREE.CylinderGeometry(radius, radius, height, 6, 1, false);
  geo.rotateX(Math.PI / 2);
  return geo;
}
