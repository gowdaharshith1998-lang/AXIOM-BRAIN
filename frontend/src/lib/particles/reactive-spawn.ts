import * as THREE from "three";

export type ParticleEffectKind = "entity-arrival" | "edge-trace" | "traversal-trail" | "signing-burst";

export type ParticleEffectParticle = {
  from: THREE.Vector3;
  to: THREE.Vector3;
  delayMs: number;
};

export type ParticleEffectDescriptor = {
  kind: ParticleEffectKind;
  color: string;
  durationMs: number;
  particleCount: number;
  particles: ParticleEffectParticle[];
};

export type ParticleEffectSink = {
  addEffect: (effect: ParticleEffectDescriptor) => void;
};

function colorHex(color: string | THREE.Color): string {
  return typeof color === "string" ? color : `#${color.getHexString().toUpperCase()}`;
}

function randomEnvelopePoint(): THREE.Vector3 {
  const theta = Math.random() * Math.PI * 2;
  const y = (Math.random() - 0.5) * 100;
  const r = 115 + Math.random() * 20;
  return new THREE.Vector3(Math.cos(theta) * r, y, Math.sin(theta) * r);
}

function jitteredTarget(target: THREE.Vector3, radius: number): THREE.Vector3 {
  return target
    .clone()
    .add(
      new THREE.Vector3(
        (Math.random() - 0.5) * radius,
        (Math.random() - 0.5) * radius,
        (Math.random() - 0.5) * radius,
      ),
    );
}

function emit(system: ParticleEffectSink | null | undefined, effect: ParticleEffectDescriptor): ParticleEffectDescriptor {
  system?.addEffect(effect);
  return effect;
}

export function spawnEntityArrival(
  system: ParticleEffectSink | null | undefined,
  targetPos: THREE.Vector3,
  color: string | THREE.Color,
): ParticleEffectDescriptor {
  const particleCount = 30;
  const particles = Array.from({ length: particleCount }, (_, i) => ({
    from: randomEnvelopePoint(),
    to: jitteredTarget(targetPos, 2.5),
    delayMs: i * 8,
  }));

  return emit(system, {
    kind: "entity-arrival",
    color: colorHex(color),
    durationMs: 600,
    particleCount,
    particles,
  });
}

export function spawnEdgeTrace(
  system: ParticleEffectSink | null | undefined,
  fromPos: THREE.Vector3,
  toPos: THREE.Vector3,
  color: string | THREE.Color,
): ParticleEffectDescriptor {
  const particleCount = 10;
  const direction = toPos.clone().sub(fromPos);
  const particles = Array.from({ length: particleCount }, (_, i) => {
    const startT = i / particleCount;
    const endT = Math.min(1, startT + 0.18);
    return {
      from: fromPos.clone().addScaledVector(direction, startT),
      to: fromPos.clone().addScaledVector(direction, endT),
      delayMs: i * 18,
    };
  });

  return emit(system, {
    kind: "edge-trace",
    color: colorHex(color),
    durationMs: 600,
    particleCount,
    particles,
  });
}
