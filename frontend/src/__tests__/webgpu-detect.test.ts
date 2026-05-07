import { describe, expect, it } from "vitest";

import { hasWebGPU } from "@/lib/webgpu-detect";

describe("webgpu-detect", () => {
  it("returns false when navigator.gpu is undefined", () => {
    const nav = navigator as unknown as { gpu?: unknown };
    const prev = nav.gpu;
    // eslint-disable-next-line @typescript-eslint/no-dynamic-delete
    delete nav.gpu;
    expect(hasWebGPU()).toBe(false);
    nav.gpu = prev;
  });
});

