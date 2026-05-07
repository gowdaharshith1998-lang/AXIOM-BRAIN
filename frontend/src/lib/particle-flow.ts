import * as THREE from "three";

import { CLUSTER_COLORS, CLUSTER_CENTROIDS, type ClusterId } from "@/lib/cluster-layout";
import { conduitPathsForEdges, pointAtPathT, tangentAngleAtPathT, type ConduitPath } from "@/lib/curved-conduits";
import type { InterHubEdge } from "@/lib/hex-layout";

export type FlowParticle = {
  edgeKey: string;
  source: THREE.Vector3;
  target: THREE.Vector3;
  path?: THREE.Vector3[];
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
  if (particle.path) return pointAtPathT(particle.path, t);
  return particle.source.clone().lerp(particle.target, t);
}

export class ParticleFlowController {
  readonly points: THREE.Group;
  private readonly maxParticles: number;
  private readonly sprites: THREE.Sprite[] = [];
  private particles: FlowParticle[] = [];
  private edges: ConduitPath[] = [];
  private nextSpawnByEdge = new Map<string, number>();
  private pulseUntilByEdge = new Map<string, number>();
  private readonly chevronMaterial: THREE.SpriteMaterial;

  constructor(edges: InterHubEdge[] | ConduitPath[], maxParticles = 384) {
    this.maxParticles = maxParticles;
    this.points = new THREE.Group();
    this.chevronMaterial = new THREE.SpriteMaterial({
      map: createChevronTexture(),
      color: "#ffffff",
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    for (let i = 0; i < maxParticles; i++) {
      const sprite = new THREE.Sprite(this.chevronMaterial.clone());
      sprite.visible = false;
      sprite.scale.set(1.5, 1.5, 1);
      this.sprites.push(sprite);
      this.points.add(sprite);
    }
    this.setEdges(edges, 0);
  }

  setEdges(edges: InterHubEdge[] | ConduitPath[], nowMs: number): void {
    this.edges = edges.length > 0 && "points" in edges[0] ? (edges as ConduitPath[]) : conduitPathsForEdges(edges as InterHubEdge[]);
    for (const edge of edges) {
      if (!this.nextSpawnByEdge.has(edge.key)) {
        this.nextSpawnByEdge.set(edge.key, nowMs + spawnDelay(edge.key));
      }
    }
  }

  burst(edge: InterHubEdge, nowMs: number): void {
    for (let i = 0; i < 3; i++) {
      this.spawn(this.edgePath(edge), nowMs + i * 120, true);
    }
  }

  pulse(edge: InterHubEdge, nowMs: number): void {
    this.pulseUntilByEdge.set(edge.key, nowMs + 2000);
    this.burst(edge, nowMs);
  }

  update(nowMs: number): void {
    for (const edge of this.edges) {
      const next = this.nextSpawnByEdge.get(edge.key) ?? nowMs;
      if (nowMs >= next) {
        this.spawn(edge, nowMs, false);
        const pulsing = (this.pulseUntilByEdge.get(edge.key) ?? 0) > nowMs;
        this.nextSpawnByEdge.set(edge.key, nowMs + spawnDelay(edge.key, nowMs) / (pulsing ? 2 : 1));
      }
    }

    this.particles = this.particles.filter((particle) => nowMs - particle.startedAt <= particle.durationMs);
    const count = Math.min(this.particles.length, this.maxParticles);
    for (let i = 0; i < count; i++) {
      const particle = this.particles[i];
      const position = particlePositionAt(particle, nowMs);
      const sprite = this.sprites[i];
      sprite.position.copy(position);
      sprite.material.color.copy(particle.color);
      sprite.material.opacity = particle.trail ? 0.45 : 0.95;
      sprite.material.rotation = particle.path ? tangentAngleAtPathT(particle.path, (nowMs - particle.startedAt) / particle.durationMs) : 0;
      sprite.visible = true;
    }
    for (let i = count; i < this.sprites.length; i++) this.sprites[i].visible = false;
  }

  activeCount(): number {
    return this.particles.length;
  }

  dispose(): void {
    this.sprites.forEach((sprite) => sprite.material.dispose());
    this.chevronMaterial.map?.dispose();
    this.chevronMaterial.dispose();
  }

  private spawn(edge: ConduitPath, nowMs: number, burst: boolean): void {
    if (this.particles.length >= this.maxParticles) this.particles.shift();
    const particle = {
      edgeKey: edge.key,
      source: CLUSTER_CENTROIDS[edge.sourceCluster].clone(),
      target: CLUSTER_CENTROIDS[edge.targetCluster].clone(),
      path: edge.points,
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

  private edgePath(edge: InterHubEdge): ConduitPath {
    return this.edges.find((item) => item.key === edge.key) ?? conduitPathsForEdges([edge])[0];
  }
}

export function createChevronTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 32;
  canvas.height = 32;
  if (typeof navigator === "undefined" || !navigator.userAgent.includes("jsdom")) {
    const ctx = canvas.getContext("2d");
    if (ctx) {
      ctx.fillStyle = "#ffffff";
      ctx.beginPath();
      ctx.moveTo(25, 16);
      ctx.lineTo(8, 6);
      ctx.lineTo(12, 16);
      ctx.lineTo(8, 26);
      ctx.closePath();
      ctx.fill();
    }
  }
  return new THREE.CanvasTexture(canvas);
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
