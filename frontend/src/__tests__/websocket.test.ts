import { describe, expect, it, vi } from "vitest";

import { BrainSocket } from "@/lib/websocket";

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  url: string;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  close() {
    this.onclose?.();
  }
}

describe("websocket", () => {
  it("reconnects with since=lastSeq after disconnect", async () => {
    const Original = globalThis.WebSocket;
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;
    const st = vi.spyOn(window, "setTimeout");

    try {
      const sock = new BrainSocket("ws://x/ws/brain");
      const off = sock.on((e) => sock.setLastSeq(e.seq));
      sock.start();

      const ws1 = MockWebSocket.instances[0]!;
      ws1.onmessage?.({
        data: JSON.stringify({
          seq: 7,
          type: "entity_added",
          timestamp: 0,
          source_id: "s",
          persisted_id: "p",
          payload: {},
        }),
      });
      ws1.close();

      expect(st).toHaveBeenCalled();
      // next start should include since=7
      sock.start();
      const ws2 = MockWebSocket.instances[1]!;
      expect(ws2.url).toMatch(/since=7/);
      off();
      sock.close();
    } finally {
      globalThis.WebSocket = Original;
      st.mockRestore();
    }
  });

  it("reports live after first event and offline on disconnect", () => {
    const Original = globalThis.WebSocket;
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;
    const statuses: string[] = [];
    const st = vi.spyOn(window, "setTimeout");

    try {
      const sock = new BrainSocket("ws://x/ws/brain");
      sock.onStatus((status) => statuses.push(status));
      sock.start();
      const ws = MockWebSocket.instances.at(-1)!;
      ws.onmessage?.({
        data: JSON.stringify({
          seq: 1,
          type: "entity_added",
          timestamp: 0,
          source_id: "s",
          persisted_id: "p",
          payload: {},
        }),
      });
      ws.close();
      expect(statuses).toContain("live");
      expect(statuses).toContain("offline");
      sock.close();
    } finally {
      globalThis.WebSocket = Original;
      st.mockRestore();
    }
  });

  it("uses exponential reconnect backoff from one to sixteen seconds", () => {
    const Original = globalThis.WebSocket;
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;
    const st = vi.spyOn(window, "setTimeout");

    try {
      const sock = new BrainSocket("ws://x/ws/brain");
      sock.start();
      MockWebSocket.instances.at(-1)!.close();
      sock.start();
      MockWebSocket.instances.at(-1)!.close();
      sock.start();
      MockWebSocket.instances.at(-1)!.close();
      expect(st.mock.calls.map((call) => call[1])).toEqual(expect.arrayContaining([1000, 2000, 4000]));
      sock.close();
    } finally {
      globalThis.WebSocket = Original;
      st.mockRestore();
    }
  });
});
