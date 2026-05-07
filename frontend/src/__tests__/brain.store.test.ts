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

  it("applies entity_classified to update cluster_id on existing entity", () => {
    const existing = {
      id: "e7",
      type: "thread",
      data: { title: "Refund inquiry" },
      source_id: null,
      created_at: "t",
      updated_at: "t",
      cluster_id: null,
    } as const;
    useBrainStore.setState({
      entities: new Map([[existing.id, { ...existing }]]),
      edges: new Map(),
      lastSeq: 0,
      fps: 0,
      selectedId: null,
    });

    useBrainStore.getState().applyEvent({
      seq: 5,
      type: "entity_classified",
      timestamp: 0,
      source_id: null,
      persisted_id: "e7",
      payload: { entity_id: "e7", cluster_id: "billing_payments" },
    });

    expect(useBrainStore.getState().entities.get("e7")?.cluster_id).toBe("billing_payments");
    expect(useBrainStore.getState().lastSeq).toBe(5);
  });

  it("increments edge count for organizer-created edge events", () => {
    useBrainStore.setState({
      entities: new Map(),
      edges: new Map(),
      lastSeq: 0,
      fps: 0,
      selectedId: null,
      connectionStatus: "syncing",
    });
    useBrainStore.getState().applyEvent({
      seq: 1,
      type: "entity_edge_created",
      timestamp: 0,
      source_id: "a",
      persisted_id: "e1",
      payload: {
        source_id: "a",
        target_id: "b",
        relation_type: "same_cluster_related",
        cluster_id: "billing_payments",
      },
    });
    expect(useBrainStore.getState().edges.size).toBe(1);
  });

  it("ignores entity_classified for unknown entity ids", () => {
    useBrainStore.setState({
      entities: new Map(),
      edges: new Map(),
      lastSeq: 0,
      fps: 0,
      selectedId: null,
    });

    useBrainStore.getState().applyEvent({
      seq: 9,
      type: "entity_classified",
      timestamp: 0,
      source_id: null,
      persisted_id: "ghost",
      payload: { entity_id: "ghost", cluster_id: "billing_payments" },
    });

    expect(useBrainStore.getState().entities.size).toBe(0);
    expect(useBrainStore.getState().lastSeq).toBe(9);
  });
});
