import * as THREE from "three";

const MIN_OPACITY = 0.1;
const MAX_OPACITY = 0.22;

function hashToUnit(id: string, salt: number): number {
  let hash = 2166136261 ^ salt;
  for (let i = 0; i < id.length; i++) {
    hash ^= id.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) / 4294967296;
}

export function shimmerOpacity(edgeId: string, timeMs: number): number {
  const t = timeMs / 1000;
  const p1 = hashToUnit(edgeId, 11) * Math.PI * 2;
  const p2 = hashToUnit(edgeId, 17) * Math.PI * 2;
  const p3 = hashToUnit(edgeId, 23) * Math.PI * 2;
  const fbm =
    Math.sin(t * 0.7 + p1) * 0.5 +
    Math.sin(t * 1.3 + p2) * 0.3 +
    Math.sin(t * 2.1 + p3) * 0.2;
  const normalized = (fbm + 1) / 2;
  return MIN_OPACITY + normalized * (MAX_OPACITY - MIN_OPACITY);
}

export function createEdgeShimmerMaterial(): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    uniforms: {},
    vertexShader: `
      attribute float edgeAlpha;
      varying float vAlpha;
      varying vec3 vColor;

      void main() {
        vAlpha = edgeAlpha;
        vColor = color;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      varying float vAlpha;
      varying vec3 vColor;

      void main() {
        gl_FragColor = vec4(vColor, vAlpha);
      }
    `,
    transparent: true,
    depthWrite: false,
    vertexColors: true,
    blending: THREE.AdditiveBlending,
  });
}

export class EdgeShimmer {
  private readonly alphaAttr: THREE.BufferAttribute;

  constructor(
    private readonly edgeIds: readonly string[],
    geometry: THREE.BufferGeometry,
  ) {
    const alphas = new Float32Array(edgeIds.length * 2);
    this.alphaAttr = new THREE.BufferAttribute(alphas, 1);
    geometry.setAttribute("edgeAlpha", this.alphaAttr);
  }

  update(timeMs: number): void {
    const arr = this.alphaAttr.array as Float32Array;
    for (let i = 0; i < this.edgeIds.length; i++) {
      const alpha = shimmerOpacity(this.edgeIds[i], timeMs);
      arr[i * 2] = alpha;
      arr[i * 2 + 1] = alpha;
    }
    this.alphaAttr.needsUpdate = true;
  }
}
