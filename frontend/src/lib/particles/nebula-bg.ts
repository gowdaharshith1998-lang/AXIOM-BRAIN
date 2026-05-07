import * as THREE from "three";

export type NebulaBackground = {
  mesh: THREE.Mesh<THREE.SphereGeometry, THREE.ShaderMaterial>;
  update: (timeMs: number) => void;
  dispose: () => void;
};

export function createNebulaBackground(radius = 900): NebulaBackground {
  const geometry = new THREE.SphereGeometry(radius, 32, 16);
  const material = new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 },
      uCenter: { value: new THREE.Color("#0a0a14") },
      uOuter: { value: new THREE.Color("#14143a") },
    },
    vertexShader: `
      varying vec3 vWorld;

      void main() {
        vec4 world = modelMatrix * vec4(position, 1.0);
        vWorld = normalize(world.xyz);
        gl_Position = projectionMatrix * viewMatrix * world;
      }
    `,
    fragmentShader: `
      uniform float uTime;
      uniform vec3 uCenter;
      uniform vec3 uOuter;
      varying vec3 vWorld;

      void main() {
        float drift = sin(vWorld.x * 4.0 + uTime * 0.05) * 0.04
          + cos(vWorld.y * 3.0 - uTime * 0.035) * 0.04;
        float radial = smoothstep(-0.2, 0.85, abs(vWorld.y) + drift);
        vec3 color = mix(uCenter, uOuter, radial * 0.75);
        gl_FragColor = vec4(color, 1.0);
      }
    `,
    side: THREE.BackSide,
    depthWrite: false,
    depthTest: false,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.renderOrder = -1000;
  mesh.frustumCulled = false;

  return {
    mesh,
    update: (timeMs: number) => {
      material.uniforms.uTime.value = timeMs / 1000;
    },
    dispose: () => {
      geometry.dispose();
      material.dispose();
    },
  };
}
