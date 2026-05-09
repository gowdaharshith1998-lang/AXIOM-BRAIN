import * as THREE from "three";

export const HEX_HUB_RADIUS = 3.6;
export const HEX_NODE_RADIUS = 1.6;
export const HEX_HEIGHT = 0.4;

export function createHexPrismGeometry(
  radius: number = 1,
  height: number = 0.4,
): THREE.CylinderGeometry {
  const geo = new THREE.CylinderGeometry(radius, radius, height, 6, 1, false);
  geo.rotateX(Math.PI / 2);
  return geo;
}
