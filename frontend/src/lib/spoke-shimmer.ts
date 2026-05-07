export function hashStringToFloat(value: string): number {
  let h = 2166136261;
  for (let i = 0; i < value.length; i++) {
    h ^= value.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return (h % 10000) / 10000;
}

export function shimmerScale(seed: number, timeMs: number): number {
  const amplitude = 0.082 + 0.04 * Math.sin(seed * 12.9898 + 78.233);
  const frequency = 0.0008 + 0.0006 * (1 + Math.sin(seed * 4.7));
  return 1 + amplitude * Math.sin(timeMs * frequency + seed);
}

export function shimmerEmissiveMultiplier(seed: number, timeMs: number): number {
  return 1 + 0.18 * Math.sin(timeMs * 0.0011 + seed * 1.7);
}

export function hubEmissiveIntensityAt(baseIntensity: number, clusterIndex: number, timeMs: number): number {
  const phase = clusterIndex * 1.3;
  const period = 4000 + clusterIndex * 400;
  return baseIntensity * (1 + 0.3 * Math.sin(2 * Math.PI * (timeMs / period) + phase));
}
