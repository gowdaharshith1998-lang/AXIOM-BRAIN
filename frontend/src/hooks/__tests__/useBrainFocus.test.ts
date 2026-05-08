import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useBrainFocus } from "@/hooks/useBrainFocus";
import { useBrainStore } from "@/state/brain.store";

function resetStore() {
  useBrainStore.setState({
    entities: new Map(),
    edges: new Map(),
    lastSeq: 0,
    fps: 0,
    selectedId: null,
    selectedClusterId: null,
    connectionStatus: "syncing",
    clusterHealth: {},
    agentActions: [],
    receipts: [],
    insights: [],
    focus: { mode: "AMBIENT", clusterId: null, entityId: null, pendingEntityId: null },
  });
}

describe("useBrainFocus (focus state machine)", () => {
  it("initial state is AMBIENT with clusterId=null and entityId=null", () => {
    resetStore();
    const { result } = renderHook(() => useBrainFocus());
    expect(result.current.focus.mode).toBe("AMBIENT");
    expect(result.current.focus.clusterId).toBeNull();
    expect(result.current.focus.entityId).toBeNull();
    expect(result.current.focus.pendingEntityId).toBeNull();
  });

  it("focusCluster transitions to FOCUS_CLUSTER and sets URL hash to #cluster=<id>", () => {
    resetStore();
    const replaceSpy = vi.spyOn(window.history, "replaceState");
    const { result } = renderHook(() => useBrainFocus());

    act(() => result.current.focusCluster("documents"));

    expect(result.current.focus.mode).toBe("FOCUS_CLUSTER");
    expect(result.current.focus.clusterId).toBe("documents");
    expect(result.current.focus.entityId).toBeNull();
    expect(result.current.focus.pendingEntityId).toBeNull();
    expect(replaceSpy).toHaveBeenCalledWith(null, "", "#cluster=documents");
  });

  it("focusEntity transitions to FOCUS_ENTITY, preserves clusterId, sets URL hash to #entity=<id>", () => {
    resetStore();
    const replaceSpy = vi.spyOn(window.history, "replaceState");
    const { result } = renderHook(() => useBrainFocus());

    act(() => result.current.focusCluster("documents"));
    act(() => result.current.focusEntity("E-1", "documents"));

    expect(result.current.focus.mode).toBe("FOCUS_ENTITY");
    expect(result.current.focus.clusterId).toBe("documents");
    expect(result.current.focus.entityId).toBe("E-1");
    expect(result.current.focus.pendingEntityId).toBeNull();
    expect(replaceSpy).toHaveBeenCalledWith(null, "", "#entity=E-1");
  });

  it("clearFocus returns to AMBIENT and clears URL hash", () => {
    resetStore();
    const replaceSpy = vi.spyOn(window.history, "replaceState");
    const { result } = renderHook(() => useBrainFocus());

    act(() => result.current.focusCluster("documents"));
    act(() => result.current.clearFocus());

    expect(result.current.focus.mode).toBe("AMBIENT");
    expect(result.current.focus.clusterId).toBeNull();
    expect(result.current.focus.entityId).toBeNull();
    expect(result.current.focus.pendingEntityId).toBeNull();
    expect(replaceSpy).toHaveBeenCalledWith(null, "", "");
  });

  it("hydrateFromUrl reads #cluster=<id> on mount and transitions to FOCUS_CLUSTER", () => {
    resetStore();
    const replaceSpy = vi.spyOn(window.history, "replaceState");
    window.location.hash = "#cluster=documents";
    const { result } = renderHook(() => useBrainFocus());

    act(() => useBrainStore.getState().hydrateFromUrl());

    expect(result.current.focus.mode).toBe("FOCUS_CLUSTER");
    expect(result.current.focus.clusterId).toBe("documents");
    expect(result.current.focus.entityId).toBeNull();
    expect(result.current.focus.pendingEntityId).toBeNull();
    expect(replaceSpy).toHaveBeenCalledWith(null, "", "#cluster=documents");
  });

  it("hydrateFromUrl with #entity=<id> stays AMBIENT until entities load, then transitions", () => {
    resetStore();
    const replaceSpy = vi.spyOn(window.history, "replaceState");
    window.location.hash = "#entity=E-1";
    renderHook(() => useBrainFocus());

    act(() => useBrainStore.getState().hydrateFromUrl());

    expect(useBrainStore.getState().focus).toEqual({
      mode: "AMBIENT",
      clusterId: null,
      entityId: null,
      pendingEntityId: "E-1",
    });
    expect(replaceSpy).not.toHaveBeenCalled();

    act(() =>
      useBrainStore.getState().bootstrap(
        [
          {
            id: "E-1",
            type: "note",
            data: {},
            source_id: null,
            created_at: "2026-01-01T00:00:00.000Z",
            updated_at: "2026-01-01T00:00:00.000Z",
            cluster_id: "documents",
          },
        ],
        [],
      ),
    );

    expect(useBrainStore.getState().focus).toEqual({
      mode: "FOCUS_ENTITY",
      clusterId: "documents",
      entityId: "E-1",
      pendingEntityId: null,
    });
    expect(replaceSpy).toHaveBeenCalledWith(null, "", "#entity=E-1");
  });

  it("setHoveredCluster updates hoveredClusterId in store", () => {
    resetStore();
    const { result } = renderHook(() => useBrainFocus());

    act(() => result.current.setHoveredCluster("documents"));

    expect(useBrainStore.getState().focus.hoveredClusterId).toBe("documents");
  });

  it("setHoveredCluster(null) clears hoveredClusterId", () => {
    resetStore();
    const { result } = renderHook(() => useBrainFocus());

    act(() => result.current.setHoveredCluster("documents"));
    act(() => result.current.setHoveredCluster(null));

    expect(useBrainStore.getState().focus.hoveredClusterId).toBeNull();
  });
});

