// Phase 5.7.C — Cluster lobe layout.
//
// Lays out the seven canonical semantic clusters as Fibonacci-sphere
// centroids in 3D, then exposes a d3-force-3d compatible gravity force
// that pulls every classified node toward its cluster centroid. Together
// with the existing charge / link / center forces, this produces seven
// visually distinct lobes around the brain at overview zoom, while
// cross-cluster edges remain present (just visually subtler — see the
// dashed-edge styling in Brain.tsx).

import * as THREE from "three";

export const CLUSTER_IDS = [
  "billing_payments",
  "incidents_ops",
  "engineering_code",
  "people_teams",
  "decisions_policy",
  "customer_support",
  "growth_product",
] as const;

export type ClusterId = (typeof CLUSTER_IDS)[number];

export const CLUSTER_LABELS: Record<ClusterId, string> = {
  billing_payments: "Billing & Payments",
  incidents_ops: "Incidents & Ops",
  engineering_code: "Engineering & Code",
  people_teams: "People & Teams",
  decisions_policy: "Decisions & Policy",
  customer_support: "Customer Support",
  growth_product: "Growth & Product",
};

export const CLUSTER_COLORS: Record<ClusterId, string> = {
  billing_payments: "#FF79C6",
  incidents_ops: "#FF5555",
  engineering_code: "#7CFC9F",
  people_teams: "#F1FA8C",
  decisions_policy: "#BD93F9",
  customer_support: "#8BE9FD",
  growth_product: "#50FA7B",
};

export const CLUSTER_CENTROID_RADIUS = 100;
export const CLUSTER_GRAVITY_DEFAULT = 0.05;
export const CLUSTER_LABEL_SHOW_DISTANCE = 250;
export const CLUSTER_LABEL_HIDE_DISTANCE = 200;
export const CROSS_CLUSTER_EDGE_OPACITY = 0.3;
export const SAME_CLUSTER_EDGE_OPACITY = 0.4;
export const CROSS_CLUSTER_EDGE_WIDTH = 0.5;
export const SAME_CLUSTER_EDGE_WIDTH = 0.7;

export function isClusterId(value: unknown): value is ClusterId {
  return typeof value === "string" && (CLUSTER_IDS as readonly string[]).includes(value);
}

/**
 * Generate `n` points evenly distributed on a sphere of the given radius
 * using the Fibonacci-spiral / golden-angle method.
 *
 * Reference: González, "Measurement of Areas on a Sphere Using Fibonacci
 * and Latitude–Longitude Lattices" (Math. Geosci., 2010).
 */
export function fibonacciSpherePoints(n: number, radius: number): THREE.Vector3[] {
  const points: THREE.Vector3[] = [];
  if (n <= 0) return points;
  if (n === 1) {
    points.push(new THREE.Vector3(0, 0, 0));
    return points;
  }
  const phi = Math.PI * (Math.sqrt(5) - 1); // golden angle
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2;
    const radiusAtY = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = phi * i;
    const x = Math.cos(theta) * radiusAtY;
    const z = Math.sin(theta) * radiusAtY;
    points.push(new THREE.Vector3(x * radius, y * radius, z * radius));
  }
  return points;
}

export const CLUSTER_CENTROIDS: Record<ClusterId, THREE.Vector3> = (() => {
  const points = fibonacciSpherePoints(CLUSTER_IDS.length, CLUSTER_CENTROID_RADIUS);
  const out: Partial<Record<ClusterId, THREE.Vector3>> = {};
  CLUSTER_IDS.forEach((id, i) => {
    out[id] = points[i];
  });
  return out as Record<ClusterId, THREE.Vector3>;
})();

export type ClusterGravityNode = {
  cluster_id?: string | null;
  x?: number;
  y?: number;
  z?: number;
  vx?: number;
  vy?: number;
  vz?: number;
};

export type ClusterGravityForce = {
  (alpha: number): void;
  initialize: (nodes: ClusterGravityNode[]) => void;
  strength: (value?: number) => number | ClusterGravityForce;
};

/**
 * d3-force-3d compatible force that nudges each classified node toward
 * the centroid of its cluster every tick. Unclassified nodes pass
 * through unchanged. Magnitude scales with the simulation alpha so the
 * pull fades out as the layout settles, matching d3 conventions.
 */
export function clusterGravityForce(
  strength: number = CLUSTER_GRAVITY_DEFAULT,
): ClusterGravityForce {
  let nodes: ClusterGravityNode[] = [];
  let s = strength;

  const force = ((alpha: number) => {
    if (s === 0) return;
    for (const node of nodes) {
      if (!isClusterId(node.cluster_id)) continue;
      const centroid = CLUSTER_CENTROIDS[node.cluster_id];
      if (!centroid) continue;
      const x = node.x ?? 0;
      const y = node.y ?? 0;
      const z = node.z ?? 0;
      node.vx = (node.vx ?? 0) + (centroid.x - x) * s * alpha;
      node.vy = (node.vy ?? 0) + (centroid.y - y) * s * alpha;
      node.vz = (node.vz ?? 0) + (centroid.z - z) * s * alpha;
    }
  }) as ClusterGravityForce;

  force.initialize = (next: ClusterGravityNode[]) => {
    nodes = next;
  };

  force.strength = ((value?: number) => {
    if (value === undefined) return s;
    s = value;
    return force;
  }) as ClusterGravityForce["strength"];

  return force;
}
