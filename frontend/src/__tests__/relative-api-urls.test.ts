/// <reference types="vite/client" />

import { describe, expect, it } from "vitest";

import brainSource from "../components/Brain.tsx?raw";
import studioClientSource from "../lib/studioClient.ts?raw";
import viteConfigSource from "../../vite.config.ts?raw";
import agentsClientSource from "../lib/agentsClient.ts?raw";
import approvalsClientSource from "../lib/approvalsClient.ts?raw";
import connectorsPageSource from "../pages/ConnectorsPage.tsx?raw";
import connectorsStoreSource from "../state/connectors.store.ts?raw";
import llmKeysClientSource from "../lib/llmKeysClient.ts?raw";
import passportsClientSource from "../lib/passportsClient.ts?raw";
import passportsPageSource from "../pages/PassportsPage.tsx?raw";
import skillsClientSource from "../lib/skillsClient.ts?raw";
import vaultClientSource from "../lib/vaultClient.ts?raw";
import watchdogClientSource from "../lib/watchdogClient.ts?raw";

const ABSOLUTE_API_ORIGIN = /https?:\/\/(?:127\.0\.0\.1|localhost):8000\/api/;

// All non-test app sources must route HTTP through the shared auth wrapper and
// WS through the auth-aware helper, never bare fetch( / new WebSocket(.
const AUTH_ROUTED_SOURCES: Array<[string, string]> = [
  ["agentsClient", agentsClientSource],
  ["approvalsClient", approvalsClientSource],
  ["connectorsPage", connectorsPageSource],
  ["connectorsStore", connectorsStoreSource],
  ["llmKeysClient", llmKeysClientSource],
  ["passportsClient", passportsClientSource],
  ["skillsClient", skillsClientSource],
  ["vaultClient", vaultClientSource],
  ["watchdogClient", watchdogClientSource],
];

describe("relative API URLs", () => {
  it("brain_fetches_relative_paths_only", () => {
    expect(brainSource).toContain('fetchJson<unknown[]>("/api/entities")');
    expect(brainSource).toContain('fetchJson<unknown[]>("/api/edges")');
    expect(brainSource).toContain('fetchJson<Record<string, ClusterHealthSnapshot>>("/api/cluster_health")');
    expect(brainSource).not.toMatch(ABSOLUTE_API_ORIGIN);
  });

  it("studio_client_no_absolute_urls", () => {
    expect(studioClientSource).toContain('request<{ settings: StudioSettings }>("/api/internal/settings")');
    expect(studioClientSource).toContain('request<{ status: string }>("/api/health")');
    expect(studioClientSource).not.toMatch(ABSOLUTE_API_ORIGIN);
  });

  it("vite_proxy_config_intact", () => {
    expect(viteConfigSource).toContain('"/api": "http://localhost:8000"');
    expect(viteConfigSource).toContain('target: "ws://localhost:8000"');
  });
});

describe("client auth routing (P1-15)", () => {
  it.each(AUTH_ROUTED_SOURCES)("%s routes HTTP through the shared wrapper", (_name, source) => {
    // No bare fetch( — every call goes through request() / requestRaw().
    expect(source).not.toMatch(/(?<![A-Za-z_])fetch\(/);
    expect(source).toContain('from "@/lib/http"');
  });

  it("brain fetches go through the shared http wrapper", () => {
    expect(brainSource).toContain('import { request as fetchJson } from "@/lib/http"');
    expect(brainSource).not.toMatch(/(?<![A-Za-z_])fetch\(/);
  });

  it.each([
    ["connectorsPage", connectorsPageSource],
    ["passportsPage", passportsPageSource],
  ])("%s opens WebSockets through wsConnect, never bare new WebSocket(", (_name, source) => {
    expect(source).not.toContain("new WebSocket(");
    expect(source).toContain('from "@/lib/ws"');
  });
});
