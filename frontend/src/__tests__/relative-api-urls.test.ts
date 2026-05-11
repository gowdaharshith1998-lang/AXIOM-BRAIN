/// <reference types="vite/client" />

import { describe, expect, it } from "vitest";

import brainSource from "../components/Brain.tsx?raw";
import studioClientSource from "../lib/studioClient.ts?raw";
import viteConfigSource from "../../vite.config.ts?raw";

const ABSOLUTE_API_ORIGIN = /https?:\/\/(?:127\.0\.0\.1|localhost):8000\/api/;

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
