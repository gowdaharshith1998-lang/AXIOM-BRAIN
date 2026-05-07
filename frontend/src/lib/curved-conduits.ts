import * as THREE from "three";

import { CLUSTER_CENTROIDS, CLUSTER_COLORS, type ClusterId } from "@/lib/cluster-layout";
import type { InterHubEdge } from "@/lib/hex-layout";

export type ConduitPath = InterHubEdge & {
  points: THREE.Vector3[];
};

export function buildCurvedConduit(
  source: THREE.Vector3,
  target: THREE.Vector3,
  arcHeight = 0.35,
): THREE.Vector3[] {
  const midpoint = source.clone().lerp(target, 0.5);
  const distance = source.distanceTo(target);
  const control = midpoint.clone();
  control.z += distance * arcHeight;
  const points: THREE.Vector3[] = [];
  const segments = 32;
  for (let i = 0; i <= segments; i++) {
    const t = i / segments;
    const u = 1 - t;
    points.push(
      new THREE.Vector3()
        .addScaledVector(source, u * u)
        .addScaledVector(control, 2 * u * t)
        .addScaledVector(target, t * t),
    );
  }
  return points;
}

export function pointAtPathT(path: THREE.Vector3[], t: number): THREE.Vector3 {
  if (path.length === 0) return new THREE.Vector3();
  if (path.length === 1) return path[0].clone();
  const clamped = THREE.MathUtils.clamp(t, 0, 1);
  const scaled = clamped * (path.length - 1);
  const index = Math.min(path.length - 2, Math.floor(scaled));
  const localT = scaled - index;
  return path[index].clone().lerp(path[index + 1], localT);
}

export function tangentAngleAtPathT(path: THREE.Vector3[], t: number): number {
  const here = pointAtPathT(path, t);
  const there = pointAtPathT(path, Math.min(1, t + 0.01));
  const tangent = there.sub(here);
  return Math.atan2(tangent.y, tangent.x);
}

export function conduitPathsForEdges(edges: InterHubEdge[]): ConduitPath[] {
  return edges.map((edge) => ({
    ...edge,
    points: buildCurvedConduit(CLUSTER_CENTROIDS[edge.sourceCluster], CLUSTER_CENTROIDS[edge.targetCluster]),
  }));
}

export function createConduitLine(edge: ConduitPath): THREE.Line {
  const geometry = new THREE.BufferGeometry().setFromPoints(edge.points);
  const source = new THREE.Color(CLUSTER_COLORS[edge.sourceCluster]);
  const target = new THREE.Color(CLUSTER_COLORS[edge.targetCluster]);
  const colors = new Float32Array(edge.points.length * 3);
  for (let i = 0; i < edge.points.length; i++) {
    const color = source.clone().lerp(target, i / Math.max(1, edge.points.length - 1));
    colors[i * 3] = color.r;
    colors[i * 3 + 1] = color.g;
    colors[i * 3 + 2] = color.b;
  }
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  const material = new THREE.LineBasicMaterial({
    vertexColors: true,
    transparent: true,
    opacity: 0.45,
    depthWrite: false,
  });
  const line = new THREE.Line(geometry, material);
  line.userData = { key: edge.key, sourceCluster: edge.sourceCluster, targetCluster: edge.targetCluster };
  return line;
}
