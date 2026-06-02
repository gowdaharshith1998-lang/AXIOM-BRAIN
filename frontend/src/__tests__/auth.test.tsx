import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TokenGate } from "@/components/TokenGate";
import { clearApiToken, getApiToken, hasApiToken, setApiToken } from "@/lib/auth";
import { AUTH_REQUIRED_EVENT, request, requestRaw, withAuth } from "@/lib/http";
import { authSubprotocols, WS_AUTH_SUBPROTOCOL, WS_AUTH_TOKEN_PREFIX, wsConnect } from "@/lib/ws";

function mockFetchOnce(status: number, body: unknown = {}): typeof fetch {
  return vi.fn(async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  ) as unknown as typeof fetch;
}

afterEach(() => {
  clearApiToken();
  vi.restoreAllMocks();
});

describe("auth token store", () => {
  it("setApiToken / getApiToken / hasApiToken / clearApiToken roundtrip in memory", () => {
    expect(hasApiToken()).toBe(false);
    setApiToken("secret-token");
    expect(getApiToken()).toBe("secret-token");
    expect(hasApiToken()).toBe(true);
    clearApiToken();
    expect(getApiToken()).toBeNull();
    expect(hasApiToken()).toBe(false);
  });

  it("blank token clears instead of storing", () => {
    setApiToken("real");
    setApiToken("   ");
    expect(hasApiToken()).toBe(false);
  });

  it("does NOT persist to sessionStorage by default", () => {
    setApiToken("in-memory-only");
    expect(window.sessionStorage.getItem("axiom.api-token")).toBeNull();
  });

  it("persists to sessionStorage only when remember=true", () => {
    setApiToken("remembered", true);
    expect(window.sessionStorage.getItem("axiom.api-token")).toBe("remembered");
    clearApiToken();
    expect(window.sessionStorage.getItem("axiom.api-token")).toBeNull();
  });
});

describe("http request() auth header", () => {
  it("adds Authorization: Bearer header when a token is set", async () => {
    const fetchMock = mockFetchOnce(200, { ok: true });
    vi.stubGlobal("fetch", fetchMock);
    setApiToken("abc123");

    await request("/api/anything");

    const [, init] = (fetchMock as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    const headers = new Headers((init as RequestInit).headers);
    expect(headers.get("Authorization")).toBe("Bearer abc123");
    expect((init as RequestInit).credentials).toBe("include");
  });

  it("omits Authorization header when no token is set (cookie mode)", async () => {
    const fetchMock = mockFetchOnce(200, { ok: true });
    vi.stubGlobal("fetch", fetchMock);

    await request("/api/anything");

    const [, init] = (fetchMock as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    const headers = new Headers((init as RequestInit).headers);
    expect(headers.has("Authorization")).toBe(false);
    expect((init as RequestInit).credentials).toBe("include");
  });

  it("does not clobber a caller-supplied Authorization header", () => {
    setApiToken("store-token");
    const init = withAuth({ headers: { Authorization: "Bearer explicit" } });
    const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBe("Bearer explicit");
  });

  it("dispatches axiom:auth-required on 401", async () => {
    const fetchMock = mockFetchOnce(401, { detail: "nope" });
    vi.stubGlobal("fetch", fetchMock);
    const handler = vi.fn();
    window.addEventListener(AUTH_REQUIRED_EVENT, handler);

    await requestRaw("/api/protected");

    expect(handler).toHaveBeenCalledTimes(1);
    window.removeEventListener(AUTH_REQUIRED_EVENT, handler);
  });

  it("dispatches axiom:auth-required on 403", async () => {
    const fetchMock = mockFetchOnce(403);
    vi.stubGlobal("fetch", fetchMock);
    const handler = vi.fn();
    window.addEventListener(AUTH_REQUIRED_EVENT, handler);

    await requestRaw("/api/protected");

    expect(handler).toHaveBeenCalledTimes(1);
    window.removeEventListener(AUTH_REQUIRED_EVENT, handler);
  });

  it("does NOT dispatch axiom:auth-required on a 200 (dev mode)", async () => {
    const fetchMock = mockFetchOnce(200);
    vi.stubGlobal("fetch", fetchMock);
    const handler = vi.fn();
    window.addEventListener(AUTH_REQUIRED_EVENT, handler);

    await requestRaw("/api/open");

    expect(handler).not.toHaveBeenCalled();
    window.removeEventListener(AUTH_REQUIRED_EVENT, handler);
  });
});

describe("wsConnect subprotocol", () => {
  it("passes the auth subprotocol + base64url token when a token is set", () => {
    const calls: Array<{ url: string; protocols?: string | string[] }> = [];
    class MockWS {
      constructor(url: string, protocols?: string | string[]) {
        calls.push({ url, protocols });
      }
    }
    const Original = globalThis.WebSocket;
    globalThis.WebSocket = MockWS as unknown as typeof WebSocket;
    try {
      setApiToken("tok-énçodé");
      wsConnect("/ws/brain");
      expect(calls).toHaveLength(1);
      const protocols = calls[0].protocols as string[];
      expect(Array.isArray(protocols)).toBe(true);
      expect(protocols[0]).toBe(WS_AUTH_SUBPROTOCOL);
      expect(protocols[1].startsWith(WS_AUTH_TOKEN_PREFIX)).toBe(true);
      // base64url alphabet: no '+' '/' '=' padding.
      const encoded = protocols[1].slice(WS_AUTH_TOKEN_PREFIX.length);
      expect(encoded).not.toMatch(/[+/=]/);
    } finally {
      globalThis.WebSocket = Original;
    }
  });

  it("opens without subprotocols when no token is set (cookie mode)", () => {
    const calls: Array<{ url: string; protocols?: string | string[] }> = [];
    class MockWS {
      constructor(url: string, protocols?: string | string[]) {
        calls.push({ url, protocols });
      }
    }
    const Original = globalThis.WebSocket;
    globalThis.WebSocket = MockWS as unknown as typeof WebSocket;
    try {
      wsConnect("/ws/brain");
      expect(calls).toHaveLength(1);
      expect(calls[0].protocols).toBeUndefined();
    } finally {
      globalThis.WebSocket = Original;
    }
  });

  it("authSubprotocols() returns undefined without a token", () => {
    expect(authSubprotocols()).toBeUndefined();
  });
});

describe("TokenGate", () => {
  beforeEach(() => {
    clearApiToken();
  });

  it("is hidden until an auth-required event fires", () => {
    render(<TokenGate />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("appears on axiom:auth-required and disappears after a token is set", async () => {
    render(<TokenGate />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    window.dispatchEvent(new CustomEvent(AUTH_REQUIRED_EVENT, { detail: { status: 401, url: "/x" } }));

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toBeInTheDocument();

    const input = screen.getByLabelText("API Token");
    fireEvent.change(input, { target: { value: "my-token" } });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(getApiToken()).toBe("my-token");
  });

  it("honours the 'remember for this tab' checkbox", async () => {
    render(<TokenGate />);
    window.dispatchEvent(new CustomEvent(AUTH_REQUIRED_EVENT, { detail: { status: 401, url: "/x" } }));
    await screen.findByRole("dialog");

    fireEvent.change(screen.getByLabelText("API Token"), { target: { value: "remembered-token" } });
    fireEvent.click(screen.getByLabelText("Remember for this tab"));
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(window.sessionStorage.getItem("axiom.api-token")).toBe("remembered-token");
  });
});
