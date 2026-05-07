import { describe, expect, it } from "vitest";

import { displayLabelFor, shouldShowLabel, truncate } from "@/lib/labels";
import type { Entity } from "@/state/brain.store";

function entity(id: string, type: string, data: Record<string, unknown>): Entity {
  return {
    id,
    type,
    data,
    source_id: null,
    created_at: "2026-05-06T00:00:00Z",
    updated_at: "2026-05-06T00:00:00Z",
  };
}

describe("displayLabelFor", () => {
  it("returns ticket titles", () => {
    expect(displayLabelFor(entity("ticket123", "ticket", { title: "DB migration fails" }))).toBe("DB migration fails");
  });

  it("returns thread titles", () => {
    expect(displayLabelFor(entity("thread123", "thread", { title: "Incident follow-up: webhook latency" }))).toBe(
      "Incident follow-up: web…",
    );
  });

  it("returns document titles", () => {
    expect(displayLabelFor(entity("doc12345", "document", { title: "Runbook" }))).toBe("Runbook");
  });

  it("returns decision titles", () => {
    expect(displayLabelFor(entity("dec12345", "decision", { title: "Use Neon for storage" }))).toBe(
      "Use Neon for storage",
    );
  });

  it("returns process names", () => {
    expect(displayLabelFor(entity("proc123", "process", { name: "Incident response" }))).toBe("Incident response");
  });

  it("returns code basenames", () => {
    expect(displayLabelFor(entity("code123", "code", { file_path: "scripts/generate_fixture.py" }))).toBe(
      "generate_fixture.py",
    );
  });

  it("returns people names", () => {
    expect(displayLabelFor(entity("person12", "people", { name: "Ada Lovelace" }))).toBe("Ada Lovelace");
  });

  it("falls back to id[:8] when the preferred field is missing", () => {
    expect(displayLabelFor(entity("abc12345xyz", "ticket", {}))).toBe("abc12345");
  });

  it("falls back to id[:8] when the preferred field is empty", () => {
    expect(displayLabelFor(entity("fallback123", "thread", { title: "  " }))).toBe("fallback");
  });
});

describe("truncate", () => {
  it("preserves short strings unchanged", () => {
    expect(truncate("short")).toBe("short");
  });

  it("truncates long strings with an ellipsis", () => {
    const result = truncate("a".repeat(50));
    expect(result).toHaveLength(24);
    expect(result.endsWith("…")).toBe(true);
  });

  it("respects custom maximum lengths", () => {
    expect(truncate("hello world", 5)).toBe("hell…");
  });
});

describe("shouldShowLabel", () => {
  it("always shows the selected node label", () => {
    expect(
      shouldShowLabel({
        nodeId: "n1",
        cameraDistance: 9999,
        selectedId: "n1",
        selectedNeighborIds: new Set(),
        fpsGuardState: "emergency",
      }),
    ).toBe(true);
  });

  it("shows selected neighbor labels regardless of distance", () => {
    expect(
      shouldShowLabel({
        nodeId: "n2",
        cameraDistance: 9999,
        selectedId: "n1",
        selectedNeighborIds: new Set(["n2", "n3"]),
        fpsGuardState: "full",
      }),
    ).toBe(true);
  });

  it("hides distant non-selected labels", () => {
    expect(
      shouldShowLabel({
        nodeId: "n4",
        cameraDistance: 500,
        selectedId: "n1",
        selectedNeighborIds: new Set(["n2"]),
        fpsGuardState: "full",
      }),
    ).toBe(false);
  });

  it("shows close labels when FPS is healthy", () => {
    expect(
      shouldShowLabel({
        nodeId: "n5",
        cameraDistance: 80,
        selectedId: null,
        selectedNeighborIds: new Set(),
        fpsGuardState: "full",
      }),
    ).toBe(true);
  });

  it("keeps visible labels through the hysteresis band", () => {
    expect(
      shouldShowLabel({
        nodeId: "n5",
        cameraDistance: 100,
        selectedId: null,
        selectedNeighborIds: new Set(),
        fpsGuardState: "full",
        currentlyVisible: true,
      }),
    ).toBe(true);
  });

  it("does not show hidden labels inside the hysteresis band", () => {
    expect(
      shouldShowLabel({
        nodeId: "n5",
        cameraDistance: 100,
        selectedId: null,
        selectedNeighborIds: new Set(),
        fpsGuardState: "full",
        currentlyVisible: false,
      }),
    ).toBe(false);
  });

  it("hides everything but selected labels during emergency cull", () => {
    expect(
      shouldShowLabel({
        nodeId: "n6",
        cameraDistance: 50,
        selectedId: "n1",
        selectedNeighborIds: new Set(),
        fpsGuardState: "emergency",
      }),
    ).toBe(false);
  });
});
