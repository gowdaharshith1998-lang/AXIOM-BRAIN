import { describe, expect, it } from "vitest";

import type { Entity } from "@/state/brain.store";
import { superClusterIdForEntity } from "@/lib/cluster-reframe";

function entity(overrides: Partial<Entity> & Pick<Entity, "id">): Entity {
  return {
    type: "unknown",
    data: {},
    source_id: null,
    created_at: "",
    updated_at: "",
    ...overrides,
  };
}

describe("superClusterIdForEntity", () => {
  it("maps backend cluster_id values to super-clusters", () => {
    expect(superClusterIdForEntity(entity({ id: "1", cluster_id: "knowledge" }))).toBe("policies");
    expect(superClusterIdForEntity(entity({ id: "2", cluster_id: "comms" }))).toBe("company_knowledge");
    expect(superClusterIdForEntity(entity({ id: "3", cluster_id: "engineering_code" }))).toBe(
      "execution_context",
    );
    expect(superClusterIdForEntity(entity({ id: "4", cluster_id: "people" }))).toBe("people_teams");
    expect(superClusterIdForEntity(entity({ id: "5", cluster_id: "customers" }))).toBe("customers");
  });

  it("maps entity type customer to customers super-cluster", () => {
    expect(superClusterIdForEntity(entity({ id: "6", type: "customer" }))).toBe("customers");
  });

  it("falls back to company_knowledge for unknown cluster_id and type", () => {
    expect(
      superClusterIdForEntity(entity({ id: "7", cluster_id: "totally_unknown", type: "unknown" })),
    ).toBe("company_knowledge");
  });
});
