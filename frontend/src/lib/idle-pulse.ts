const BREATH_FREQUENCY_HZ = 0.3;
const BREATH_AMPLITUDE = 0.07;
const FNV_OFFSET = 2166136261;
const FNV_PRIME = 16777619;

export function breath(timeMs: number, phaseOffset = 0): number {
  const radians = 2 * Math.PI * BREATH_FREQUENCY_HZ * (timeMs / 1000) + phaseOffset;
  return 1 + Math.sin(radians) * BREATH_AMPLITUDE;
}

export function phaseOffsetFromId(id: string): number {
  let hash = FNV_OFFSET;
  for (let i = 0; i < id.length; i++) {
    hash ^= id.charCodeAt(i);
    hash = Math.imul(hash, FNV_PRIME);
  }
  return ((hash >>> 0) / 4294967296) * 2 * Math.PI;
}
