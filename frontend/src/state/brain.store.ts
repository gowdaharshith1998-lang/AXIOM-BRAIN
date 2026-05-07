import { create } from "zustand";

import type { BrainEvent } from "@/lib/websocket";

export type Entity = {
  id: string;
  type: string;
  data: Record<string, unknown>;
  source_id: string | null;
  created_at: string;
  updated_at: string;
  cluster_id?: string | null;
  composite_importance?: number;
};

export type Edge = {
  id: string;
  source_id: string;
  target_id: string;
  relationship: string;
  data: Record<string, unknown>;
  created_at: string;
};

type BrainState = {
  entities: Map<string, Entity>;
  edges: Map<string, Edge>;
  lastSeq: number;
  fps: number;
  selectedId: string | null;

  bootstrap: (entities: Entity[], edges: Edge[]) => void;
  applyEvent: (event: BrainEvent) => void;
  setFps: (fps: number) => void;
  select: (id: string | null) => void;
};

export const useBrainStore = create<BrainState>((set) => ({
  entities: new Map(),
  edges: new Map(),
  lastSeq: 0,
  fps: 0,
  selectedId: null,

  bootstrap: (entities, edges) =>
    set({
      entities: new Map(entities.map((e) => [e.id, e])),
      edges: new Map(edges.map((e) => [e.id, e])),
    }),

  applyEvent: (event) =>
    set((state) => {
      if (event.seq <= state.lastSeq) return {};
      const next: Partial<BrainState> = { lastSeq: event.seq };

      if (event.type === "entity_added" && event.persisted_id) {
        const entities = new Map(state.entities);
        const payload = event.payload as unknown as Omit<Entity, "id"> & {
          nick?: unknown;
        };
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        const { nick, ...rest } = payload;
        entities.set(event.persisted_id, { id: event.persisted_id, ...rest });
        next.entities = entities;
      }

      if (event.type === "edge_added" && event.persisted_id) {
        const edges = new Map(state.edges);
        const payload = event.payload as unknown as Omit<Edge, "id">;
        edges.set(event.persisted_id, { id: event.persisted_id, ...payload });
        next.edges = edges;
      }

      if (event.type === "entity_classified") {
        const payload = event.payload as { entity_id?: string; cluster_id?: string };
        const id = payload.entity_id ?? event.persisted_id;
        const cluster_id = payload.cluster_id;
        if (typeof id === "string" && typeof cluster_id === "string") {
          const existing = state.entities.get(id);
          if (existing) {
            const entities = new Map(state.entities);
            entities.set(id, { ...existing, cluster_id });
            next.entities = entities;
          }
        }
      }

      return next;
    }),

  setFps: (fps) => set({ fps }),
  select: (id) => set({ selectedId: id }),
}));

