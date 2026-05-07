import * as THREE from "three";

import { CLUSTER_CENTROIDS, CLUSTER_COLORS, CLUSTER_IDS, type ClusterId } from "@/lib/cluster-layout";

export const CLUSTER_AURA_RADIUS = 25;
export const CLUSTER_AURA_PULSE = 1.5;

export function auraRadiusAt(timeMs: number): number {
  return CLUSTER_AURA_RADIUS + CLUSTER_AURA_PULSE * Math.sin(timeMs / 2000);
}

export function createClusterAura(cluster: ClusterId): THREE.Mesh<THREE.SphereGeometry, THREE.MeshBasicMaterial> {
  const geometry = new THREE.SphereGeometry(CLUSTER_AURA_RADIUS, 24, 16);
  const material = new THREE.MeshBasicMaterial({
    color: CLUSTER_COLORS[cluster],
    transparent: true,
    opacity: 0.06,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    side: THREE.BackSide,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.copy(CLUSTER_CENTROIDS[cluster]);
  mesh.renderOrder = -10;
  mesh.userData = { cluster };
  return mesh;
}

export function createClusterAuras(): THREE.Mesh<THREE.SphereGeometry, THREE.MeshBasicMaterial>[] {
  return CLUSTER_IDS.map((cluster) => createClusterAura(cluster));
}

export function updateClusterAuras(
  auras: THREE.Mesh<THREE.SphereGeometry, THREE.MeshBasicMaterial>[],
  timeMs: number,
): void {
  const scale = auraRadiusAt(timeMs) / CLUSTER_AURA_RADIUS;
  for (const aura of auras) aura.scale.setScalar(scale);
}
