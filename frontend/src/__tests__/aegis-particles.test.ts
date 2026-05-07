import { describe, expect, it } from "vitest";

import { AegisParticleController } from "@/lib/aegis-particles";

describe("AegisParticleController", () => {
  it("spawns particles for actions", () => {
    const controller = new AegisParticleController();
    controller.spawn("act_1", "billing_payments", 0);
    expect(controller.activeCount()).toBe(1);
    controller.dispose();
  });

  it("removes allowed particles after they dissolve", () => {
    const controller = new AegisParticleController();
    controller.spawn("act_1", "billing_payments", 0);
    controller.evaluate("act_1", "allow");
    for (let t = 0; t < 5000; t += 100) controller.update(t);
    expect(controller.activeCount()).toBe(0);
    controller.dispose();
  });
});
