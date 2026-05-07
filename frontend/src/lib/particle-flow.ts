import * as THREE from "three";

import { CLUSTER_COLORS, CLUSTER_CENTROIDS, type ClusterId } from "@/lib/cluster-layout";
import type { InterHubEdge } from "@/lib/hex-layout";

export type FlowParticle = {
  edgeKey: string;
  source: THREE.Vector3;
  target: THREE.Vector3;
  color: THREE.Color;
  startedAt: number;
  durationMs: number;
  burst: boolean;
  trail: boolean;
};

export function particleColorForClusters(sourceCluster: ClusterId, targetCluster: ClusterId): THREE.Color {
  return new THREE.Color(CLUSTER_COLORS[sourceCluster]).lerp(new THREE.Color(CLUSTER_COLORS[targetCluster]), 0.5);
}

export function particlePositionAt(particle: FlowParticle, nowMs: number): THREE.Vector3 {
  const t = THREE.MathUtils.clamp((nowMs - particle.startedAt) / particle.durationMs, 0, 1);
  return particle.source.clone().lerp(particle.target, t);
}

export class ParticleFlowController {
  readonly points: THREE.Points;
  private readonly maxParticles: number;
  private readonly positions: Float32Array;
  private readonly colors: Float32Array;
  private particles: FlowParticle[] = [];
  private edges: InterHubEdge[] = [];
  private nextSpawnByEdge = new Map<string, number>();

  constructor(edges: InterHubEdge[], maxParticles = 384) {
    this.maxParticles = maxParticles;
    this.positions = new Float32Array(maxParticles * 3);
    this.colors = new Float32Array(maxParticles * 3);
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(this.positions, 3));
    geometry.setAttribute("color", new THREE.BufferAttribute(this.colors, 3));
    geometry.setDrawRange(0, 0);
    const material = new THREE.PointsMaterial({
      size: 1.6,
      vertexColors: true,
      transparent: true,
      opacity: 1,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    this.points = new THREE.Points(geometry, material);
    this.setEdges(edges, 0);
  }

  setEdges(edges: InterHubEdge[], nowMs: number): void {
    this.edges = edges;
    for (const edge of edges) {
      if (!this.nextSpawnByEdge.has(edge.key)) {
        this.nextSpawnByEdge.set(edge.key, nowMs + spawnDelay(edge.key));
      }
    }
  }

  burst(edge: InterHubEdge, nowMs: number): void {
    for (let i = 0; i < 3; i++) {
      this.spawn(edge, nowMs + i * 120, true);
    }
  }

  update(nowMs: number): void {
    for (const edge of this.edges) {
      const next = this.nextSpawnByEdge.get(edge.key) ?? nowMs;
      if (nowMs >= next) {
        this.spawn(edge, nowMs, false);
        this.nextSpawnByEdge.set(edge.key, nowMs + spawnDelay(edge.key, nowMs));
      }
    }

    this.particles = this.particles.filter((particle) => nowMs - particle.startedAt <= particle.durationMs);
    const count = Math.min(this.particles.length, this.maxParticles);
    for (let i = 0; i < count; i++) {
      const particle = this.particles[i];
      const position = particlePositionAt(particle, nowMs);
      this.positions[i * 3] = position.x;
      this.positions[i * 3 + 1] = position.y;
      this.positions[i * 3 + 2] = position.z;
      this.colors[i * 3] = particle.color.r;
      this.colors[i * 3 + 1] = particle.color.g;
      this.colors[i * 3 + 2] = particle.color.b;
    }
    this.points.geometry.setDrawRange(0, count);
    const positionAttr = this.points.geometry.getAttribute("position");
    const colorAttr = this.points.geometry.getAttribute("color");
    if (positionAttr) positionAttr.needsUpdate = true;
    if (colorAttr) colorAttr.needsUpdate = true;
  }

  activeCount(): number {
    return this.particles.length;
  }

  dispose(): void {
    this.points.geometry.dispose();
    const material = this.points.material;
    if (Array.isArray(material)) material.forEach((m) => m.dispose());
    else material.dispose();
  }

  private spawn(edge: InterHubEdge, nowMs: number, burst: boolean): void {
    if (this.particles.length >= this.maxParticles) this.particles.shift();
    const particle = {
      edgeKey: edge.key,
      source: CLUSTER_CENTROIDS[edge.sourceCluster].clone(),
      target: CLUSTER_CENTROIDS[edge.targetCluster].clone(),
      color: particleColorForClusters(edge.sourceCluster, edge.targetCluster),
      startedAt: nowMs,
      durationMs: traversalMs(edge.key),
      burst,
      trail: false,
    };
    this.particles.push(particle);
    if (this.particles.length >= this.maxParticles) this.particles.shift();
    this.particles.push({
      ...particle,
      color: particle.color.clone().multiplyScalar(0.55),
      startedAt: nowMs + 80,
      trail: true,
    });
  }
}

export function traversalMs(key: string): number {
  return 1100 + (hash(key) % 400);
}

export function spawnDelay(key: string, salt = 0): number {
  return 350 + (hash(`${key}:${Math.floor(salt)}`) % 250);
}

function hash(value: string): number {
  let out = 0;
  for (let i = 0; i < value.length; i++) out = (out * 31 + value.charCodeAt(i)) >>> 0;
  return out;
}
