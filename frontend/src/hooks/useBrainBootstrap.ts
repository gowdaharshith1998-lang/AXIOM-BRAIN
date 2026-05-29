import { useEffect } from "react";

import { useBrainStore, type ClusterHealthSnapshot, type Edge, type Entity } from "@/state/brain.store";

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as T;
}

export function useBrainBootstrap() {
  const bootstrap = useBrainStore((s) => s.bootstrap);
  const setClusterHealth = useBrainStore((s) => s.setClusterHealth);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [entities, edges, health] = await Promise.all([
          fetchJson<unknown[]>("/api/entities"),
          fetchJson<unknown[]>("/api/edges"),
          fetchJson<Record<string, ClusterHealthSnapshot>>("/api/cluster_health").catch(() => ({})),
        ]);
        if (cancelled) return;
        bootstrap(entities as Entity[], edges as Edge[]);
        setClusterHealth(health);
      } catch (error) {
        // eslint-disable-next-line no-console
        console.error("[useBrainBootstrap] failed:", error);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [bootstrap, setClusterHealth]);
}
