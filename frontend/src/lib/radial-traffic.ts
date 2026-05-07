import * as THREE from "three";

import { CLUSTER_CENTROIDS, CLUSTER_COLORS } from "@/lib/cluster-layout";
import type { VisibleEntitySlot } from "@/lib/hex-layout";

export type RadialTrafficDot = {
  key: string;
  source: THREE.Vector3;
  target: THREE.Vector3;
  color: THREE.Color;
  startedAt: number;
  durationMs: number;
};

export function radialTrafficPositionAt(dot: RadialTrafficDot, nowMs: number): THREE.Vector3 {
  const t = THREE.MathUtils.clamp((nowMs - dot.startedAt) / dot.durationMs, 0, 1);
  return dot.source.clone().lerp(dot.target, t);
}

export function radialTrafficColor(slot: VisibleEntitySlot): THREE.Color {
  return new THREE.Color(CLUSTER_COLORS[slot.clusterId]);
}

export class RadialTrafficController {
  readonly points: THREE.Points;
  private readonly maxParticles: number;
  private readonly positions: Float32Array;
  private readonly colors: Float32Array;
  private slots: VisibleEntitySlot[] = [];
  private dots: RadialTrafficDot[] = [];
  private nextSpawnBySlot = new Map<string, number>();

  constructor(slots: VisibleEntitySlot[], maxParticles = 600) {
    this.maxParticles = maxParticles;
    this.positions = new Float32Array(maxParticles * 3);
    this.colors = new Float32Array(maxParticles * 3);
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(this.positions, 3));
    geometry.setAttribute("color", new THREE.BufferAttribute(this.colors, 3));
    geometry.setDrawRange(0, 0);
    const material = new THREE.PointsMaterial({
      size: 1,
      vertexColors: true,
      transparent: true,
      opacity: 0.7,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    this.points = new THREE.Points(geometry, material);
    this.setSlots(slots, 0);
  }

  setSlots(slots: VisibleEntitySlot[], nowMs: number): void {
    this.slots = slots;
    for (const slot of slots) {
      if (!this.nextSpawnBySlot.has(slot.entity.id)) {
        this.nextSpawnBySlot.set(slot.entity.id, nowMs + spawnDelay(slot.entity.id));
      }
    }
  }

  update(nowMs: number): void {
    for (const slot of this.slots) {
      const next = this.nextSpawnBySlot.get(slot.entity.id) ?? nowMs;
      if (nowMs >= next) {
        this.spawn(slot, nowMs);
        this.nextSpawnBySlot.set(slot.entity.id, nowMs + spawnDelay(slot.entity.id, nowMs));
      }
    }

    this.dots = this.dots.filter((dot) => nowMs - dot.startedAt <= dot.durationMs);
    const count = Math.min(this.dots.length, this.maxParticles);
    for (let i = 0; i < count; i++) {
      const dot = this.dots[i];
      const position = radialTrafficPositionAt(dot, nowMs);
      this.positions[i * 3] = position.x;
      this.positions[i * 3 + 1] = position.y;
      this.positions[i * 3 + 2] = position.z;
      this.colors[i * 3] = dot.color.r;
      this.colors[i * 3 + 1] = dot.color.g;
      this.colors[i * 3 + 2] = dot.color.b;
    }
    this.points.geometry.setDrawRange(0, count);
    const positionAttr = this.points.geometry.getAttribute("position");
    const colorAttr = this.points.geometry.getAttribute("color");
    if (positionAttr) positionAttr.needsUpdate = true;
    if (colorAttr) colorAttr.needsUpdate = true;
  }

  activeCount(): number {
    return this.dots.length;
  }

  dispose(): void {
    this.points.geometry.dispose();
    const material = this.points.material;
    if (Array.isArray(material)) material.forEach((m) => m.dispose());
    else material.dispose();
  }

  private spawn(slot: VisibleEntitySlot, nowMs: number): void {
    if (this.dots.length >= this.maxParticles) this.dots.shift();
    this.dots.push({
      key: slot.entity.id,
      source: CLUSTER_CENTROIDS[slot.clusterId].clone(),
      target: slot.position.clone(),
      color: radialTrafficColor(slot),
      startedAt: nowMs,
      durationMs: traversalMs(slot.entity.id),
    });
  }
}

function traversalMs(seed: string): number {
  return 1500 + (hash(seed) % 700);
}

function spawnDelay(seed: string, salt = 0): number {
  return 2200 + (hash(`${seed}:${Math.floor(salt)}`) % 1300);
}

function hash(value: string): number {
  let out = 0;
  for (let i = 0; i < value.length; i++) out = (out * 31 + value.charCodeAt(i)) >>> 0;
  return out;
}
