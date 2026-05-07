import * as THREE from "three";

export class OrbitalHalo {
  readonly points: THREE.Points<THREE.BufferGeometry, THREE.PointsMaterial>;

  private readonly positions = new Float32Array(4 * 3);
  private readonly geometry = new THREE.BufferGeometry();
  private readonly material: THREE.PointsMaterial;
  private center = new THREE.Vector3();
  private radius = 5;

  constructor(color: string | THREE.Color) {
    this.geometry.setAttribute("position", new THREE.BufferAttribute(this.positions, 3));
    this.material = new THREE.PointsMaterial({
      color,
      size: 3,
      sizeAttenuation: true,
      transparent: true,
      opacity: 0.4,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    this.points = new THREE.Points(this.geometry, this.material);
    this.points.frustumCulled = false;
  }

  setTarget(center: THREE.Vector3, radius: number, color: string | THREE.Color): void {
    this.center = center.clone();
    this.radius = radius;
    this.material.color.set(color);
  }

  update(timeMs: number): void {
    const angle = ((timeMs % 1500) / 1500) * Math.PI * 2;
    for (let i = 0; i < 4; i++) {
      const a = angle + (i / 4) * Math.PI * 2;
      this.positions[i * 3] = this.center.x + Math.cos(a) * this.radius;
      this.positions[i * 3 + 1] = this.center.y + Math.sin(a * 2) * this.radius * 0.18;
      this.positions[i * 3 + 2] = this.center.z + Math.sin(a) * this.radius;
    }
    const attr = this.geometry.getAttribute("position");
    if (attr) attr.needsUpdate = true;
  }

  dispose(): void {
    this.geometry.dispose();
    this.material.dispose();
  }
}
