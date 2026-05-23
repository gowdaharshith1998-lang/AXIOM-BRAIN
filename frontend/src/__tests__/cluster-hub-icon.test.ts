import { describe, expect, it } from "vitest";

import { createClusterHubIconSprite, iconTextForCluster } from "@/components/ClusterHubIcon";

describe("ClusterHubIcon", () => {
  it("maps service identity icons to each cluster", () => {
    expect(iconTextForCluster("billing")).toBe("$");
    expect(iconTextForCluster("execution_context")).toBe("EX");
    expect(iconTextForCluster("company_knowledge")).toBe("CK");
  });

  it("creates a four world unit icon sprite", () => {
    const sprite = createClusterHubIconSprite("customers");
    expect(sprite.scale.x).toBe(4);
    expect(sprite.userData.kind).toBe("cluster-hub-icon");
  });

  // HIDDEN-V2: asserts governance UI removed for YC company-brain positioning. unskip when re-surfacing.
  it.skip("[HIDDEN-V2] maps growth to an ASCII trend label", () => {
    expect(iconTextForCluster("governance")).toBe("GV");
  });
});
