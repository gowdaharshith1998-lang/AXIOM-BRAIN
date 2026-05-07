export type FpsGuardState = "full" | "half" | "emergency";

const FULL_THRESHOLD = 55;
const HALF_THRESHOLD = 40;
const NODE_BUDGET_THRESHOLD = 45;
const NODE_BUDGET_SUSTAINED_MS = 3000;
export const FPS_NODE_BUDGETS = [80, 56, 40, 26] as const;

export class FpsGuard {
  private readonly samples: number[] = [];
  private readonly maxSamples: number;
  private warned = false;
  private currentState: FpsGuardState = "full";
  private budgetIndex = 0;
  private belowBudgetSinceMs: number | null = null;
  private readonly budgetCallbacks = new Set<(maxPerCluster: number) => void>();

  constructor(maxSamples = 90) {
    this.maxSamples = maxSamples;
  }

  sample(fps: number, nowMs: number): FpsGuardState {
    this.samples.push(fps);
    if (this.samples.length > this.maxSamples) this.samples.shift();

    const avg = this.averageFps();
    this.updateNodeBudget(avg, nowMs);
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

  nodeBudget(): number {
    return FPS_NODE_BUDGETS[this.budgetIndex];
  }

  onBudgetChange(callback: (maxPerCluster: number) => void): () => void {
    this.budgetCallbacks.add(callback);
    return () => this.budgetCallbacks.delete(callback);
  }

  private averageFps(): number {
    if (this.samples.length === 0) return 60;
    return this.samples.reduce((sum, fps) => sum + fps, 0) / this.samples.length;
  }

  private updateNodeBudget(avgFps: number, nowMs: number): void {
    if (avgFps >= NODE_BUDGET_THRESHOLD) {
      this.belowBudgetSinceMs = null;
      return;
    }

    this.belowBudgetSinceMs ??= nowMs;
    if (nowMs - this.belowBudgetSinceMs < NODE_BUDGET_SUSTAINED_MS) return;
    if (this.budgetIndex >= FPS_NODE_BUDGETS.length - 1) return;

    this.budgetIndex += 1;
    this.belowBudgetSinceMs = nowMs;
    const nextBudget = this.nodeBudget();
    for (const callback of this.budgetCallbacks) callback(nextBudget);
  }
}
