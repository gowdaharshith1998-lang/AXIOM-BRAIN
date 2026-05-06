import * as THREE from "three";

import { colorForRelationship } from "@/lib/edge-tint";

const MIN_OPACITY = 0.1;
const MAX_OPACITY = 0.22;
const TWO_PI = Math.PI * 2;

function hashToUnit(id: string): number {
  let hash = 2166136261;
  for (let i = 0; i < id.length; i++) {
    hash ^= id.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) / 4294967296;
}

export function phaseOffsetFromEdgeKey(edgeKey: string): number {
  return hashToUnit(edgeKey) * TWO_PI;
}

export function computeEdgeOpacity(timeMs: number, phaseOffset: number): number {
  const t = timeMs / 2000 + phaseOffset;
  const octave1 = (Math.sin(t) + 1) / 2;
  const octave2 = (Math.sin(t * 2.07 + phaseOffset * 0.37) + 1) / 2;
  const fbm = octave1 * 0.68 + octave2 * 0.32;
  return MIN_OPACITY + fbm * (MAX_OPACITY - MIN_OPACITY);
}

export function shimmerOpacity(edgeId: string, timeMs: number): number {
  return computeEdgeOpacity(timeMs, phaseOffsetFromEdgeKey(edgeId));
}

export function createEdgeShimmerMaterial(): THREE.LineBasicMaterial {
  return new THREE.LineBasicMaterial({
    transparent: true,
    depthWrite: false,
    vertexColors: true,
    blending: THREE.AdditiveBlending,
  });
}

export interface EdgeShimmerSpec {
  geom: THREE.BufferGeometry;
  edgeKeys: ReadonlyArray<string>;
  edgeRelationships: ReadonlyArray<string>;
  phases: ReadonlyMap<string, number>;
}

export function updateEdgeShimmer(spec: EdgeShimmerSpec, timeMs: number): void {
  const colorAttr = spec.geom.getAttribute("color");
  if (!(colorAttr instanceof THREE.BufferAttribute)) return;

  const arr = colorAttr.array as Float32Array;
  const color = new THREE.Color();
  let i = 0;

  for (let edgeIndex = 0; edgeIndex < spec.edgeKeys.length; edgeIndex++) {
    const key = spec.edgeKeys[edgeIndex];
    color.set(colorForRelationship(spec.edgeRelationships[edgeIndex] ?? ""));
    const opacity = computeEdgeOpacity(timeMs, spec.phases.get(key) ?? 0);

    arr[i++] = color.r;
    arr[i++] = color.g;
    arr[i++] = color.b;
    arr[i++] = opacity;
    arr[i++] = color.r;
    arr[i++] = color.g;
    arr[i++] = color.b;
    arr[i++] = opacity;
  }

  colorAttr.needsUpdate = true;
}

export class EdgeShimmer {
  private readonly phases: ReadonlyMap<string, number>;

  constructor(
    private readonly edgeIds: readonly string[],
    private readonly geometry: THREE.BufferGeometry,
  ) {
    this.phases = new Map(edgeIds.map((id) => [id, phaseOffsetFromEdgeKey(id)]));
  }

  update(timeMs: number): void {
    updateEdgeShimmer(
      {
        geom: this.geometry,
        edgeKeys: this.edgeIds,
        edgeRelationships: [],
        phases: this.phases,
      },
      timeMs,
    );
  }
}
