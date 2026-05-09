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
  bendSign = 1,
): THREE.Vector3[] {
  const midpoint = source.clone().lerp(target, 0.5);
  const distance = source.distanceTo(target);
  const direction = target.clone().sub(source).normalize();
  const perpendicular = new THREE.Vector3(-direction.y, direction.x, 0.35 * bendSign).normalize();
  const control = midpoint.clone().addScaledVector(perpendicular, distance * arcHeight * bendSign);
  const points: THREE.Vector3[] = [];
  const segments = 56;
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

export function conduitPathsForEdges(
  edges: InterHubEdge[],
  centroids: Record<ClusterId, THREE.Vector3> = CLUSTER_CENTROIDS,
): ConduitPath[] {
  return edges.map((edge, index) => ({
    ...edge,
    points: buildCurvedConduit(
      centroids[edge.sourceCluster],
      centroids[edge.targetCluster],
      0.3,
      index % 2 === 0 ? 1 : -1,
    ),
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
    opacity: 0.045,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const line = new THREE.Line(geometry, material);
  line.userData = { key: edge.key, sourceCluster: edge.sourceCluster, targetCluster: edge.targetCluster };
  return line;
}
