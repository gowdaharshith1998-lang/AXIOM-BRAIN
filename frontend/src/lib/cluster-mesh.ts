import * as THREE from "three";

import { CLUSTER_COLORS, type ClusterId } from "@/lib/cluster-layout";
import type { VisibleEntitySlot } from "@/lib/hex-layout";

export type MeshEdge = {
  sourceId: string;
  targetId: string;
  cluster: ClusterId;
};

export function computeIntraClusterEdges(
  slots: VisibleEntitySlot[],
  cluster: ClusterId,
  maxEdgesPerNode = 4,
): MeshEdge[] {
  const clusterSlots = slots.filter((slot) => slot.clusterId === cluster);
  const edges: MeshEdge[] = [];
  const seen = new Set<string>();

  for (const slot of clusterSlots) {
    const nearest = clusterSlots
      .filter((other) => other.entity.id !== slot.entity.id)
      .map((other) => ({
        slot: other,
        dist: slot.position.distanceTo(other.position),
      }))
      .sort((a, b) => a.dist - b.dist)
      .slice(0, maxEdgesPerNode);

    for (const { slot: other } of nearest) {
      const key = [slot.entity.id, other.entity.id].sort().join("|");
      if (seen.has(key)) continue;
      seen.add(key);
      edges.push({
        sourceId: slot.entity.id,
        targetId: other.entity.id,
        cluster,
      });
    }
  }

  return edges;
}

export function buildIntraClusterMeshGroup(slots: VisibleEntitySlot[]): THREE.Group {
  const group = new THREE.Group();
  group.renderOrder = -2;
  const byId = new Map(slots.map((slot) => [slot.entity.id, slot.position]));
  const clusters = new Set(slots.map((slot) => slot.clusterId));

  for (const cluster of clusters) {
    const meshEdges = computeIntraClusterEdges(slots, cluster);
    const positions = new Float32Array(meshEdges.length * 2 * 3);
    let index = 0;
    for (const edge of meshEdges) {
      const source = byId.get(edge.sourceId);
      const target = byId.get(edge.targetId);
      if (!source || !target) continue;
      positions[index++] = source.x;
      positions[index++] = source.y;
      positions[index++] = source.z;
      positions[index++] = target.x;
      positions[index++] = target.y;
      positions[index++] = target.z;
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const material = new THREE.LineBasicMaterial({
      color: CLUSTER_COLORS[cluster],
      transparent: true,
      opacity: 0.18,
      blending: THREE.NormalBlending,
      depthWrite: false,
    });
    const lines = new THREE.LineSegments(geometry, material);
    lines.renderOrder = -2;
    group.add(lines);
  }

  return group;
}
