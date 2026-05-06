import { describe, expect, it } from "vitest";

import { useBrainStore } from "@/state/brain.store";

describe("brain.store", () => {
  it("bootstraps entities and edges", () => {
    useBrainStore.setState({
      entities: new Map(),
      edges: new Map(),
      lastSeq: 0,
      fps: 0,
      selectedId: null,
    });

    useBrainStore.getState().bootstrap(
      [
        {
          id: "e1",
          type: "thread",
          data: {},
          source_id: null,
          created_at: "t",
          updated_at: "t",
        },
      ],
      [
        {
          id: "l1",
          source_id: "e1",
          target_id: "e1",
          relationship: "R",
          data: {},
          created_at: "t",
        },
      ],
    );

    expect(useBrainStore.getState().entities.size).toBe(1);
    expect(useBrainStore.getState().edges.size).toBe(1);
  });

  it("applyEvent is idempotent by seq", () => {
    useBrainStore.setState({
      entities: new Map(),
      edges: new Map(),
      lastSeq: 0,
      fps: 0,
      selectedId: null,
    });

    useBrainStore.getState().applyEvent({
      seq: 2,
      type: "entity_added",
      timestamp: 0,
      source_id: "s",
      persisted_id: "e2",
      payload: {
        type: "thread",
        data: {},
        source_id: null,
        created_at: "t",
        updated_at: "t",
      },
    });
    expect(useBrainStore.getState().lastSeq).toBe(2);
    expect(useBrainStore.getState().entities.has("e2")).toBe(true);

    // replay
    useBrainStore.getState().applyEvent({
      seq: 2,
      type: "entity_added",
      timestamp: 0,
      source_id: "s",
      persisted_id: "e2",
      payload: {
        type: "thread",
        data: {},
        source_id: null,
        created_at: "t",
        updated_at: "t",
      },
    });
    expect(useBrainStore.getState().entities.size).toBe(1);
  });

  it("applies edge_added into edges map", () => {
    useBrainStore.setState({
      entities: new Map(),
      edges: new Map(),
      lastSeq: 0,
      fps: 0,
      selectedId: null,
    });

    useBrainStore.getState().applyEvent({
      seq: 1,
      type: "edge_added",
      timestamp: 0,
      source_id: "s",
      persisted_id: "l1",
      payload: {
        source_id: "e1",
        target_id: "e2",
        relationship: "R",
        data: {},
        created_at: "t",
      },
    });

    expect(useBrainStore.getState().edges.has("l1")).toBe(true);
  });
});

