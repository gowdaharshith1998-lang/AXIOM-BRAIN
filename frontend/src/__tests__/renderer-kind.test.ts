import { describe, expect, it } from "vitest";

import { preferredRendererKind } from "@/lib/webgpu-detect";

describe("preferredRendererKind", () => {
  it("selects webgpu only when both browser + three support it", () => {
    expect(
      preferredRendererKind({ navigatorHasWebGpu: true, threeHasWebGpuRenderer: true }),
    ).toBe("webgpu");
    expect(
      preferredRendererKind({ navigatorHasWebGpu: false, threeHasWebGpuRenderer: true }),
    ).toBe("webgl");
    expect(
      preferredRendererKind({ navigatorHasWebGpu: true, threeHasWebGpuRenderer: false }),
    ).toBe("webgl");
  });
});

