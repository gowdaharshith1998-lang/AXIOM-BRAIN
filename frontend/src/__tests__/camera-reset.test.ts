import { describe, expect, it } from "vitest";

import { RESET_CAMERA_MS, easeInOutCubic, shouldResetCameraFromKey } from "@/lib/camera-reset";

describe("camera reset key", () => {
  it("R key triggers reset camera", () => {
    expect(shouldResetCameraFromKey("R", false)).toBe(true);
  });

  it("R key is ignored when palette is open", () => {
    expect(shouldResetCameraFromKey("r", true)).toBe(false);
  });

  it("reset camera animates over eight hundred ms", () => {
    expect(RESET_CAMERA_MS).toBe(800);
    expect(easeInOutCubic(0)).toBe(0);
    expect(easeInOutCubic(1)).toBe(1);
  });
});
