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

type BrainState = {
  entities: Map<string, Entity>;
  edges: Map<string, Edge>;
  lastSeq: number;
  fps: number;
  selectedId: string | null;
  selectedClusterId: string | null;
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
  setConnectionStatus: (status: ConnectionStatus) => void;
  setClusterHealth: (clusterHealth: Record<string, ClusterHealthSnapshot>) => void;
  addAgentAction: (action: AgentActionLog) => void;
  addReceipt: (receipt: LedgerReceipt) => void;
  addInsight: (insight: WardenInsight) => void;
};

export const useBrainStore = create<BrainState>((set) => ({
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

  bootstrap: (entities, edges) =>
    set({
      entities: new Map(entities.map((e) => [e.id, e])),
      edges: new Map(edges.map((e) => [e.id, e])),
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
  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),
  setClusterHealth: (clusterHealth) => set({ clusterHealth }),
  addAgentAction: (action) =>
    set((state) => ({
      agentActions: [action, ...state.agentActions.filter((item) => item.action_id !== action.action_id)].slice(0, 25),
    })),
  addReceipt: (receipt) => set((state) => ({ receipts: [receipt, ...state.receipts].slice(0, 30) })),
  addInsight: (insight) => set((state) => ({ insights: [insight, ...state.insights].slice(0, 10) })),
}));
