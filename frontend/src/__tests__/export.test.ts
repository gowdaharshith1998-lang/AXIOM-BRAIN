import { describe, expect, it, vi } from "vitest";

import { exportVisibleAsJson, visibleExportData } from "@/lib/export";
import type { Entity } from "@/state/brain.store";

function entity(id: string, cluster_id: string, composite_importance: number): Entity {
  return {
    id,
    type: "thread",
    data: {},
    source_id: null,
    created_at: "t",
    updated_at: "t",
    cluster_id,
    composite_importance,
  };
}

describe("visibleExportData", () => {
  it("includes visible entities and cluster metadata", () => {
    const state = {
      entities: new Map(Array.from({ length: 30 }, (_, i) => [`e${i}`, entity(`e${i}`, "billing_payments", 1 - i / 100)])),
      edges: new Map([["edge", { id: "edge", source_id: "e0", target_id: "e1", relationship: "mentions", data: {}, created_at: "t" }]]),
    };
    const data = visibleExportData(state);
    expect(data.version).toBe("0.1");
    expect(data.entities).toHaveLength(26);
    expect(data.edges).toHaveLength(1);
    expect(data.clusters).toHaveLength(7);
  });

  it("downloads json through a Blob URL", () => {
    Object.defineProperty(URL, "createObjectURL", { value: vi.fn(), configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: vi.fn(), configurable: true });
    const create = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:axiom");
    const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    exportVisibleAsJson({ entities: new Map(), edges: new Map() });
    expect(create).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
    expect(revoke).toHaveBeenCalledWith("blob:axiom");
    create.mockRestore();
    revoke.mockRestore();
    click.mockRestore();
  });

  it("reports full cluster counts even when visible entities are capped", () => {
    const state = {
      entities: new Map(Array.from({ length: 30 }, (_, i) => [`e${i}`, entity(`e${i}`, "billing_payments", 1 - i / 100)])),
      edges: new Map(),
    };
    const data = visibleExportData(state);
    expect(data.clusters.find((cluster) => cluster.id === "billing_payments")?.count).toBe(30);
  });
});
