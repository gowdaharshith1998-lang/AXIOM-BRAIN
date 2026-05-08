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

export type ConnectionStatus = "syncing" | "live" | "offline";
export type ClusterHealthStatus = "healthy" | "degraded" | "critical";

export type ClusterHealthSnapshot = {
  cluster_id: string;
  status: ClusterHealthStatus;
  ingest_rate_per_min: number;
  last_ingest_at: string | null;
  total_entities: number;
};

export type AgentActionLog = {
  action_id: string;
  agent_name: string;
  cluster_id: string;
  skill_called: string;
  decision?: "allow" | "deny";
  reason?: string;
  timestamp: string;
};

export type LedgerReceipt = {
  receipt_id: string;
  action_id: string;
  decision: "allow" | "deny";
  agent_name: string;
  merkle_root: string;
  timestamp: string;
};

export type WardenInsight = {
  insight_id: string;
  severity: "info" | "warning" | "critical";
  message: string;
  confidence: number;
  related_entity_ids: string[];
  recommended_actions: string[];
  timestamp: string;
};

export type BrainFocusMode = "AMBIENT" | "FOCUS_CLUSTER" | "FOCUS_ENTITY";

export type BrainFocusState = {
  mode: BrainFocusMode;
  clusterId: string | null;
  entityId: string | null;
  pendingEntityId: string | null;
  hoveredClusterId: string | null;
};

type BrainState = {
  entities: Map<string, Entity>;
  edges: Map<string, Edge>;
  lastSeq: number;
  fps: number;
  selectedId: string | null;
  selectedClusterId: string | null;
  focus: BrainFocusState;
  connectionStatus: ConnectionStatus;
  clusterHealth: Record<string, ClusterHealthSnapshot>;
  agentActions: AgentActionLog[];
  receipts: LedgerReceipt[];
  insights: WardenInsight[];

  bootstrap: (entities: Entity[], edges: Edge[]) => void;
  applyEvent: (event: BrainEvent) => void;
  setFps: (fps: number) => void;
  select: (id: string | null) => void;
  selectCluster: (id: string | null) => void;
  focusCluster: (clusterId: string) => void;
  focusEntity: (entityId: string, parentClusterId: string) => void;
  clearFocus: () => void;
  hydrateFromUrl: () => void;
  setHoveredCluster: (id: string | null) => void;
  setConnectionStatus: (status: ConnectionStatus) => void;
  setClusterHealth: (clusterHealth: Record<string, ClusterHealthSnapshot>) => void;
  addAgentAction: (action: AgentActionLog) => void;
  addReceipt: (receipt: LedgerReceipt) => void;
  addInsight: (insight: WardenInsight) => void;
};

function isSafeId(value: unknown): value is string {
  return typeof value === "string" && /^[\w-]+$/.test(value);
}

function replaceHash(fragment: string) {
  if (typeof window === "undefined") return;
  window.history.replaceState(null, "", fragment);
}

function resolvePendingEntityFocus(entities: Map<string, Entity>, focus: BrainFocusState): BrainFocusState {
  if (!focus.pendingEntityId) return focus;
  const pending = entities.get(focus.pendingEntityId);
  if (!pending || !isSafeId(pending.cluster_id)) return focus;
  const entityId = focus.pendingEntityId;
  return { ...focus, mode: "FOCUS_ENTITY", clusterId: pending.cluster_id, entityId, pendingEntityId: null };
}

function focusReducer(prev: BrainFocusState, next: Partial<BrainFocusState>): BrainFocusState {
  const hoveredClusterId = Object.prototype.hasOwnProperty.call(next, "hoveredClusterId")
    ? next.hoveredClusterId
    : prev.hoveredClusterId;

  const merged: BrainFocusState = {
    mode: next.mode ?? prev.mode,
    clusterId: next.clusterId ?? prev.clusterId,
    entityId: next.entityId ?? prev.entityId,
    pendingEntityId: next.pendingEntityId ?? prev.pendingEntityId,
    hoveredClusterId,
  };

  if (merged.pendingEntityId !== null) {
    return { mode: "AMBIENT", clusterId: null, entityId: null, pendingEntityId: merged.pendingEntityId, hoveredClusterId: merged.hoveredClusterId };
  }

  if (merged.mode === "AMBIENT") {
    return { mode: "AMBIENT", clusterId: null, entityId: null, pendingEntityId: null, hoveredClusterId: merged.hoveredClusterId };
  }

  if (merged.mode === "FOCUS_CLUSTER") {
    return { mode: "FOCUS_CLUSTER", clusterId: merged.clusterId, entityId: null, pendingEntityId: null, hoveredClusterId: merged.hoveredClusterId };
  }

  return { mode: "FOCUS_ENTITY", clusterId: merged.clusterId, entityId: merged.entityId, pendingEntityId: null, hoveredClusterId: merged.hoveredClusterId };
}

export const useBrainStore = create<BrainState>((set) => ({
  entities: new Map(),
  edges: new Map(),
  lastSeq: 0,
  fps: 0,
  selectedId: null,
  selectedClusterId: null,
  focus: { mode: "AMBIENT", clusterId: null, entityId: null, pendingEntityId: null, hoveredClusterId: null },
  connectionStatus: "syncing",
  clusterHealth: {},
  agentActions: [],
  receipts: [],
  insights: [],

  bootstrap: (entities, edges) =>
    set((state) => {
      const nextEntities = new Map(entities.map((e) => [e.id, e]));
      const nextFocus = resolvePendingEntityFocus(nextEntities, state.focus);
      if (nextFocus !== state.focus && nextFocus.mode === "FOCUS_ENTITY" && nextFocus.entityId) {
        replaceHash(`#entity=${nextFocus.entityId}`);
      }
      return {
        entities: nextEntities,
        edges: new Map(edges.map((e) => [e.id, e])),
        focus: nextFocus,
      };
    }),

  applyEvent: (event) =>
    set((state) => {
      if (event.seq <= state.lastSeq) return {};
      const next: Partial<BrainState> = { lastSeq: event.seq };

      if ((event.type === "entity_added" || event.type === "entity_created") && event.persisted_id) {
        const entities = new Map(state.entities);
        const payload = event.payload as unknown as Omit<Entity, "id"> & {
          nick?: unknown;
        };
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        const { nick, ...rest } = payload;
        entities.set(event.persisted_id, { id: event.persisted_id, ...rest });
        next.entities = entities;
      }

      if ((event.type === "edge_added" || event.type === "entity_edge_created") && event.persisted_id) {
        const edges = new Map(state.edges);
        const payload = event.payload as unknown as Partial<Omit<Edge, "id">> & {
          source_id?: string;
          target_id?: string;
          relation_type?: string;
          relationship?: string;
        };
        if (typeof payload.source_id === "string" && typeof payload.target_id === "string") {
          edges.set(event.persisted_id, {
            id: event.persisted_id,
            source_id: payload.source_id,
            target_id: payload.target_id,
            relationship: payload.relationship ?? payload.relation_type ?? "related",
            data: (payload.data as Record<string, unknown> | undefined) ?? {},
            created_at: typeof payload.created_at === "string" ? payload.created_at : new Date().toISOString(),
          });
        }
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

      if (event.type === "cluster_health_changed") {
        const payload = event.payload as Partial<ClusterHealthSnapshot>;
        if (typeof payload.cluster_id === "string" && typeof payload.status === "string") {
          next.clusterHealth = {
            ...state.clusterHealth,
            [payload.cluster_id]: payload as ClusterHealthSnapshot,
          };
        }
      }

      if (event.type === "agent_action" || event.type === "agent_action_evaluated") {
        const payload = event.payload as Partial<AgentActionLog>;
        if (typeof payload.action_id === "string") {
          const existing = state.agentActions.filter((action) => action.action_id !== payload.action_id);
          next.agentActions = [{ ...(payload as AgentActionLog) }, ...existing].slice(0, 25);
        }
      }

      if (event.type === "receipt_added") {
        const payload = event.payload as Partial<LedgerReceipt>;
        if (typeof payload.receipt_id === "string") {
          next.receipts = [payload as LedgerReceipt, ...state.receipts].slice(0, 30);
        }
      }

      if (event.type === "insight_flagged") {
        const payload = event.payload as Partial<WardenInsight>;
        if (typeof payload.insight_id === "string") {
          next.insights = [payload as WardenInsight, ...state.insights].slice(0, 10);
        }
      }

      return next;
    }),

  setFps: (fps) => set({ fps }),
  select: (id) => set({ selectedId: id, selectedClusterId: null }),
  selectCluster: (id) => set({ selectedClusterId: id, selectedId: null }),

  focusCluster: (clusterId) =>
    set((state) => {
      if (!isSafeId(clusterId)) return {};
      replaceHash(`#cluster=${clusterId}`);
      return { focus: focusReducer(state.focus, { mode: "FOCUS_CLUSTER", clusterId, entityId: null, pendingEntityId: null }) };
    }),

  focusEntity: (entityId, parentClusterId) =>
    set((state) => {
      if (!isSafeId(entityId) || !isSafeId(parentClusterId)) return {};
      replaceHash(`#entity=${entityId}`);
      return {
        focus: focusReducer(state.focus, {
          mode: "FOCUS_ENTITY",
          clusterId: parentClusterId,
          entityId,
          pendingEntityId: null,
        }),
      };
    }),

  clearFocus: () =>
    set((state) => {
      replaceHash("");
      return { focus: focusReducer(state.focus, { mode: "AMBIENT", clusterId: null, entityId: null, pendingEntityId: null }) };
    }),

  hydrateFromUrl: () =>
    set((state) => {
      if (typeof window === "undefined") return {};
      const hash = window.location.hash ?? "";

      const clusterMatch = /^#cluster=([\w-]+)$/.exec(hash);
      if (clusterMatch) {
        const clusterId = clusterMatch[1];
        if (!isSafeId(clusterId)) return {};
        replaceHash(`#cluster=${clusterId}`);
        return { focus: focusReducer(state.focus, { mode: "FOCUS_CLUSTER", clusterId, entityId: null, pendingEntityId: null }) };
      }

      const entityMatch = /^#entity=([\w-]+)$/.exec(hash);
      if (entityMatch) {
        const entityId = entityMatch[1];
        if (!isSafeId(entityId)) return {};
        const entity = state.entities.get(entityId);
        if (entity && isSafeId(entity.cluster_id)) {
          replaceHash(`#entity=${entityId}`);
          return {
            focus: focusReducer(state.focus, {
              mode: "FOCUS_ENTITY",
              clusterId: entity.cluster_id,
              entityId,
              pendingEntityId: null,
            }),
          };
        }

        // Clean URL already has #entity=<id>; do not rewrite history here.
        return { focus: focusReducer(state.focus, { mode: "AMBIENT", pendingEntityId: entityId }) };
      }

      return {};
    }),

  setHoveredCluster: (id) =>
    set((state) => {
      if (id !== null && !isSafeId(id)) return {};
      return { focus: focusReducer(state.focus, { hoveredClusterId: id }) };
    }),

  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),
  setClusterHealth: (clusterHealth) => set({ clusterHealth }),
  addAgentAction: (action) =>
    set((state) => ({
      agentActions: [action, ...state.agentActions.filter((item) => item.action_id !== action.action_id)].slice(0, 25),
    })),
  addReceipt: (receipt) => set((state) => ({ receipts: [receipt, ...state.receipts].slice(0, 30) })),
  addInsight: (insight) => set((state) => ({ insights: [insight, ...state.insights].slice(0, 10) })),
}));
