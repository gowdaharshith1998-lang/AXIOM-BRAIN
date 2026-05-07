export class RollingFpsCounter {
  private readonly windowSize: number;
  private times: number[] = [];

  constructor(windowSize = 60) {
    this.windowSize = windowSize;
  }

  tick(nowMs: number): number {
    this.times.push(nowMs);
    while (this.times.length > this.windowSize) this.times.shift();

    if (this.times.length < this.windowSize) return 0;
    const elapsedSec = (this.times[this.times.length - 1] - this.times[0]) / 1000;
    if (elapsedSec <= 0) return 0;
    return Math.round((this.windowSize - 1) / elapsedSec);
  }
}

