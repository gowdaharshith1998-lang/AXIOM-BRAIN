import { describe, it, expect, afterEach } from "vitest";

import { wsUrl } from "@/lib/wsUrl";

const originalLocation = window.location;

function setLocation(protocol: string, host: string) {
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { protocol, host },
  });
}

afterEach(() => {
  Object.defineProperty(window, "location", {
    configurable: true,
    value: originalLocation,
  });
});

describe("wsUrl", () => {
  it("maps http -> ws and preserves host (with port)", () => {
    setLocation("http:", "localhost:5173");
    expect(wsUrl("/ws/brain")).toBe("ws://localhost:5173/ws/brain");
  });

  it("maps https -> wss", () => {
    setLocation("https:", "app.example.com");
    expect(wsUrl("/ws/brain")).toBe("wss://app.example.com/ws/brain");
  });

  it("normalizes a path that is missing a leading slash", () => {
    setLocation("https:", "app.example.com");
    expect(wsUrl("ws/passports")).toBe("wss://app.example.com/ws/passports");
  });

  it("does not produce a double slash when the path has a leading slash", () => {
    setLocation("http:", "host:8080");
    expect(wsUrl("/ws/passports")).toBe("ws://host:8080/ws/passports");
  });

  it("never emits a hardcoded :8000 backend port", () => {
    setLocation("https:", "proxy.example.com");
    expect(wsUrl("/ws/brain")).not.toContain(":8000");
    setLocation("http:", "localhost:5173");
    expect(wsUrl("/ws/brain")).not.toContain(":8000");
  });
});
