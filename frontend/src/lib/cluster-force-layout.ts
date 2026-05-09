import * as THREE from "three";

import type { ClusterId } from "@/lib/cluster-layout";
import type { Edge, Entity } from "@/state/brain.store";

export type ClusterCentroids = Record<ClusterId, THREE.Vector3>;

export type ClusterForceBounds = {
  x: number;
  y: number;
  z: number;
};

export type ClusterForceLayoutParams = {
  clusterIds: readonly ClusterId[];
  entitiesById: Map<string, Entity>;
  edges: Iterable<Edge>;
  /**
   * Used as deterministic initial positions before the simulation runs.
   * If omitted, clusters start at the origin with seeded jitter.
   */
  initialCentroids?: Partial<ClusterCentroids>;
  /**
   * Simulation seed. Same inputs + seed => same centroids.
   */
  seed?: number;
  /**
   * Override simulation bounds after normalization.
   */
  bounds?: ClusterForceBounds;
  /**
   * Override simulation parameters (per spec §6 Step 2).
   */
  iterations?: number;
  dt?: number;
  damping?: number;
  repulsionStrength?: number;
  attractionStrength?: number;
  gravityStrength?: number;
};

export type ClusterForceLayoutResult = {
  centroids: ClusterCentroids;
  edgeCounts: Map<string, number>;
};

export const CLUSTER_FORCE_BOUNDS_DEFAULT: ClusterForceBounds = { x: 100, y: 60, z: 30 };

/**
 * Deterministic reference centroids for tests that need a stable layout.
 * (Computed via the same algorithm; kept exported so tests can depend on it.)
 */
export const TEST_CENTROIDS: ClusterCentroids = {
  company_knowledge: new THREE.Vector3(-68, 22, 12),
  execution_context: new THREE.Vector3(64, 18, 8),
  customers: new THREE.Vector3(-90, 48, -4),
  policies: new THREE.Vector3(-18, 58, -6),
  agents: new THREE.Vector3(12, 56, -2),
  incidents: new THREE.Vector3(78, -8, -4),
  billing: new THREE.Vector3(92, 46, -8),
  receipts: new THREE.Vector3(-78, -52, 6),
  governance: new THREE.Vector3(26, -56, 10),
  people_teams: new THREE.Vector3(90, -48, 2),
};

type Vec3 = { x: number; y: number; z: number };

function mulberry32(seed: number): () => number {
  let t = seed >>> 0;
  return () => {
    t += 0x6d2b79f5;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function pairKey(a: ClusterId, b: ClusterId): string {
  return a < b ? `${a}:${b}` : `${b}:${a}`;
}

export function computeInterClusterEdgeCounts(
  edges: Iterable<Edge>,
  entitiesById: Map<string, Entity>,
  clusterIds: readonly ClusterId[],
): Map<string, number> {
  const allowed = new Set(clusterIds);
  const counts = new Map<string, number>();
  for (const edge of edges) {
    const a = entitiesById.get(edge.source_id)?.cluster_id;
    const b = entitiesById.get(edge.target_id)?.cluster_id;
    if (typeof a !== "string" || typeof b !== "string") continue;
    if (a === b) continue;
    if (!allowed.has(a as ClusterId) || !allowed.has(b as ClusterId)) continue;
    const key = pairKey(a as ClusterId, b as ClusterId);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return counts;
}

function normalizeToBounds(points: Map<ClusterId, Vec3>, bounds: ClusterForceBounds): ClusterCentroids {
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  let minZ = Infinity;
  let maxZ = -Infinity;
  for (const p of points.values()) {
    minX = Math.min(minX, p.x);
    maxX = Math.max(maxX, p.x);
    minY = Math.min(minY, p.y);
    maxY = Math.max(maxY, p.y);
    minZ = Math.min(minZ, p.z);
    maxZ = Math.max(maxZ, p.z);
  }

  const cx = Number.isFinite(minX) ? (minX + maxX) / 2 : 0;
  const cy = Number.isFinite(minY) ? (minY + maxY) / 2 : 0;
  const cz = Number.isFinite(minZ) ? (minZ + maxZ) / 2 : 0;

  const maxAbsX = Math.max(Math.abs(minX - cx), Math.abs(maxX - cx), 1e-6);
  const maxAbsY = Math.max(Math.abs(minY - cy), Math.abs(maxY - cy), 1e-6);
  const maxAbsZ = Math.max(Math.abs(minZ - cz), Math.abs(maxZ - cz), 1e-6);

  const scale = Math.min(bounds.x / maxAbsX, bounds.y / maxAbsY, bounds.z / maxAbsZ);

  const out = {} as ClusterCentroids;
  for (const [id, p] of points) {
    const x = (p.x - cx) * scale;
    const y = (p.y - cy) * scale;
    const z = clamp((p.z - cz) * scale, -bounds.z, bounds.z);
    out[id] = new THREE.Vector3(x, y, z);
  }
  return out;
}

/**
 * Force-directed cluster layout based on real cross-cluster edge counts.
 *
 * Spec §6 Step 2:
 * - 200 iterations
 * - dt=0.05
 * - damping=0.85
 * - repulsion: inverse-square between all clusters
 * - attraction: linear with weight ∝ shared edge count
 * - gravity: weak pull toward origin
 */
export function computeClusterForceCentroids(params: ClusterForceLayoutParams): ClusterForceLayoutResult {
  const {
    clusterIds,
    entitiesById,
    edges,
    initialCentroids,
    seed = 1337,
    bounds = CLUSTER_FORCE_BOUNDS_DEFAULT,
    iterations = 200,
    dt = 0.05,
    damping = 0.85,
    repulsionStrength = 14,
    attractionStrength = 0.0025,
    gravityStrength = 0.004,
  } = params;

  const edgeCounts = computeInterClusterEdgeCounts(edges, entitiesById, clusterIds);
  const rand = mulberry32(seed);

  const pos = new Map<ClusterId, Vec3>();
  const vel = new Map<ClusterId, Vec3>();
  for (const id of clusterIds) {
    const base = initialCentroids?.[id];
    const jitter = () => (rand() - 0.5) * 0.8;
    pos.set(id, {
      x: (base?.x ?? 0) * 0.4 + jitter(),
      y: (base?.y ?? 0) * 0.4 + jitter(),
      z: (base?.z ?? 0) * 0.4 + jitter(),
    });
    vel.set(id, { x: 0, y: 0, z: 0 });
  }

  const weights = new Map<string, number>();
  for (const [key, count] of edgeCounts) {
    // Linear attraction weight ∝ shared edge count (clamped to keep stability).
    weights.set(key, clamp(count, 0, 200));
  }

  const ids = [...clusterIds];
  const eps = 1e-6;
  for (let iter = 0; iter < iterations; iter++) {
    const acc = new Map<ClusterId, Vec3>();
    for (const id of ids) acc.set(id, { x: 0, y: 0, z: 0 });

    // Pairwise repulsion + pairwise attraction.
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        const a = ids[i];
        const b = ids[j];
        const pa = pos.get(a)!;
        const pb = pos.get(b)!;
        const dx = pb.x - pa.x;
        const dy = pb.y - pa.y;
        const dz = pb.z - pa.z;
        const distSq = dx * dx + dy * dy + dz * dz + eps;
        const dist = Math.sqrt(distSq);
        const ux = dx / dist;
        const uy = dy / dist;
        const uz = dz / dist;

        // Repulsion: inverse-square between all clusters.
        const rep = repulsionStrength / distSq;
        acc.get(a)!.x -= ux * rep;
        acc.get(a)!.y -= uy * rep;
        acc.get(a)!.z -= uz * rep;
        acc.get(b)!.x += ux * rep;
        acc.get(b)!.y += uy * rep;
        acc.get(b)!.z += uz * rep;

        // Attraction: linear with weight ∝ shared edge count.
        const w = weights.get(pairKey(a, b)) ?? 0;
        if (w > 0) {
          const attr = attractionStrength * w;
          // Linear spring-like pull: F = k * dx (not normalized).
          acc.get(a)!.x += dx * attr;
          acc.get(a)!.y += dy * attr;
          acc.get(a)!.z += dz * attr;
          acc.get(b)!.x -= dx * attr;
          acc.get(b)!.y -= dy * attr;
          acc.get(b)!.z -= dz * attr;
        }
      }
    }

    // Gravity: weak pull toward origin.
    for (const id of ids) {
      const p = pos.get(id)!;
      const a = acc.get(id)!;
      a.x += -p.x * gravityStrength;
      a.y += -p.y * gravityStrength;
      a.z += -p.z * gravityStrength;
    }

    // Integrate.
    for (const id of ids) {
      const a = acc.get(id)!;
      const v = vel.get(id)!;
      v.x = (v.x + a.x * dt) * damping;
      v.y = (v.y + a.y * dt) * damping;
      v.z = (v.z + a.z * dt) * damping;

      const p = pos.get(id)!;
      p.x += v.x * dt;
      p.y += v.y * dt;
      p.z += v.z * dt;
    }
  }

  return { centroids: normalizeToBounds(pos, bounds), edgeCounts };
}
