import * as THREE from "three";

import { CLUSTER_CENTROIDS, CLUSTER_RADIUS } from "@/lib/cluster-layout";
import { packSatellites, type SatelliteRing } from "@/lib/satellite-pack";
import type { ClusterId } from "@/lib/cluster-layout";
import { HEX_NODE_RADIUS } from "@/lib/hex-geometry";
import type { Edge, Entity } from "@/state/brain.store";

function hashSeed(value: string): number {
  let out = 0;
  for (let i = 0; i < value.length; i++) out = (out * 31 + value.charCodeAt(i)) >>> 0;
  return out;
}

export const CLUSTER_HUB_SPACING = 90;
export const CLUSTER_RING_RADIUS = 18;
export const CLUSTER_RING_STEP = 6;
export const CLUSTER_VISIBLE_SLOTS = [8, 12, 16, 20, 24] as const;
export const MAX_VISIBLE_PER_CLUSTER = CLUSTER_VISIBLE_SLOTS.reduce((total, next) => total + next, 0);

export const HEX_CLUSTER_CENTROIDS: Record<ClusterId, THREE.Vector3> = CLUSTER_CENTROIDS;

export type VisibleEntitySlot = {
  entity: Entity;
  clusterId: ClusterId;
  position: THREE.Vector3;
  ring: SatelliteRing;
  slot: number;
  hexRadius: number;
};

export type InterHubEdge = {
  key: string;
  sourceCluster: ClusterId;
  targetCluster: ClusterId;
  weight?: number;
};

export function entityImportance(entity: Entity): number {
  const direct = entity.composite_importance;
  if (typeof direct === "number" && Number.isFinite(direct)) return direct;
  const nested = entity.data?.composite_importance;
  return typeof nested === "number" && Number.isFinite(nested) ? nested : 0;
}

export function sortedVisibleEntities(entities: Entity[], maxVisible = MAX_VISIBLE_PER_CLUSTER): Entity[] {
  return [...entities]
    .sort((a, b) => entityImportance(b) - entityImportance(a) || a.id.localeCompare(b.id))
    .slice(0, maxVisible);
}

export function computeStarburstPositions(
  entities: Entity[],
  centroids: Record<ClusterId, THREE.Vector3> = HEX_CLUSTER_CENTROIDS,
): Map<string, THREE.Vector3> {
  const positioned = new Map<string, THREE.Vector3>();
  const visible = sortedVisibleEntities(entities);
  const cluster = visible.find((entity) => entity.cluster_id)?.cluster_id;
  if (!cluster || !(cluster in centroids)) return positioned;
  const centroid = centroids[cluster as ClusterId];

  let index = 0;
  for (let ring = 0; ring < CLUSTER_VISIBLE_SLOTS.length; ring++) {
    const slots = CLUSTER_VISIBLE_SLOTS[ring];
    const radius = CLUSTER_RING_RADIUS + ring * CLUSTER_RING_STEP;
    for (let slot = 0; slot < slots && index < visible.length; slot++) {
      const angle = (slot / slots) * Math.PI * 2;
      const z = centroid.z + (ring - 1) * 1.8;
      positioned.set(
        visible[index].id,
        new THREE.Vector3(
          centroid.x + Math.cos(angle) * radius,
          centroid.y + Math.sin(angle) * radius,
          z,
        ),
      );
      index++;
    }
  }

  return positioned;
}

export function computeVisibleEntitySlots(
  entities: Iterable<Entity>,
  clusterIds: readonly ClusterId[],
  maxVisiblePerCluster = MAX_VISIBLE_PER_CLUSTER,
  centroids: Record<ClusterId, THREE.Vector3> = HEX_CLUSTER_CENTROIDS,
): VisibleEntitySlot[] {
  const byCluster = new Map<ClusterId, Entity[]>();
  for (const id of clusterIds) byCluster.set(id, []);
  for (const entity of entities) {
    const cluster = entity.cluster_id;
    if (cluster && byCluster.has(cluster as ClusterId)) {
      byCluster.get(cluster as ClusterId)?.push(entity);
    }
  }

  const slotsOut: VisibleEntitySlot[] = [];
  for (const clusterId of clusterIds) {
    const visible = sortedVisibleEntities(byCluster.get(clusterId) ?? [], maxVisiblePerCluster);
    const centroid = centroids[clusterId];
    const packed = packSatellites({
      centroid,
      count: visible.length,
      clusterRadius: CLUSTER_RADIUS[clusterId],
      seed: (hashSeed(clusterId) ^ 1337) >>> 0,
      baseHexRadius: HEX_NODE_RADIUS,
    });
    for (let i = 0; i < visible.length; i++) {
      const sat = packed[i];
      if (!sat) break;
      slotsOut.push({
        entity: visible[i],
        clusterId,
        position: sat.position,
        ring: sat.ring,
        slot: i,
        hexRadius: sat.hexRadius,
      });
    }
  }
  return slotsOut;
}

export function countEntitiesByCluster(entities: Iterable<Entity>, clusterId: ClusterId): number {
  let count = 0;
  for (const entity of entities) {
    if (entity.cluster_id === clusterId) count++;
  }
  return count;
}

export function computeInterHubEdges(
  edges: Iterable<Edge>,
  entitiesById: Map<string, Entity>,
  centroids: Record<ClusterId, THREE.Vector3> = HEX_CLUSTER_CENTROIDS,
): InterHubEdge[] {
  const pairs = new Map<string, InterHubEdge>();
  for (const edge of edges) {
    const sourceCluster = entitiesById.get(edge.source_id)?.cluster_id as ClusterId | undefined;
    const targetCluster = entitiesById.get(edge.target_id)?.cluster_id as ClusterId | undefined;
    if (!sourceCluster || !targetCluster || sourceCluster === targetCluster) continue;
    if (!(sourceCluster in centroids) || !(targetCluster in centroids)) continue;
    const sorted = [sourceCluster, targetCluster].sort() as [ClusterId, ClusterId];
    const key = `${sorted[0]}:${sorted[1]}`;
    const existing = pairs.get(key);
    if (existing) {
      existing.weight = (existing.weight ?? 1) + 1;
    } else {
      pairs.set(key, { key, sourceCluster: sorted[0], targetCluster: sorted[1], weight: 1 });
    }
  }
  return Array.from(pairs.values()).sort((a, b) => (b.weight ?? 0) - (a.weight ?? 0) || a.key.localeCompare(b.key));
}

export function findEntityPosition(
  entity: Entity | undefined,
  positionsById: Map<string, THREE.Vector3>,
  centroids: Record<ClusterId, THREE.Vector3> = HEX_CLUSTER_CENTROIDS,
): THREE.Vector3 | null {
  if (!entity) return null;
  const visible = positionsById.get(entity.id);
  if (visible) return visible.clone();
  const cluster = entity.cluster_id as ClusterId | undefined;
  if (cluster && cluster in centroids) return centroids[cluster].clone();
  return null;
}
