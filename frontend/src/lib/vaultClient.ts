/**
 * Thin typed wrapper over vault HTTP API (Phase 5.13.2).
 * Uses relative `/api/*` URLs — Vite dev proxy forwards to backend.
 */

import type {
  ProviderMetadata,
  SecretMetadata,
  StoreSecretBody,
  VerifyResult,
} from "@/lib/vaultTypes";

const JSON_HEADERS = { "Content-Type": "application/json" } as const;

export type VaultErrorDetail = string | Record<string, unknown>;

export class VaultApiError extends Error {
  readonly status: number;
  readonly detail: VaultErrorDetail;

  constructor(message: string, status: number, detail: VaultErrorDetail) {
    super(message);
    this.name = "VaultApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** HTTP 503 — vault master key missing / malformed */
export class VaultLockedError extends VaultApiError {
  constructor(detail: VaultErrorDetail) {
    super("Vault locked", 503, detail);
    this.name = "VaultLockedError";
  }
}

/** HTTP 404 — secret or provider not found */
export class VaultNotFoundError extends VaultApiError {
  constructor(detail: VaultErrorDetail) {
    super("Not found", 404, detail);
    this.name = "VaultNotFoundError";
  }
}

/** HTTP 409 — duplicate secret */
export class VaultConflictError extends VaultApiError {
  constructor(detail: VaultErrorDetail) {
    super("Conflict", 409, detail);
    this.name = "VaultConflictError";
  }
}

function detailToString(detail: VaultErrorDetail): string {
  if (typeof detail === "string") return detail;
  try {
    return JSON.stringify(detail);
  } catch {
    return String(detail);
  }
}

function mapStatusToError(status: number, detail: VaultErrorDetail): VaultApiError {
  if (status === 503) return new VaultLockedError(detail);
  if (status === 404) return new VaultNotFoundError(detail);
  if (status === 409) return new VaultConflictError(detail);
  return new VaultApiError(`HTTP ${status}`, status, detail);
}

async function parseJsonSafe(text: string): Promise<unknown> {
  if (!text.trim()) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

async function vaultRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      ...(init?.body ? JSON_HEADERS : {}),
      ...(init?.headers ?? {}),
    },
  });

  const text = await res.text();
  const parsed = await parseJsonSafe(text);

  if (!res.ok) {
    const rawDetail =
      parsed !== null && typeof parsed === "object" && parsed !== null && "detail" in parsed
        ? (parsed as { detail: VaultErrorDetail }).detail
        : typeof parsed === "string"
          ? parsed
          : text || `HTTP ${res.status}`;
    throw mapStatusToError(res.status, rawDetail);
  }

  return parsed as T;
}

export async function listProviders(): Promise<ProviderMetadata[]> {
  const data = await vaultRequest<{ providers: ProviderMetadata[] }>("/api/providers");
  return data.providers;
}

export async function getProvider(providerId: string): Promise<ProviderMetadata> {
  const data = await vaultRequest<{ provider: ProviderMetadata }>(
    `/api/providers/${encodeURIComponent(providerId)}`,
  );
  return data.provider;
}

export async function listSecrets(): Promise<SecretMetadata[]> {
  const data = await vaultRequest<{ secrets: SecretMetadata[] }>("/api/secrets");
  return data.secrets;
}

export async function storeSecret(body: StoreSecretBody): Promise<SecretMetadata> {
  const data = await vaultRequest<{ secret: SecretMetadata }>("/api/secrets", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return data.secret;
}

export async function deleteSecret(providerId: string, keyName: string): Promise<void> {
  await vaultRequest<{ deleted: boolean }>(
    `/api/secrets/${encodeURIComponent(providerId)}/${encodeURIComponent(keyName)}`,
    { method: "DELETE" },
  );
}

export async function testSecret(
  providerId: string,
  keyName: string,
): Promise<{ result: VerifyResult; secret: SecretMetadata }> {
  const data = await vaultRequest<{ result: VerifyResult; secret: SecretMetadata }>(
    `/api/secrets/${encodeURIComponent(providerId)}/${encodeURIComponent(keyName)}/test`,
    { method: "POST" },
  );
  return data;
}

export async function rotateSecret(body: StoreSecretBody): Promise<SecretMetadata> {
  const { provider_id, key_name } = body;
  const data = await vaultRequest<{ secret: SecretMetadata }>(
    `/api/secrets/${encodeURIComponent(provider_id)}/${encodeURIComponent(key_name)}`,
    {
      method: "PUT",
      body: JSON.stringify(body),
    },
  );
  return data.secret;
}

/** Normalize FastAPI / pydantic error detail for inline UI */
export function formatVaultError(err: unknown): string {
  if (err instanceof VaultApiError) return detailToString(err.detail);
  if (err instanceof Error) return err.message;
  return String(err);
}
