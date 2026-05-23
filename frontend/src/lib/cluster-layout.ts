import * as THREE from "three";

import { SUPER_CLUSTER_IDS, type SuperClusterId } from "@/lib/cluster-reframe";

export const CLUSTER_IDS = SUPER_CLUSTER_IDS;

// Phase 5.12: frontend-visible super-clusters. Kept as ClusterId to minimize ripple.
export type ClusterId = SuperClusterId;

// Tab order for the Company Brain SVG overlay clusters (Phase 5.11).
// This is the canonical keyboard traversal order for focusable hit-regions.
export const TAB_ORDER = [
  "people",
  "leadership",
  "meetings",
  "decisions",
  "code",
  "projects",
  "tickets",
  "incidents",
  "systems",
  "vendors",
  "customers",
  "policies",
  "documents",
  "teams",
] as const;

export const HUB_CENTROID_FRAC = { x: 0.474, y: 0.368 } as const;

export const HUB_COLOR = "#53a6ff";

export const CLUSTER_LABELS: Record<ClusterId, string> = {
  company_knowledge: "Company Knowledge",
  execution_context: "Execution Context",
  customers: "Customers",
  // HIDDEN-V2: "Policies"->"Knowledge"; "Receipts" merged into "Audit Trail" for YC company-brain positioning. cluster_id keys unchanged.
  policies: "Knowledge",
  receipts: "Audit Trail",
  agents: "Agents",
  incidents: "Incidents",
  governance: "Audit Trail",
  people_teams: "People & Teams",
  billing: "Billing",
};

export const CLUSTER_COLORS: Record<ClusterId, string> = {
  company_knowledge: "#00E5D8",
  execution_context: "#2B7FFF",
  customers: "#4DD3B8",
  policies: "#4DD3B8",
  receipts: "#4DD3B8",
  agents: "#8B5CF6",
  incidents: "#2B7FFF",
  governance: "#6B4FE0",
  people_teams: "#4DD3B8",
  billing: "#4DD3B8",
};

export const CLUSTER_CENTROID_RADIUS = 90;
export const CLUSTER_GRAVITY_DEFAULT = 0.35;
export const CLUSTER_LABEL_SHOW_DISTANCE = 250;
export const CLUSTER_LABEL_HIDE_DISTANCE = 200;
export const CROSS_CLUSTER_EDGE_OPACITY = 0.25;
export const SAME_CLUSTER_EDGE_OPACITY = 1.0;
export const CROSS_CLUSTER_EDGE_WIDTH = 0.5;
export const SAME_CLUSTER_EDGE_WIDTH = 0.7;

// Phase 5.12.4: per-cluster satellite packing radius (world units)
export const CLUSTER_RADIUS: Record<ClusterId, number> = {
  company_knowledge: 31,
  execution_context: 29,
  customers: 11,
  policies: 11,
  receipts: 11,
  agents: 12,
  incidents: 11,
  governance: 12,
  people_teams: 9,
  billing: 10,
};

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

export const CLUSTER_CENTROIDS: Record<ClusterId, THREE.Vector3> = {
  company_knowledge: new THREE.Vector3(-50, 10, 0),
  execution_context: new THREE.Vector3(52, 18, -5),
  policies: new THREE.Vector3(-78, 58, 10),
  customers: new THREE.Vector3(-158, -3, 5),
  receipts: new THREE.Vector3(-62, -32, 0),
  agents: new THREE.Vector3(62, 62, -10),
  incidents: new THREE.Vector3(92, 14, 0),
  governance: new THREE.Vector3(86, -12, -5),
  people_teams: new THREE.Vector3(0, 43, 15),
  billing: new THREE.Vector3(10, -7, 10),
};

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

export function clusterGravityDampingFactor(distance: number): number {
  if (distance <= 4) return 0.3;
  if (distance >= 12) return 1;
  const t = (distance - 4) / 8;
  return 0.3 + 0.7 * (0.5 - 0.5 * Math.cos(Math.PI * t));
}

/**
 * d3-force-3d compatible force that nudges each classified node toward
 * the centroid of its cluster every tick. Unclassified nodes pass
 * through unchanged. Magnitude scales with the simulation alpha so the
 * pull fades out as the layout settles, matching d3 conventions.
 */
export function clusterGravityForce(
  strength: number = CLUSTER_GRAVITY_DEFAULT,
  centroids: Record<ClusterId, THREE.Vector3> = CLUSTER_CENTROIDS,
): ClusterGravityForce {
  let nodes: ClusterGravityNode[] = [];
  let s = strength;

  const force = ((alpha: number) => {
    if (s === 0) return;
    for (const node of nodes) {
      if (!isClusterId(node.cluster_id)) continue;
      const centroid = centroids[node.cluster_id];
      if (!centroid) continue;
      const x = node.x ?? 0;
      const y = node.y ?? 0;
      const z = node.z ?? 0;
      const dx = centroid.x - x;
      const dy = centroid.y - y;
      const dz = centroid.z - z;
      const distance = Math.sqrt(dx * dx + dy * dy + dz * dz);
      const damped = s * clusterGravityDampingFactor(distance);
      node.vx = (node.vx ?? 0) + dx * damped * alpha;
      node.vy = (node.vy ?? 0) + dy * damped * alpha;
      node.vz = (node.vz ?? 0) + dz * damped * alpha;
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
