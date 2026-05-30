export type LLMProviderId = "anthropic" | "groq" | "mistral" | "openai";

export type LLMKeyMetadata = {
  provider: LLMProviderId;
  key_fingerprint: string;
  connected_at: string;
  last_tested_at: string | null;
  last_test_status: "valid" | "invalid" | "untested";
  demo_flag: boolean;
};

const JSON_HEADERS = { "Content-Type": "application/json" } as const;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    ...init,
    headers: {
      ...(init?.body ? JSON_HEADERS : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string") detail = payload.detail;
    } catch {
      // keep HTTP status fallback
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export async function listLLMKeys(): Promise<LLMKeyMetadata[]> {
  const data = await request<{ keys: LLMKeyMetadata[] }>("/api/internal/llm-keys");
  return data.keys;
}

export async function saveLLMKey(provider: string, key: string): Promise<LLMKeyMetadata> {
  return request<LLMKeyMetadata>("/api/internal/llm-keys", {
    method: "POST",
    body: JSON.stringify({ provider, key }),
  });
}

export async function testLLMKey(provider: string): Promise<LLMKeyMetadata> {
  return request<LLMKeyMetadata>(`/api/internal/llm-keys/${encodeURIComponent(provider)}/test`, {
    method: "POST",
  });
}

export async function disconnectLLMKey(provider: string): Promise<void> {
  await request<{ deleted: boolean }>(`/api/internal/llm-keys/${encodeURIComponent(provider)}`, {
    method: "DELETE",
  });
}
