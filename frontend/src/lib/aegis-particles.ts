import * as THREE from "three";

import { CLUSTER_CENTROIDS, type ClusterId } from "@/lib/cluster-layout";

export type AegisParticleDecision = "allow" | "deny";

type ParticleState = "travelling" | "evaluating" | "allowed" | "denied" | "done";

export type AegisParticle = {
  actionId: string;
  cluster: ClusterId;
  position: THREE.Vector3;
  startedAt: number;
  state: ParticleState;
  decision?: AegisParticleDecision;
  sprite: THREE.Sprite;
};

export class AegisParticleController {
  readonly group = new THREE.Group();
  private readonly particles = new Map<string, AegisParticle>();

  spawn(actionId: string, cluster: ClusterId, nowMs: number): AegisParticle {
    const sprite = new THREE.Sprite(
      new THREE.SpriteMaterial({
        color: "#ffffff",
        transparent: true,
        opacity: 0.95,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    );
    sprite.scale.set(2.2, 2.2, 1);
    const particle: AegisParticle = {
      actionId,
      cluster,
      position: new THREE.Vector3(0, 0, 30),
      startedAt: nowMs,
      state: "travelling",
      sprite,
    };
    sprite.position.copy(particle.position);
    this.particles.set(actionId, particle);
    this.group.add(sprite);
    return particle;
  }

  evaluate(actionId: string, decision: AegisParticleDecision): void {
    const particle = this.particles.get(actionId);
    if (!particle) return;
    particle.decision = decision;
    particle.state = decision === "allow" ? "allowed" : "denied";
  }

  update(nowMs: number): void {
    for (const particle of this.particles.values()) {
      const target = CLUSTER_CENTROIDS[particle.cluster];
      const gatePoint = target.clone().lerp(new THREE.Vector3(0, 0, 30), 14 / Math.max(14, target.length()));
      if (particle.state === "travelling") {
        const t = Math.min(1, (nowMs - particle.startedAt) / 900);
        particle.position.lerpVectors(new THREE.Vector3(0, 0, 30), gatePoint, t);
        if (t >= 1) particle.state = "evaluating";
      } else if (particle.state === "allowed") {
        particle.position.lerp(target, 0.18);
        particle.sprite.material.opacity *= 0.94;
        if (particle.position.distanceTo(target) < 1 || particle.sprite.material.opacity < 0.05) particle.state = "done";
      } else if (particle.state === "denied") {
        particle.position.lerp(new THREE.Vector3(0, 0, 44), 0.16);
        particle.sprite.material.opacity *= 0.93;
        if (particle.sprite.material.opacity < 0.05) particle.state = "done";
      }
      particle.sprite.position.copy(particle.position);
    }
    for (const [id, particle] of this.particles) {
      if (particle.state !== "done") continue;
      this.group.remove(particle.sprite);
      particle.sprite.material.dispose();
      this.particles.delete(id);
    }
  }

  activeCount(): number {
    return this.particles.size;
  }

  dispose(): void {
    for (const particle of this.particles.values()) particle.sprite.material.dispose();
    this.particles.clear();
  }
}
