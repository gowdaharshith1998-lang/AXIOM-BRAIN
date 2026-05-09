/**
 * Phase 5 Finish — Event-driven particle behaviors.
 *
 * Six behaviors, each triggered by a real backend event.
 * No decorative particles — every particle is driven by data.
 */
import * as THREE from "three";

import type { BrainEvent } from "@/lib/websocket";

// ── Types ──────────────────────────────────────────────────────────────

export type ParticleBehavior =
  | "ingest_stream"
  | "traversal_flow"
  | "confidence_change"
  | "signing_burst"
  | "refusal_pattern"
  | "correct_signal";

export interface ActiveParticle {
  behavior: ParticleBehavior;
  position: THREE.Vector3;
  velocity: THREE.Vector3;
  color: THREE.Color;
  opacity: number;
  startedAt: number;
  durationMs: number;
  demo: boolean;
  /** Label text for DEMO badge sprite */
  demoBadge: boolean;
}

export type PositionResolver = (entityId: string) => THREE.Vector3 | null;

// ── Colors ─────────────────────────────────────────────────────────────

const COLOR_INGEST_NEUTRAL = new THREE.Color("#8BB8E8");
const COLOR_TRAVERSAL = new THREE.Color("#A8D8FF");
const COLOR_CONFIDENCE_RISING = new THREE.Color("#00E5FF");
const COLOR_CONFIDENCE_FALLING = new THREE.Color("#B388FF");
const COLOR_SIGNING_ED25519 = new THREE.Color("#4CAF50");
const COLOR_SIGNING_ML_DSA = new THREE.Color("#2196F3");
const COLOR_SIGNING_HYBRID = new THREE.Color("#009688");
const COLOR_REFUSAL = new THREE.Color("#FF1744");
const COLOR_CORRECT = new THREE.Color("#FFB300");

const MAX_PARTICLES = 200;
const DEMO_OPACITY_FACTOR = 0.6;

// ── Pool ───────────────────────────────────────────────────────────────

export class ParticleBehaviorPool {
  readonly particles: ActiveParticle[] = [];
  private _screenEdge = new THREE.Vector3(-120, 0, 0);

  setScreenEdge(v: THREE.Vector3): void {
    this._screenEdge.copy(v);
  }

  get activeCount(): number {
    return this.particles.length;
  }

  handleEvent(event: BrainEvent, resolve: PositionResolver): void {
    const payload = event.payload as Record<string, unknown>;
    switch (event.type) {
      case "entity_added":
      case "entity_created":
        this._emitIngestStream(event, resolve);
        break;
      case "agent_navigation_step":
        this._emitTraversalFlow(payload, resolve);
        break;
      case "confidence_changed":
        this._emitConfidenceChange(payload, resolve);
        break;
      case "receipt_added":
        this._emitSigningBurst(payload, resolve);
        break;
      case "agent_action_evaluated": {
        const decision = payload.decision as string | undefined;
        if (decision === "deny") this._emitRefusalPattern(payload, resolve);
        else if (decision === "correct") this._emitCorrectSignal(payload, resolve);
        break;
      }
    }
  }

  update(nowMs: number): void {
    let write = 0;
    for (let i = 0; i < this.particles.length; i++) {
      const p = this.particles[i];
      const age = nowMs - p.startedAt;
      if (age > p.durationMs) continue;

      const t = age / p.durationMs;
      p.position.add(p.velocity.clone().multiplyScalar(16.7 / p.durationMs));
      p.opacity = (1 - t * t) * (p.demo ? DEMO_OPACITY_FACTOR : 1.0);

      if (write !== i) this.particles[write] = p;
      write++;
    }
    this.particles.length = write;
  }

  clear(): void {
    this.particles.length = 0;
  }

  // ── Behavior implementations ───────────────────────────────────────

  private _emitIngestStream(event: BrainEvent, resolve: PositionResolver): void {
    const id = event.persisted_id;
    if (!id) return;
    const target = resolve(id);
    if (!target) return;
    const demo = Boolean((event.payload as Record<string, unknown>).demo);
    const count = 5;
    for (let i = 0; i < count; i++) {
      const start = this._screenEdge.clone().add(new THREE.Vector3(0, (i - 2) * 2, 0));
      this._spawn({
        behavior: "ingest_stream",
        position: start,
        velocity: target.clone().sub(start).normalize().multiplyScalar(0.8),
        color: COLOR_INGEST_NEUTRAL.clone(),
        opacity: 1,
        startedAt: performance.now() + i * 80,
        durationMs: 2000,
        demo,
        demoBadge: demo,
      });
    }
  }

  private _emitTraversalFlow(payload: Record<string, unknown>, resolve: PositionResolver): void {
    const fromId = payload.from_id as string | undefined;
    const toId = payload.to_id as string | undefined;
    if (!fromId || !toId) return;
    const from = resolve(fromId);
    const to = resolve(toId);
    if (!from || !to) return;
    const demo = Boolean(payload.demo);
    const count = 3;
    for (let i = 0; i < count; i++) {
      this._spawn({
        behavior: "traversal_flow",
        position: from.clone(),
        velocity: to.clone().sub(from).normalize().multiplyScalar(0.6),
        color: COLOR_TRAVERSAL.clone(),
        opacity: 1,
        startedAt: performance.now() + i * 100,
        durationMs: 1800,
        demo,
        demoBadge: demo,
      });
    }
  }

  private _emitConfidenceChange(payload: Record<string, unknown>, resolve: PositionResolver): void {
    const entityId = payload.entity_id as string | undefined;
    if (!entityId) return;
    const center = resolve(entityId);
    if (!center) return;
    const direction = payload.direction as string;
    const demo = Boolean(payload.demo);
    const rising = direction === "rising";
    const color = rising ? COLOR_CONFIDENCE_RISING : COLOR_CONFIDENCE_FALLING;
    const count = 4;

    for (let i = 0; i < count; i++) {
      const angle = (i / count) * Math.PI * 2;
      const outward = new THREE.Vector3(Math.cos(angle), Math.sin(angle), 0).multiplyScalar(rising ? -0.3 : 0.3);
      this._spawn({
        behavior: "confidence_change",
        position: rising ? center.clone().add(outward.clone().multiplyScalar(15)) : center.clone(),
        velocity: outward,
        color: color.clone(),
        opacity: 1,
        startedAt: performance.now() + i * 60,
        durationMs: 1600,
        demo,
        demoBadge: demo,
      });
    }
  }

  private _emitSigningBurst(payload: Record<string, unknown>, resolve: PositionResolver): void {
    const actionId = payload.action_id as string | undefined;
    const entityId = (payload.target_entity_id ?? actionId) as string | undefined;
    const scheme = (payload.signing_scheme ?? "ed25519") as string;
    const demo = Boolean(payload.demo);

    const center = entityId ? resolve(entityId) : null;
    const origin = center ?? new THREE.Vector3(0, 0, 0);

    let color: THREE.Color;
    if (scheme === "ml_dsa_65") color = COLOR_SIGNING_ML_DSA.clone();
    else if (scheme === "hybrid") color = COLOR_SIGNING_HYBRID.clone();
    else color = COLOR_SIGNING_ED25519.clone();

    const count = 6;
    for (let i = 0; i < count; i++) {
      const angle = (i / count) * Math.PI * 2;
      this._spawn({
        behavior: "signing_burst",
        position: origin.clone(),
        velocity: new THREE.Vector3(Math.cos(angle), Math.sin(angle), 0).multiplyScalar(0.5),
        color,
        opacity: 1,
        startedAt: performance.now(),
        durationMs: 1200,
        demo,
        demoBadge: demo,
      });
    }
  }

  private _emitRefusalPattern(payload: Record<string, unknown>, resolve: PositionResolver): void {
    const entityId = (payload.target_entity_id ?? payload.action_id) as string | undefined;
    const center = entityId ? resolve(entityId) : null;
    const origin = center ?? new THREE.Vector3(0, 0, 0);
    const demo = Boolean(payload.demo);

    const directions = [
      new THREE.Vector3(1, 1, 0),
      new THREE.Vector3(-1, 1, 0),
      new THREE.Vector3(1, -1, 0),
      new THREE.Vector3(-1, -1, 0),
    ];
    for (const dir of directions) {
      this._spawn({
        behavior: "refusal_pattern",
        position: origin.clone(),
        velocity: dir.normalize().multiplyScalar(0.4),
        color: COLOR_REFUSAL.clone(),
        opacity: 1,
        startedAt: performance.now(),
        durationMs: 1000,
        demo,
        demoBadge: demo,
      });
    }
  }

  private _emitCorrectSignal(payload: Record<string, unknown>, resolve: PositionResolver): void {
    const entityId = (payload.target_entity_id ?? payload.action_id) as string | undefined;
    const altId = payload.suggested_alternative as string | undefined;
    const origin = entityId ? resolve(entityId) : null;
    const altPos = altId ? resolve(altId) : null;
    const demo = Boolean(payload.demo);

    const from = origin ?? new THREE.Vector3(0, 0, 0);

    if (altPos) {
      const count = 5;
      for (let i = 0; i < count; i++) {
        this._spawn({
          behavior: "correct_signal",
          position: from.clone(),
          velocity: altPos.clone().sub(from).normalize().multiplyScalar(0.7),
          color: COLOR_CORRECT.clone(),
          opacity: 1,
          startedAt: performance.now() + i * 80,
          durationMs: 1500,
          demo,
          demoBadge: demo,
        });
      }
    } else {
      const count = 4;
      for (let i = 0; i < count; i++) {
        const angle = (i / count) * Math.PI * 2;
        this._spawn({
          behavior: "correct_signal",
          position: from.clone(),
          velocity: new THREE.Vector3(Math.cos(angle), Math.sin(angle), 0).multiplyScalar(0.25),
          color: COLOR_CORRECT.clone(),
          opacity: 1,
          startedAt: performance.now(),
          durationMs: 1800,
          demo,
          demoBadge: demo,
        });
      }
    }
  }

  // ── Internal ───────────────────────────────────────────────────────

  private _spawn(particle: ActiveParticle): void {
    if (this.particles.length >= MAX_PARTICLES) {
      this.particles.shift();
    }
    this.particles.push(particle);
  }
}
