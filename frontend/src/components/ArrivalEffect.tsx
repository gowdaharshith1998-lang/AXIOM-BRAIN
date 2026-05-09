import * as THREE from "three";

import { CLUSTER_COLORS, isClusterId } from "@/lib/cluster-layout";

export const ARRIVAL_EFFECT_MS = 1000;
export const ARRIVAL_PULSE_MS = 600;
export const ARRIVAL_PARTICLE_MS = 800;

export type ArrivalParticle = {
  position: THREE.Vector3;
  opacity: number;
};

export function arrivalColorForCluster(clusterId?: string | null): string {
  return isClusterId(clusterId) ? CLUSTER_COLORS[clusterId] : "#E8F0FF";
}

export function arrivalPulseState(ageMs: number): { radius: number; opacity: number; alive: boolean } {
  const t = Math.min(1, Math.max(0, ageMs / ARRIVAL_PULSE_MS));
  const eased = 1 - (1 - t) * (1 - t);
  return {
    radius: 2 + (12 - 2) * eased,
    opacity: 1 - eased,
    alive: ageMs <= ARRIVAL_EFFECT_MS,
  };
}

export function arrivalSpiralParticles(ageMs: number, origin: THREE.Vector3): ArrivalParticle[] {
  const t = Math.min(1, Math.max(0, ageMs / ARRIVAL_PARTICLE_MS));
  const radius = 4 + (14 - 4) * t;
  return Array.from({ length: 8 }, (_, i) => {
    const angle = i * ((Math.PI * 2) / 8) + t * Math.PI * 2;
    return {
      position: origin.clone().add(new THREE.Vector3(Math.cos(angle) * radius, (i - 3.5) * 0.3, Math.sin(angle) * radius)),
      opacity: 1 - t,
    };
  });
}
