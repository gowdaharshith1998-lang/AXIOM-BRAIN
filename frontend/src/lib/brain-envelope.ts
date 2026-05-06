const ELLIPSOID = { rx: 80, ry: 50, rz: 60 };

function idToFloat(id: string, salt: number): number {
  let h = 2166136261 ^ salt;
  for (let i = 0; i < id.length; i++) {
    h ^= id.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0) / 4294967296;
}

export function envelopePosition(id: string): [number, number, number] {
  const u = idToFloat(id, 1);
  const v = idToFloat(id, 2);
  const r = Math.cbrt(idToFloat(id, 3));

  const theta = 2 * Math.PI * u;
  const phi = Math.acos(2 * v - 1);

  const sx = r * Math.sin(phi) * Math.cos(theta);
  const sy = r * Math.sin(phi) * Math.sin(theta);
  const sz = r * Math.cos(phi);

  const noise = (idToFloat(id, 4) - 0.5) * 0.15;

  return [
    sx * ELLIPSOID.rx * (1 + noise),
    sy * ELLIPSOID.ry * (1 + noise),
    sz * ELLIPSOID.rz * (1 + noise),
  ];
}

