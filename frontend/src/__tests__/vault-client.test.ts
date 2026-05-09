import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  VaultApiError,
  VaultConflictError,
  VaultLockedError,
  VaultNotFoundError,
  deleteSecret,
  getProvider,
  listProviders,
  listSecrets,
  rotateSecret,
  storeSecret,
  testSecret,
} from "@/lib/vaultClient";
import type { ProviderMetadata, SecretMetadata } from "@/lib/vaultTypes";

const sampleProvider: ProviderMetadata = {
  id: "anthropic",
  display_name: "Anthropic",
  kind: "llm",
  credential_shape: [{ name: "api_key", label: "API Key", secret: true }],
  docs_url: "https://example.com",
  verify_endpoint: "POST https://api.example.com",
};

const sampleSecret: SecretMetadata = {
  id: "s1",
  provider_id: "anthropic",
  key_name: "default",
  status: "valid",
  last_tested_at: null,
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
};

describe("vaultClient", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function mockJsonResponse(status: number, body: unknown) {
    fetchMock.mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      text: async () => JSON.stringify(body),
    });
  }

  it("listProviders GET /api/providers", async () => {
    mockJsonResponse(200, { providers: [sampleProvider] });
    const rows = await listProviders();
    expect(fetchMock).toHaveBeenCalledWith("/api/providers", expect.any(Object));
    expect(rows).toHaveLength(1);
    expect(rows[0].id).toBe("anthropic");
  });

  it("getProvider GET /api/providers/:id", async () => {
    mockJsonResponse(200, { provider: sampleProvider });
    const p = await getProvider("anthropic");
    expect(fetchMock).toHaveBeenCalledWith("/api/providers/anthropic", expect.any(Object));
    expect(p.id).toBe("anthropic");
  });

  it("listSecrets GET /api/secrets", async () => {
    mockJsonResponse(200, { secrets: [sampleSecret] });
    const secrets = await listSecrets();
    expect(fetchMock).toHaveBeenCalledWith("/api/secrets", expect.any(Object));
    expect(secrets[0].key_name).toBe("default");
  });

  it("storeSecret POST /api/secrets with JSON body", async () => {
    mockJsonResponse(201, { secret: sampleSecret });
    const meta = await storeSecret({
      provider_id: "anthropic",
      key_name: "default",
      plaintext: "sk-test",
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/secrets",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          provider_id: "anthropic",
          key_name: "default",
          plaintext: "sk-test",
        }),
      }),
    );
    expect(meta.provider_id).toBe("anthropic");
  });

  it("deleteSecret DELETE /api/secrets/:provider/:key", async () => {
    mockJsonResponse(200, { deleted: true });
    await deleteSecret("anthropic", "default");
    expect(fetchMock).toHaveBeenCalledWith("/api/secrets/anthropic/default", expect.objectContaining({ method: "DELETE" }));
  });

  it("testSecret POST /api/secrets/:provider/:key/test", async () => {
    mockJsonResponse(200, {
      result: { status: "ok", detail: null },
      secret: sampleSecret,
    });
    const out = await testSecret("anthropic", "default");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/secrets/anthropic/default/test",
      expect.objectContaining({ method: "POST" }),
    );
    expect(out.result.status).toBe("ok");
  });

  it("rotateSecret PUT /api/secrets/:provider/:key", async () => {
    mockJsonResponse(200, { secret: sampleSecret });
    await rotateSecret({
      provider_id: "anthropic",
      key_name: "default",
      plaintext: "new",
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/secrets/anthropic/default",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          provider_id: "anthropic",
          key_name: "default",
          plaintext: "new",
        }),
      }),
    );
  });

  it("maps 503 to VaultLockedError", async () => {
    mockJsonResponse(503, { detail: "Vault locked. Run python -m axiom.cli vault init." });
    await expect(listSecrets()).rejects.toBeInstanceOf(VaultLockedError);
  });

  it("maps 404 to VaultNotFoundError", async () => {
    mockJsonResponse(404, { detail: "not found" });
    await expect(getProvider("nope")).rejects.toBeInstanceOf(VaultNotFoundError);
  });

  it("maps 409 to VaultConflictError", async () => {
    mockJsonResponse(409, { detail: "duplicate" });
    await expect(storeSecret({ provider_id: "x", key_name: "y", plaintext: "z" })).rejects.toBeInstanceOf(VaultConflictError);
  });

  it("maps other statuses to VaultApiError", async () => {
    mockJsonResponse(418, { detail: "short" });
    await expect(listProviders()).rejects.toBeInstanceOf(VaultApiError);
  });
});
