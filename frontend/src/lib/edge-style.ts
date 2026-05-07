import * as THREE from "three";

import {
  CROSS_CLUSTER_EDGE_OPACITY,
  SAME_CLUSTER_EDGE_OPACITY,
  isClusterId,
} from "@/lib/cluster-layout";

export function isCrossClusterEdge(sourceCluster?: string | null, targetCluster?: string | null): boolean {
  return isClusterId(sourceCluster) && isClusterId(targetCluster) && sourceCluster !== targetCluster;
}

export function edgeOpacityForClusters(sourceCluster?: string | null, targetCluster?: string | null): number {
  return isCrossClusterEdge(sourceCluster, targetCluster) ? CROSS_CLUSTER_EDGE_OPACITY : SAME_CLUSTER_EDGE_OPACITY;
}

export function edgeAlphaForLod(baseAlpha: number, fpsState: string, farLodActive: boolean, farEdgeAlpha: number): number {
  const fpsCap = fpsState === "emergency" ? 0.16 : 1.0;
  const lodCap = farLodActive ? farEdgeAlpha : 1.0;
  return Math.min(baseAlpha, fpsCap, lodCap);
}

export function createEdgeMaterialForClusters(
  sourceCluster: string | null | undefined,
  targetCluster: string | null | undefined,
  color: THREE.ColorRepresentation,
): THREE.LineBasicMaterial | THREE.LineDashedMaterial {
  if (isCrossClusterEdge(sourceCluster, targetCluster)) {
    return new THREE.LineDashedMaterial({
      color,
      dashSize: 0.5,
      gapSize: 0.4,
      opacity: CROSS_CLUSTER_EDGE_OPACITY,
      transparent: true,
    });
  }
  return new THREE.LineBasicMaterial({
    color,
    opacity: SAME_CLUSTER_EDGE_OPACITY,
    transparent: true,
  });
}
