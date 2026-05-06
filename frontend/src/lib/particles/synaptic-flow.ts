import * as THREE from "three";

import { colorForRelationship } from "@/lib/edge-tint";
import type { FpsGuardState } from "@/lib/fps-guard";

export type SynapticFlowEdge = {
  id: string;
  sourceId: string;
  targetId: string;
  relationship: string;
};

export type SynapticFlowPosition = {
  source: THREE.Vector3;
  target: THREE.Vector3;
};

type GetNodePositions = (edge: SynapticFlowEdge) => SynapticFlowPosition | null;

const PARTICLES_FULL = 3;
const PARTICLES_HALF = 2;
const TWO_PI = Math.PI * 2;

let activeFlow: SynapticFlow | null = null;

export function particleCountForFps(edgeCount: number, fpsState: FpsGuardState): number {
  if (fpsState === "emergency") return 0;
  return edgeCount * (fpsState === "half" ? PARTICLES_HALF : PARTICLES_FULL);
}

export function particlePositionAtT(source: THREE.Vector3, target: THREE.Vector3, t: number): THREE.Vector3 {
  return source.clone().lerp(target, t);
}

export function wrapParticleT(t: number): number {
  if (t < 1) return Math.max(0, t);
  return t % 1;
}

export function createSynapticFlow(
  scene: THREE.Scene,
  edges: SynapticFlowEdge[],
  edgePhases: ReadonlyMap<string, number>,
  getNodePositions: GetNodePositions,
): SynapticFlow {
  activeFlow?.disposeSynapticFlow();
  activeFlow = new SynapticFlow(scene, edges, edgePhases, getNodePositions);
  return activeFlow;
}

export function updateSynapticFlow(timeMs: number, dtMs: number, fpsState: FpsGuardState = "full"): void {
  activeFlow?.updateSynapticFlow(timeMs, dtMs, fpsState);
}

export function disposeSynapticFlow(): void {
  activeFlow?.disposeSynapticFlow();
  activeFlow = null;
}

export class SynapticFlow {
  private edges: SynapticFlowEdge[];
  private readonly geometry = new THREE.BufferGeometry();
  private readonly material = new THREE.PointsMaterial({
    size: 2.5,
    vertexColors: true,
    transparent: true,
    opacity: 0.85,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  private readonly points = new THREE.Points(this.geometry, this.material);
  private progress = new Float32Array(0);
  private speed = new Float32Array(0);
  private edgeIndexByParticle = new Uint32Array(0);
  private fpsState: FpsGuardState = "full";

  constructor(
    private readonly scene: THREE.Scene,
    edges: SynapticFlowEdge[],
    private readonly edgePhases: ReadonlyMap<string, number>,
    private readonly getNodePositions: GetNodePositions,
  ) {
    this.edges = edges.slice();
    this.scene.add(this.points);
    this.rebuild("full");
  }

  setEdges(edges: SynapticFlowEdge[]): void {
    this.edges = edges.slice();
    this.rebuild(this.fpsState);
  }

  particleCount(): number {
    return this.progress.length;
  }

  updateSynapticFlow(_timeMs: number, dtMs: number, fpsState: FpsGuardState = "full"): void {
    if (fpsState !== this.fpsState || this.particleCount() !== particleCountForFps(this.edges.length, fpsState)) {
      this.rebuild(fpsState);
    }
    if (this.progress.length === 0) return;

    const positionAttr = this.geometry.getAttribute("position");
    const colorAttr = this.geometry.getAttribute("color");
    if (!(positionAttr instanceof THREE.BufferAttribute) || !(colorAttr instanceof THREE.BufferAttribute)) return;

    const positions = positionAttr.array as Float32Array;
    const colors = colorAttr.array as Float32Array;
    const color = new THREE.Color();
    const dtSeconds = Math.max(0, dtMs) / 1000;

    for (let particleIndex = 0; particleIndex < this.progress.length; particleIndex++) {
      const edge = this.edges[this.edgeIndexByParticle[particleIndex]];
      this.progress[particleIndex] = wrapParticleT(this.progress[particleIndex] + this.speed[particleIndex] * dtSeconds);
      const nodePositions = this.getNodePositions(edge);
      if (!nodePositions) continue;

      const pos = particlePositionAtT(nodePositions.source, nodePositions.target, this.progress[particleIndex]);
      const posOffset = particleIndex * 3;
      positions[posOffset] = pos.x;
      positions[posOffset + 1] = pos.y;
      positions[posOffset + 2] = pos.z;

      color.set(colorForRelationship(edge.relationship));
      colors[posOffset] = color.r;
      colors[posOffset + 1] = color.g;
      colors[posOffset + 2] = color.b;
    }

    positionAttr.needsUpdate = true;
    colorAttr.needsUpdate = true;
  }

  disposeSynapticFlow(): void {
    this.scene.remove(this.points);
    this.geometry.dispose();
    this.material.dispose();
  }

  private rebuild(fpsState: FpsGuardState): void {
    this.fpsState = fpsState;
    const particlesPerEdge = fpsState === "emergency" ? 0 : fpsState === "half" ? PARTICLES_HALF : PARTICLES_FULL;
    const particleCount = this.edges.length * particlesPerEdge;
    this.progress = new Float32Array(particleCount);
    this.speed = new Float32Array(particleCount);
    this.edgeIndexByParticle = new Uint32Array(particleCount);

    const positions = new Float32Array(particleCount * 3);
    const colors = new Float32Array(particleCount * 3);
    let particleIndex = 0;
    for (let edgeIndex = 0; edgeIndex < this.edges.length; edgeIndex++) {
      const edge = this.edges[edgeIndex];
      const phaseUnit = ((this.edgePhases.get(edge.id) ?? 0) % TWO_PI) / TWO_PI;
      for (let slot = 0; slot < particlesPerEdge; slot++) {
        this.edgeIndexByParticle[particleIndex] = edgeIndex;
        this.progress[particleIndex] = (phaseUnit + slot / Math.max(1, particlesPerEdge)) % 1;
        this.speed[particleIndex] = 0.4 + ((phaseUnit + slot * 0.173) % 0.2);
        particleIndex++;
      }
    }

    this.geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    this.geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    this.geometry.setDrawRange(0, particleCount);
    this.points.visible = particleCount > 0;
  }
}
