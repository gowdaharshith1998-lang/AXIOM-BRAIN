export type FpsGuardState = "full" | "half" | "emergency";

const FULL_THRESHOLD = 58;
const HALF_THRESHOLD = 50;
const EMERGENCY_AFTER_MS = 5000;

export class FpsGuard {
  private readonly samples: number[] = [];
  private readonly maxSamples: number;
  private belowThresholdSince: number | null = null;
  private warned = false;
  private currentState: FpsGuardState = "full";

  constructor(maxSamples = 90) {
    this.maxSamples = maxSamples;
  }

  sample(fps: number, nowMs: number): FpsGuardState {
    this.samples.push(fps);
    if (this.samples.length > this.maxSamples) this.samples.shift();

    const avg = this.averageFps();
    if (avg >= FULL_THRESHOLD) {
      this.belowThresholdSince = null;
      this.warned = false;
      this.currentState = "full";
      return this.currentState;
    }

    if (avg >= HALF_THRESHOLD) {
      this.belowThresholdSince = null;
      this.warned = false;
      this.currentState = "half";
      return this.currentState;
    }

    this.belowThresholdSince ??= nowMs;
    if (nowMs - this.belowThresholdSince >= EMERGENCY_AFTER_MS) {
      if (!this.warned) {
        // eslint-disable-next-line no-console
        console.warn("[Brain] FPS guard entered emergency particle culling.");
        this.warned = true;
      }
      this.currentState = "emergency";
      return this.currentState;
    }

    this.currentState = "half";
    return this.currentState;
  }

  state(): FpsGuardState {
    return this.currentState;
  }

  particleMultiplier(): number {
    if (this.currentState === "emergency") return 0.25;
    if (this.currentState === "half") return 0.5;
    return 1;
  }

  private averageFps(): number {
    if (this.samples.length === 0) return 60;
    return this.samples.reduce((sum, fps) => sum + fps, 0) / this.samples.length;
  }
}
