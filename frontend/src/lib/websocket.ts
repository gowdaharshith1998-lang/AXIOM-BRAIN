export type BrainEvent = {
  seq: number;
  type:
    | "entity_added"
    | "entity_modified"
    | "entity_removed"
    | "edge_added"
    | "edge_removed"
    | "entity_classified";
  timestamp: number;
  source_id: string | null;
  persisted_id: string | null;
  payload: Record<string, unknown>;
};

export type BrainEventHandler = (event: BrainEvent) => void;

export class BrainSocket {
  private ws: WebSocket | null = null;
  private retryDelayMs = 500;
  private closed = false;
  private handlers = new Set<BrainEventHandler>();
  private lastSeq = 0;

  constructor(private url: string) {}

  on(handler: BrainEventHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
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
      this.retryDelayMs = 500;
    };

    this.ws.onmessage = (msg) => {
      try {
        const event: BrainEvent = JSON.parse(String(msg.data));
        if (typeof event.seq === "number") this.setLastSeq(event.seq);
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
      const delay = this.retryDelayMs;
      this.retryDelayMs = Math.min(this.retryDelayMs * 2, 8000);
      window.setTimeout(() => this.start(), delay);
    };
  }

  close(): void {
    this.closed = true;
    this.ws?.close();
  }
}

