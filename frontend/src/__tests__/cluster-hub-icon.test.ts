import { describe, expect, it } from "vitest";

import { createClusterHubIconSprite, iconTextForCluster } from "@/components/ClusterHubIcon";

describe("ClusterHubIcon", () => {
  it("maps service identity icons to each cluster", () => {
    expect(iconTextForCluster("billing_payments")).toBe("$");
    expect(iconTextForCluster("incidents_ops")).toBe("!");
    expect(iconTextForCluster("engineering_code")).toBe("{}");
  });

  it("creates a four world unit icon sprite", () => {
    const sprite = createClusterHubIconSprite("customer_support");
    expect(sprite.scale.x).toBe(4);
    expect(sprite.userData.kind).toBe("cluster-hub-icon");
  });

  it("maps growth to an ASCII trend label", () => {
    expect(iconTextForCluster("growth_product")).toBe("UP");
  });
});
