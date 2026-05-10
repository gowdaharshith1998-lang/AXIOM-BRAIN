export type BrainEvent = {
  seq: number;
  type:
    | "entity_added"
    | "entity_created"
    | "entity_modified"
    | "entity_removed"
    | "edge_added"
    | "entity_edge_created"
    | "edge_removed"
    | "entity_classified"
    | "cluster_health_changed"
    | "agent_action"
    | "agent_action_evaluated"
    | "receipt_added"
    | "insight_flagged"
    | "watchdog_alert_raised"
    | "watchdog_alert_acknowledged"
    | "watchdog_alert_resolved"
    | "agent_navigation_step"
    | "confidence_changed";
  timestamp: number;
  source_id: string | null;
  persisted_id: string | null;
  payload: Record<string, unknown>;
};

export type BrainEventHandler = (event: BrainEvent) => void;

export class BrainSocket {
  private ws: WebSocket | null = null;
  private retryDelayMs = 1000;
  private closed = false;
  private handlers = new Set<BrainEventHandler>();
  private statusHandlers = new Set<(status: "syncing" | "live" | "offline") => void>();
  private lastSeq = 0;

  constructor(private url: string) {}

  on(handler: BrainEventHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  onStatus(handler: (status: "syncing" | "live" | "offline") => void): () => void {
    this.statusHandlers.add(handler);
    return () => this.statusHandlers.delete(handler);
  }

  private emitStatus(status: "syncing" | "live" | "offline"): void {
    for (const handler of this.statusHandlers) handler(status);
  }

  getLastSeq(): number {
    return this.lastSeq;
  }

  setLastSeq(seq: number): void {
    this.lastSeq = Math.max(this.lastSeq, seq);
  }

  start(): void {
    if (this.closed) return;
    const sep = this.url.includes("?") ? "&" : "?";
    this.ws = new WebSocket(`${this.url}${sep}since=${this.lastSeq}`);

    this.ws.onopen = () => {
      this.retryDelayMs = 1000;
    };

    this.ws.onmessage = (msg) => {
      try {
        const event: BrainEvent = JSON.parse(String(msg.data));
        if (typeof event.seq === "number") this.setLastSeq(event.seq);
        this.emitStatus("live");
        for (const h of this.handlers) h(event);
      } catch {
        // ignore malformed payloads
      }
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };

    this.ws.onclose = () => {
      if (this.closed) return;
      this.emitStatus("offline");
      const delay = this.retryDelayMs;
      this.retryDelayMs = Math.min(this.retryDelayMs * 2, 16000);
      window.setTimeout(() => this.start(), delay);
    };
  }

  close(): void {
    this.closed = true;
    this.ws?.close();
  }
}
