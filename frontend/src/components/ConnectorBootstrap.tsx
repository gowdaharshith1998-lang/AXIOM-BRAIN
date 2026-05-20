import { useEffect } from "react";

import { useConnectorsStore } from "@/state/connectors.store";

/** Hydrates connector status on app load and after sync/OAuth events. */
export function ConnectorBootstrap() {
  const fetchStatuses = useConnectorsStore((s) => s.fetchStatuses);

  useEffect(() => {
    void fetchStatuses();
  }, [fetchStatuses]);

  useEffect(() => {
    const onBrainEvent = (event: Event) => {
      const detail = (event as CustomEvent<{ type?: string }>).detail;
      if (
        detail?.type === "connector_sync_completed" ||
        detail?.type === "connector_install_completed"
      ) {
        void fetchStatuses();
      }
    };
    window.addEventListener("axiom:brain-event", onBrainEvent);
    return () => window.removeEventListener("axiom:brain-event", onBrainEvent);
  }, [fetchStatuses]);

  return null;
}
