import { describe, expect, it } from "vitest";

import { AegisParticleController } from "@/lib/aegis-particles";

describe("AegisParticleController", () => {
  it("spawns particles for actions", () => {
    const controller = new AegisParticleController();
    controller.spawn("act_1", "billing", 0);
    expect(controller.activeCount()).toBe(1);
    controller.dispose();
  });

  it("removes allowed particles after they dissolve", () => {
    const controller = new AegisParticleController();
    controller.spawn("act_1", "billing", 0);
    controller.evaluate("act_1", "allow");
    for (let t = 0; t < 5000; t += 100) controller.update(t);
    expect(controller.activeCount()).toBe(0);
    controller.dispose();
  });

  it("keeps denied particles active until fade completes", () => {
    const controller = new AegisParticleController();
    controller.spawn("act_2", "execution_context", 0);
    controller.evaluate("act_2", "deny");
    controller.update(100);
    expect(controller.activeCount()).toBe(1);
    controller.dispose();
  });
});
