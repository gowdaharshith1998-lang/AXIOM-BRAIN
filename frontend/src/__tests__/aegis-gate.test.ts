import { describe, expect, it } from "vitest";

import { AegisGate, createAegisRing } from "@/lib/aegis-gate";

describe("AegisGate", () => {
  it("starts idle with low opacity", () => {
    const gate = new AegisGate("billing", createAegisRing("billing"));
    expect(gate.currentState()).toBe("idle");
    expect(gate.ring.material.opacity).toBeCloseTo(0.35);
  });

  it("flashes allow and returns to idle", () => {
    const gate = new AegisGate("billing", createAegisRing("billing"));
    gate.setState("allow", 0);
    expect(gate.currentState()).toBe("allow");
    gate.update(700);
    expect(gate.currentState()).toBe("idle");
  });

  it("uses red for deny state", () => {
    const gate = new AegisGate("billing", createAegisRing("billing"));
    gate.setState("deny", 0);
    expect(`#${gate.ring.material.color.getHexString()}`).toBe("#ef4444");
  });
});
