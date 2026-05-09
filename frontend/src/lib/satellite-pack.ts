import * as THREE from "three";

export type SatelliteRing = 0 | 1 | 2;

export type SatellitePosition = {
  position: THREE.Vector3;
  ring: SatelliteRing;
  hexRadius: number;
};

export type PackSatellitesInput = {
  centroid: THREE.Vector3;
  count: number;
  clusterRadius: number;
  seed: number;
  baseHexRadius: number;
};

function mulberry32(seed: number): () => number {
  let t = seed >>> 0;
  return () => {
    t += 0x6d2b79f5;
    let x = t;
    x = Math.imul(x ^ (x >>> 15), x | 1);
    x ^= x + Math.imul(x ^ (x >>> 7), x | 61);
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

function fibonacciSpherePoints(n: number): THREE.Vector3[] {
  const points: THREE.Vector3[] = [];
  if (n <= 0) return points;
  if (n === 1) return [new THREE.Vector3(1, 0, 0)];
  const phi = Math.PI * (Math.sqrt(5) - 1); // golden angle
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2;
    const radiusAtY = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = phi * i;
    const x = Math.cos(theta) * radiusAtY;
    const z = Math.sin(theta) * radiusAtY;
    points.push(new THREE.Vector3(x, y, z));
  }
  return points;
}

function jitterRadially(v: THREE.Vector3, amount: number, rand: () => number): THREE.Vector3 {
  const direction = v.lengthSq() === 0 ? new THREE.Vector3(1, 0, 0) : v.clone().normalize();
  const delta = (rand() * 2 - 1) * amount;
  return direction.multiplyScalar(delta);
}

export function packSatellites(input: PackSatellitesInput): SatellitePosition[] {
  const { centroid, count, clusterRadius, seed, baseHexRadius } = input;
  if (count <= 0) return [];

  const rand = mulberry32(seed);
  const jitterFrac = 0.075;

  const innerCount = Math.min(count, 8);
  const remainingAfterInner = count - innerCount;
  const midCount = Math.min(remainingAfterInner, 16);
  const outerCount = Math.max(0, count - innerCount - midCount);

  const shells: Array<{
    ring: SatelliteRing;
    n: number;
    shellRadius: number;
    radiusScale: number;
  }> = [
    { ring: 0, n: innerCount, shellRadius: clusterRadius * 0.3, radiusScale: 1.4 },
    { ring: 1, n: midCount, shellRadius: clusterRadius * 0.65, radiusScale: 1.0 },
    { ring: 2, n: outerCount, shellRadius: clusterRadius * 1.0, radiusScale: 0.7 },
  ];

  const out: SatellitePosition[] = [];
  for (const shell of shells) {
    const { ring, n, shellRadius, radiusScale } = shell;
    if (n <= 0) continue;
    const points = fibonacciSpherePoints(n);
    for (const p of points) {
      const base = p.clone().multiplyScalar(shellRadius);
      const jitter = jitterRadially(base, shellRadius * jitterFrac, rand);
      out.push({
        ring,
        hexRadius: baseHexRadius * radiusScale,
        position: centroid.clone().add(base).add(jitter),
      });
    }
  }

  return out.slice(0, count);
}
