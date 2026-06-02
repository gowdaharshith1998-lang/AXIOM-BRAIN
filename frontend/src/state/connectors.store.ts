import { create } from "zustand";

import { requestRaw } from "@/lib/http";

export type ConnectorStatus = {
  vendor: string;
  status: "connected" | "disconnected" | "error";
  configured?: boolean;
  account_label?: string | null;
  last_sync_at?: string | null;
  entities_ingested?: number;
  events_24h?: number;
  writes_blocked_week?: number;
  watch_mode?: "webhook" | "polling";
};

export const CONNECTOR_VENDORS = [
  { id: "github", label: "GitHub" },
  { id: "linear", label: "Linear" },
  { id: "slack", label: "Slack" },
  { id: "notion", label: "Notion" },
  { id: "gmail", label: "Gmail" },
] as const;

const STATUS_URL = "/api/internal/connectors/status";
const SYNC_ALL_URL = "/api/internal/connectors/sync-all";

type ConnectorsState = {
  connectors: ConnectorStatus[];
  loading: boolean;
  syncingAll: boolean;
  error: string | null;
  lastFetchedAt: number | null;
  fetchStatuses: () => Promise<void>;
  syncAll: () => Promise<{ ok: boolean; message?: string }>;
  incrementConnectorEvents: (vendor: string) => void;
  getByVendor: (vendor: string) => ConnectorStatus | undefined;
};

export const useConnectorsStore = create<ConnectorsState>((set, get) => ({
  connectors: [],
  loading: false,
  syncingAll: false,
  error: null,
  lastFetchedAt: null,

  fetchStatuses: async () => {
    set({ loading: true, error: null });
    try {
      const response = await requestRaw(STATUS_URL);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = (await response.json()) as { connectors?: ConnectorStatus[] };
      set({
        connectors: Array.isArray(payload.connectors) ? payload.connectors : [],
        loading: false,
        lastFetchedAt: Date.now(),
      });
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : "Unable to load connector status",
      });
    }
  },

  syncAll: async () => {
    set({ syncingAll: true });
    try {
      const response = await requestRaw(SYNC_ALL_URL, { method: "POST" });
      if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
          const payload = (await response.json()) as { detail?: string };
          detail = String(payload.detail || detail);
        } catch {
          // ignore
        }
        return { ok: false, message: detail };
      }
      await get().fetchStatuses();
      return { ok: true };
    } catch (error) {
      return {
        ok: false,
        message: error instanceof Error ? error.message : "Sync request failed",
      };
    } finally {
      set({ syncingAll: false });
    }
  },

  incrementConnectorEvents: (vendor) => {
    set((state) => ({
      connectors: state.connectors.map((row) =>
        row.vendor === vendor ? { ...row, events_24h: (row.events_24h ?? 0) + 1 } : row,
      ),
    }));
  },

  getByVendor: (vendor) => get().connectors.find((row) => row.vendor === vendor),
}));
