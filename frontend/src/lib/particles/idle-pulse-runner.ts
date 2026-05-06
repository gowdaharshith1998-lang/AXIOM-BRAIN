import * as THREE from "three";

import { breath, phaseOffsetFromId } from "@/lib/idle-pulse";

type PulsedMesh = THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial>;

export class IdlePulseRunner {
  private readonly phases = new Map<string, number>();
  private readonly baseIntensity = new Map<string, number>();

  update(meshes: ReadonlyMap<string, THREE.Mesh>, timeMs: number): void {
    for (const [id, mesh] of meshes) {
      const material = mesh.material;
      if (!(material instanceof THREE.MeshStandardMaterial)) continue;

      const pulsed = mesh as PulsedMesh;
      const phase = this.phaseFor(id);
      const base = this.baseFor(id, pulsed.material.emissiveIntensity);
      pulsed.material.emissiveIntensity = base * breath(timeMs, phase);
    }
  }

  private phaseFor(id: string): number {
    const existing = this.phases.get(id);
    if (existing !== undefined) return existing;
    const phase = phaseOffsetFromId(id);
    this.phases.set(id, phase);
    return phase;
  }

  private baseFor(id: string, intensity: number): number {
    const existing = this.baseIntensity.get(id);
    if (existing !== undefined) return existing;
    this.baseIntensity.set(id, intensity);
    return intensity;
  }
}
