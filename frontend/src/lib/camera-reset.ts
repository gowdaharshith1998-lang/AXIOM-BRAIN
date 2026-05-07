export const RESET_CAMERA_MS = 800;

export function shouldResetCameraFromKey(key: string, paletteOpen: boolean): boolean {
  return !paletteOpen && key.toLowerCase() === "r";
}

export function easeInOutCubic(t: number): number {
  const clamped = Math.min(1, Math.max(0, t));
  return clamped < 0.5 ? 4 * clamped * clamped * clamped : 1 - Math.pow(-2 * clamped + 2, 3) / 2;
}
