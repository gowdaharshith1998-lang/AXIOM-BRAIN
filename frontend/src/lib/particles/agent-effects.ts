import * as THREE from "three";

import type { ParticleEffectDescriptor, ParticleEffectSink } from "@/lib/particles/reactive-spawn";

type RuntimeParticle = {
  from: THREE.Vector3;
  to: THREE.Vector3;
  color: THREE.Color;
  startMs: number;
  durationMs: number;
};

const MAX_PARTICLES = 2000;

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

function clampUnit(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function makeSigningBurst(pos: THREE.Vector3, color: string): ParticleEffectDescriptor {
  const particleCount = 40;
  const particles = Array.from({ length: particleCount }, (_, i) => {
    const theta = (i / particleCount) * Math.PI * 2;
    const phi = Math.acos(2 * ((i + 0.5) / particleCount) - 1);
    const dir = new THREE.Vector3(Math.sin(phi) * Math.cos(theta), Math.cos(phi), Math.sin(phi) * Math.sin(theta));
    return {
      from: pos.clone(),
      to: pos.clone().addScaledVector(dir, 18),
      delayMs: i * 5,
    };
  });

  return {
    kind: "signing-burst",
    color,
    durationMs: 800,
    particleCount,
    particles,
  };
}

export class ParticleEffectSystem implements ParticleEffectSink {
  readonly points: THREE.Points<THREE.BufferGeometry, THREE.ShaderMaterial>;

  private readonly positions = new Float32Array(MAX_PARTICLES * 3);
  private readonly colors = new Float32Array(MAX_PARTICLES * 3);
  private readonly alphas = new Float32Array(MAX_PARTICLES);
  private readonly geometry = new THREE.BufferGeometry();
  private readonly material = new THREE.ShaderMaterial({
    uniforms: { uSize: { value: 5 } },
    vertexShader: `
      attribute float alpha;
      varying float vAlpha;
      varying vec3 vColor;
      uniform float uSize;

      void main() {
        vAlpha = alpha;
        vColor = color;
        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
        gl_PointSize = uSize * (180.0 / -mvPosition.z);
        gl_Position = projectionMatrix * mvPosition;
      }
    `,
    fragmentShader: `
      varying float vAlpha;
      varying vec3 vColor;

      void main() {
        vec2 p = gl_PointCoord - vec2(0.5);
        float falloff = smoothstep(0.5, 0.0, length(p));
        gl_FragColor = vec4(vColor, vAlpha * falloff);
      }
    `,
    transparent: true,
    depthWrite: false,
    vertexColors: true,
    blending: THREE.AdditiveBlending,
  });
  private readonly active: RuntimeParticle[] = [];
  private multiplier = 1;

  constructor() {
    this.geometry.setAttribute("position", new THREE.BufferAttribute(this.positions, 3));
    this.geometry.setAttribute("color", new THREE.BufferAttribute(this.colors, 3));
    this.geometry.setAttribute("alpha", new THREE.BufferAttribute(this.alphas, 1));
    this.geometry.setDrawRange(0, 0);
    this.points = new THREE.Points(this.geometry, this.material);
    this.points.frustumCulled = false;
  }

  setParticleMultiplier(multiplier: number): void {
    this.multiplier = Math.max(0.1, Math.min(1, multiplier));
  }

  addEffect(effect: ParticleEffectDescriptor, nowMs = performance.now()): void {
    const color = new THREE.Color(effect.color);
    const keepEvery = Math.max(1, Math.round(1 / this.multiplier));
    effect.particles.forEach((particle, index) => {
      if (index % keepEvery !== 0) return;
      this.active.push({
        from: particle.from.clone(),
        to: particle.to.clone(),
        color: color.clone(),
        startMs: nowMs + particle.delayMs,
        durationMs: effect.durationMs,
      });
    });
    if (this.active.length > MAX_PARTICLES) {
      this.active.splice(0, this.active.length - MAX_PARTICLES);
    }
  }

  ingestStream(targetPos: THREE.Vector3, color: string): void {
    this.addEffect({
      kind: "entity-arrival",
      color,
      durationMs: 900,
      particleCount: 16,
      particles: Array.from({ length: 16 }, (_, i) => ({
        from: targetPos.clone().add(new THREE.Vector3(-35 - i * 0.7, Math.sin(i) * 8, Math.cos(i) * 8)),
        to: targetPos.clone(),
        delayMs: i * 22,
      })),
    });
  }

  traversalTrail(pathNodes: readonly THREE.Vector3[], color: string): void {
    for (let i = 0; i < pathNodes.length - 1; i++) {
      const from = pathNodes[i];
      const to = pathNodes[i + 1];
      this.addEffect({
        kind: "traversal-trail",
        color,
        durationMs: 700,
        particleCount: 8,
        particles: Array.from({ length: 8 }, (_, j) => ({
          from: from.clone().lerp(to, j / 8),
          to: from.clone().lerp(to, Math.min(1, j / 8 + 0.22)),
          delayMs: j * 20,
        })),
      });
    }
  }

  signingBurst(pos: THREE.Vector3, color: string): void {
    this.addEffect(makeSigningBurst(pos, color));
  }

  update(nowMs: number): void {
    let write = 0;
    for (let i = this.active.length - 1; i >= 0; i--) {
      const particle = this.active[i];
      const raw = (nowMs - particle.startMs) / particle.durationMs;
      if (raw >= 1) {
        this.active.splice(i, 1);
        continue;
      }
      if (raw < 0 || write >= MAX_PARTICLES) continue;

      const t = easeOutCubic(raw);
      const pos = particle.from.clone().lerp(particle.to, t);
      this.positions[write * 3] = pos.x;
      this.positions[write * 3 + 1] = pos.y;
      this.positions[write * 3 + 2] = pos.z;
      this.colors[write * 3] = clampUnit(particle.color.r);
      this.colors[write * 3 + 1] = clampUnit(particle.color.g);
      this.colors[write * 3 + 2] = clampUnit(particle.color.b);
      this.alphas[write] = Math.sin(raw * Math.PI) * 0.55;
      write++;
    }

    this.geometry.setDrawRange(0, write);
    for (const name of ["position", "color", "alpha"] as const) {
      const attr = this.geometry.getAttribute(name);
      if (attr) attr.needsUpdate = true;
    }
  }

  dispose(): void {
    this.geometry.dispose();
    this.material.dispose();
  }
}
