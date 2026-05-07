export type FpsGuardState = "full" | "half" | "emergency";

const FULL_THRESHOLD = 55;
const HALF_THRESHOLD = 40;

export class FpsGuard {
  private readonly samples: number[] = [];
  private readonly maxSamples: number;
  private warned = false;
  private currentState: FpsGuardState = "full";

  constructor(maxSamples = 90) {
    this.maxSamples = maxSamples;
  }

  sample(fps: number, _nowMs: number): FpsGuardState {
    this.samples.push(fps);
    if (this.samples.length > this.maxSamples) this.samples.shift();

    const avg = this.averageFps();
    if (fps < HALF_THRESHOLD || avg < HALF_THRESHOLD) {
      if (!this.warned) {
        // eslint-disable-next-line no-console
        console.warn("[Brain] FPS guard entered emergency particle culling.");
        this.warned = true;
      }
      this.currentState = "emergency";
      return this.currentState;
    }

    if (avg >= FULL_THRESHOLD) {
      this.warned = false;
      this.currentState = "full";
      return this.currentState;
    }

    if (avg >= HALF_THRESHOLD) {
      this.warned = false;
      this.currentState = "half";
      return this.currentState;
    }

    this.currentState = "half";
    return this.currentState;
  }

  state(): FpsGuardState {
    return this.currentState;
  }

  particleMultiplier(): number {
    if (this.currentState === "emergency") return 0;
    if (this.currentState === "half") return 0.5;
    return 1;
  }

  private averageFps(): number {
    if (this.samples.length === 0) return 60;
    return this.samples.reduce((sum, fps) => sum + fps, 0) / this.samples.length;
  }
}
