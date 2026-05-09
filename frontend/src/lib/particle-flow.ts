import * as THREE from "three";

import { CLUSTER_COLORS, CLUSTER_CENTROIDS, type ClusterId } from "@/lib/cluster-layout";
import { conduitPathsForEdges, pointAtPathT, type ConduitPath } from "@/lib/curved-conduits";
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
  phase?: number;
  sourceCluster?: ClusterId;
  targetCluster?: ClusterId;
};

export function particleColorForClusters(sourceCluster: ClusterId, targetCluster: ClusterId, t = 0.5): THREE.Color {
  return new THREE.Color(CLUSTER_COLORS[sourceCluster]).lerp(new THREE.Color(CLUSTER_COLORS[targetCluster]), t);
}

export function particlePositionAt(particle: FlowParticle, nowMs: number): THREE.Vector3 {
  const raw = (nowMs - particle.startedAt) / particle.durationMs + (particle.phase ?? 0);
  const t = particle.phase === undefined || particle.burst ? THREE.MathUtils.clamp(raw, 0, 1) : raw - Math.floor(raw);
  if (particle.path) return pointAtPathT(particle.path, t);
  return particle.source.clone().lerp(particle.target, t);
}

export class ParticleFlowController {
  readonly points: THREE.Group;
  private readonly maxParticles: number;
  private readonly sprites: THREE.Sprite[] = [];
  private particles: FlowParticle[] = [];
  private readonly materialMap = new WeakMap<THREE.Sprite, THREE.SpriteMaterial>();
  private edges: ConduitPath[] = [];
  private pulseUntilByEdge = new Map<string, number>();

  constructor(edges: InterHubEdge[] | ConduitPath[], maxParticles = 384) {
    this.maxParticles = maxParticles;
    this.points = new THREE.Group();
    const texture = createDotTexture();
    for (let i = 0; i < maxParticles; i++) {
      const material = new THREE.SpriteMaterial({
        map: texture,
        color: "#ffffff",
        transparent: true,
        opacity: 0.95,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      });
      const sprite = new THREE.Sprite(material);
      sprite.visible = false;
      sprite.scale.set(0.55, 0.55, 1);
      this.materialMap.set(sprite, material);
      this.sprites.push(sprite);
      this.points.add(sprite);
    }
    this.setEdges(edges, 0);
  }

  setEdges(edges: InterHubEdge[] | ConduitPath[], nowMs: number): void {
    this.edges = edges.length > 0 && "points" in edges[0] ? (edges as ConduitPath[]) : conduitPathsForEdges(edges as InterHubEdge[]);
    const persistent: FlowParticle[] = [];
    for (const edge of this.edges.slice(0, 15)) {
      const particleCount = Math.min(8, Math.max(4, Math.round(4 + Math.min(edge.weight ?? 1, 16) / 4)));
      for (let i = 0; i < particleCount; i++) {
        persistent.push({
          edgeKey: edge.key,
          source: CLUSTER_CENTROIDS[edge.sourceCluster].clone(),
          target: CLUSTER_CENTROIDS[edge.targetCluster].clone(),
          path: edge.points,
          color: particleColorForClusters(edge.sourceCluster, edge.targetCluster),
          startedAt: nowMs - i * 260,
          durationMs: traversalMs(edge.key),
          burst: false,
          trail: false,
          phase: i / particleCount,
          sourceCluster: edge.sourceCluster,
          targetCluster: edge.targetCluster,
        });
      }
    }
    this.particles = persistent.slice(0, this.maxParticles);
  }

  burst(edge: InterHubEdge, nowMs: number): void {
    const path = this.edgePath(edge);
    for (let i = 0; i < 3; i++) this.spawnBurst(path, nowMs + i * 120, false);
  }

  pulse(edge: InterHubEdge, nowMs: number): void {
    this.pulseUntilByEdge.set(edge.key, nowMs + 2000);
    this.burst(edge, nowMs);
  }

  update(nowMs: number): void {
    this.particles = this.particles.filter((particle) => !particle.burst || nowMs - particle.startedAt <= particle.durationMs);
    const count = Math.min(this.particles.length, this.maxParticles);
    for (let i = 0; i < count; i++) {
      const particle = this.particles[i];
      const position = particlePositionAt(particle, nowMs);
      const sprite = this.sprites[i];
      const raw = (nowMs - particle.startedAt) / particle.durationMs + (particle.phase ?? 0);
      const t = particle.burst ? THREE.MathUtils.clamp(raw, 0, 1) : raw - Math.floor(raw);
      sprite.position.copy(position);
      const material = this.materialMap.get(sprite);
      if (material) {
        if (particle.sourceCluster && particle.targetCluster) {
          material.color.copy(particleColorForClusters(particle.sourceCluster, particle.targetCluster, t));
        } else {
          material.color.copy(particle.color);
        }
        const pulseBoost = (this.pulseUntilByEdge.get(particle.edgeKey) ?? 0) > nowMs ? 1.35 : 1;
        material.opacity = (particle.trail ? 0.45 : 0.95) * pulseBoost;
      }
      const scale = particle.burst ? 0.7 : THREE.MathUtils.lerp(0.42, 0.62, Math.sin(t * Math.PI));
      sprite.scale.set(scale, scale, 1);
      sprite.visible = true;
    }
    for (let i = count; i < this.sprites.length; i++) this.sprites[i].visible = false;
  }

  activeCount(): number {
    return this.particles.length;
  }

  dispose(): void {
    const disposed = new Set<THREE.Texture>();
    this.sprites.forEach((sprite) => {
      const material = this.materialMap.get(sprite);
      if (!material) return;
      if (material.map && !disposed.has(material.map)) {
        disposed.add(material.map);
        material.map.dispose();
      }
      material.dispose();
    });
  }

  private spawnBurst(edge: ConduitPath, nowMs: number, trail: boolean): void {
    if (this.particles.length >= this.maxParticles) this.particles.shift();
    const particle: FlowParticle = {
      edgeKey: edge.key,
      source: CLUSTER_CENTROIDS[edge.sourceCluster].clone(),
      target: CLUSTER_CENTROIDS[edge.targetCluster].clone(),
      path: edge.points,
      color: particleColorForClusters(edge.sourceCluster, edge.targetCluster),
      startedAt: nowMs,
      durationMs: Math.max(1800, traversalMs(edge.key) * 0.45),
      burst: true,
      trail,
      sourceCluster: edge.sourceCluster,
      targetCluster: edge.targetCluster,
    };
    this.particles.push(particle);
    if (!trail) this.spawnBurst(edge, nowMs + 80, true);
  }

  private edgePath(edge: InterHubEdge): ConduitPath {
    return this.edges.find((item) => item.key === edge.key) ?? conduitPathsForEdges([edge])[0];
  }
}

export function createDotTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 64;
  canvas.height = 64;
  const isJsdom = typeof navigator !== "undefined" && navigator.userAgent.includes("jsdom");
  const ctx = isJsdom ? null : canvas.getContext("2d");
  if (ctx) {
    const gradient = ctx.createRadialGradient(32, 32, 0, 32, 32, 30);
    gradient.addColorStop(0, "rgba(255,255,255,1)");
    gradient.addColorStop(0.35, "rgba(255,255,255,0.95)");
    gradient.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  }
  return new THREE.CanvasTexture(canvas);
}

export function createChevronTexture(): THREE.CanvasTexture {
  return createDotTexture();
}

export function traversalMs(key: string): number {
  return 8000 + (hash(key) % 4000);
}

export function spawnDelay(key: string, salt = 0): number {
  return 350 + (hash(`${key}:${Math.floor(salt)}`) % 250);
}

function hash(value: string): number {
  let out = 0;
  for (let i = 0; i < value.length; i++) out = (out * 31 + value.charCodeAt(i)) >>> 0;
  return out;
}
