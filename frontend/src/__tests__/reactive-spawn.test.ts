import * as THREE from "three";
import { describe, expect, it } from "vitest";

import type { ParticleEffectDescriptor, ParticleEffectSink } from "@/lib/particles/reactive-spawn";
import { spawnEdgeTrace, spawnEntityArrival } from "@/lib/particles/reactive-spawn";

describe("reactive-spawn", () => {
  it("creates entity arrival swirl config", () => {
    const received: ParticleEffectDescriptor[] = [];
    const sink: ParticleEffectSink = { addEffect: (effect) => received.push(effect) };
    const effect = spawnEntityArrival(sink, new THREE.Vector3(1, 2, 3), "#8BE9FD");

    expect(effect.kind).toBe("entity-arrival");
    expect(effect.durationMs).toBe(600);
    expect(effect.particleCount).toBe(30);
    expect(effect.particles).toHaveLength(30);
    expect(received[0]).toBe(effect);
  });

  it("creates edge trace config along the requested segment", () => {
    const from = new THREE.Vector3(0, 0, 0);
    const to = new THREE.Vector3(10, 0, 0);
    const effect = spawnEdgeTrace(null, from, to, "#FFFFFF");

    expect(effect.kind).toBe("edge-trace");
    expect(effect.durationMs).toBe(600);
    expect(effect.particleCount).toBe(10);
    expect(effect.particles).toHaveLength(10);
    expect(effect.particles[0].from.x).toBe(0);
    expect(effect.particles[effect.particles.length - 1].to.x).toBeGreaterThan(9);
  });
});
