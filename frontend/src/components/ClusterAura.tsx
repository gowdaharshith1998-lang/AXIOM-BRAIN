import * as THREE from "three";

import { CLUSTER_CENTROIDS, CLUSTER_COLORS, CLUSTER_IDS, type ClusterId } from "@/lib/cluster-layout";

export const CLUSTER_AURA_RADIUS = 28;
export const CLUSTER_AURA_BASE_OPACITY = 0.06;
export const CLUSTER_AURA_SCALE_AMPLITUDE = 0.1;
export const CLUSTER_AURA_OPACITY_AMPLITUDE = 0.3;

export function clusterAuraPhase(index: number): number {
  return index * 0.9;
}

export function clusterAuraPeriod(index: number): number {
  return 5000 + index * 500;
}

export function auraWaveAt(index: number, timeMs: number): number {
  return Math.sin(2 * Math.PI * (timeMs / clusterAuraPeriod(index)) + clusterAuraPhase(index));
}

export function auraScaleAt(index: number, timeMs: number): number {
  return 1 + CLUSTER_AURA_SCALE_AMPLITUDE * auraWaveAt(index, timeMs);
}

export function auraOpacityAt(index: number, timeMs: number): number {
  return CLUSTER_AURA_BASE_OPACITY * (1 + CLUSTER_AURA_OPACITY_AMPLITUDE * auraWaveAt(index, timeMs));
}

export function auraRadiusAt(timeMs: number): number {
  return CLUSTER_AURA_RADIUS * auraScaleAt(0, timeMs);
}

export function createClusterAura(cluster: ClusterId): THREE.Mesh<THREE.SphereGeometry, THREE.MeshBasicMaterial> {
  const geometry = new THREE.SphereGeometry(CLUSTER_AURA_RADIUS, 32, 24);
  const material = new THREE.MeshBasicMaterial({
    color: CLUSTER_COLORS[cluster],
    transparent: true,
    opacity: CLUSTER_AURA_BASE_OPACITY,
    blending: THREE.NormalBlending,
    depthWrite: false,
    side: THREE.BackSide,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.copy(CLUSTER_CENTROIDS[cluster]);
  mesh.renderOrder = -5;
  mesh.userData = { cluster };
  return mesh;
}

export function createClusterAuras(): THREE.Mesh<THREE.SphereGeometry, THREE.MeshBasicMaterial>[] {
  return CLUSTER_IDS.map((cluster) => createClusterAura(cluster));
}

export function setAurasVisible(
  auras: THREE.Mesh<THREE.SphereGeometry, THREE.MeshBasicMaterial>[],
  visible: boolean,
): void {
  for (const aura of auras) aura.visible = visible;
}

export function updateClusterAuras(
  auras: THREE.Mesh<THREE.SphereGeometry, THREE.MeshBasicMaterial>[],
  timeMs: number,
): void {
  for (const [index, aura] of auras.entries()) {
    aura.scale.setScalar(auraScaleAt(index, timeMs));
    aura.material.opacity = auraOpacityAt(index, timeMs);
  }
}
