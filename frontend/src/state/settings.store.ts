import { create } from "zustand";

import { disconnectLLMKey, listLLMKeys, saveLLMKey, testLLMKey } from "@/lib/llmKeysClient";
import type { ProviderMetadata, SecretMetadata } from "@/lib/vaultTypes";

export type ActiveView = "brain" | "settings";

/** Per-provider UI busy flags — Connect/Test/remove flows */
export type ProviderUiPhase = "idle" | "saving" | "testing" | "removing";

type SettingsState = {
  activeView: ActiveView;
  providers: ProviderMetadata[];
  secrets: SecretMetadata[];
  vaultLocked: boolean;
  bootstrapError: string | null;
  providerPhase: Record<string, ProviderUiPhase>;
  dialogError: string | null;
  connectTarget: ProviderMetadata | null;

  setActiveView: (view: ActiveView) => void;
  openConnectDialog: (provider: ProviderMetadata) => void;
  closeConnectDialog: () => void;
  setDialogError: (message: string | null) => void;
  /** Testing-only / explicit banner */
  setVaultLocked: (locked: boolean) => void;

  loadSettingsData: () => Promise<void>;
  saveAndTestNewKey: (providerId: string, plaintext: string) => Promise<void>;
  runTest: (providerId: string) => Promise<void>;
  removeSecret: (providerId: string) => Promise<void>;
};

const DEFAULT_KEY_NAME = "default";

const LLM_PROVIDERS: ProviderMetadata[] = [
  {
    id: "anthropic",
    display_name: "Anthropic",
    kind: "llm",
    credential_shape: [{ name: "api_key", label: "API Key", secret: true }],
    docs_url: "https://console.anthropic.com/settings/keys",
    verify_endpoint: "GET /v1/models",
  },
  {
    id: "groq",
    display_name: "Groq",
    kind: "llm",
    credential_shape: [{ name: "api_key", label: "API Key", secret: true }],
    docs_url: "https://console.groq.com/keys",
    verify_endpoint: "GET /openai/v1/models",
  },
  {
    id: "mistral",
    display_name: "Mistral",
    kind: "llm",
    credential_shape: [{ name: "api_key", label: "API Key", secret: true }],
    docs_url: "https://console.mistral.ai/api-keys",
    verify_endpoint: "GET /v1/models",
  },
  {
    id: "openai",
    display_name: "OpenAI",
    kind: "llm",
    credential_shape: [{ name: "api_key", label: "API Key", secret: true }],
    docs_url: "https://platform.openai.com/api-keys",
    verify_endpoint: "GET /v1/models",
  },
];

function mergeSecret(list: SecretMetadata[], next: SecretMetadata): SecretMetadata[] {
  const without = list.filter((s) => !(s.provider_id === next.provider_id && s.key_name === next.key_name));
  return [...without, next].sort((a, b) => a.provider_id.localeCompare(b.provider_id) || a.key_name.localeCompare(b.key_name));
}

function formatSettingsError(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

function toSecret(meta: {
  provider: string;
  key_fingerprint: string;
  connected_at: string;
  last_tested_at: string | null;
  last_test_status: "valid" | "invalid" | "untested";
}): SecretMetadata {
  return {
    id: meta.provider,
    provider_id: meta.provider,
    key_name: DEFAULT_KEY_NAME,
    status: meta.last_test_status,
    last_tested_at: meta.last_tested_at,
    created_at: meta.connected_at,
    updated_at: meta.last_tested_at ?? meta.connected_at,
  };
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  activeView: "brain",
  providers: [],
  secrets: [],
  vaultLocked: false,
  bootstrapError: null,
  providerPhase: {},
  dialogError: null,
  connectTarget: null,

  setActiveView: (view) => set({ activeView: view }),

  openConnectDialog: (provider) => set({ connectTarget: provider, dialogError: null }),

  closeConnectDialog: () => set({ connectTarget: null, dialogError: null }),

  setDialogError: (message) => set({ dialogError: message }),

  setVaultLocked: (locked) => set({ vaultLocked: locked }),

  loadSettingsData: async () => {
    set({ bootstrapError: null });
    try {
      const keys = await listLLMKeys();
      set({
        providers: LLM_PROVIDERS,
        secrets: keys.map(toSecret),
        vaultLocked: false,
      });
    } catch (err) {
      set({ providers: LLM_PROVIDERS, bootstrapError: formatSettingsError(err) });
    }
  },

  saveAndTestNewKey: async (providerId, plaintext) => {
    const { connectTarget } = get();
    set({ dialogError: null });
    if (!connectTarget || connectTarget.id !== providerId) return;

    set((s) => ({
      providerPhase: { ...s.providerPhase, [providerId]: "saving" },
    }));

    try {
      const stored = toSecret(await saveLLMKey(providerId, plaintext));
      set((s) => ({
        secrets: mergeSecret(s.secrets, stored),
        providerPhase: { ...s.providerPhase, [providerId]: "testing" },
      }));

      const tested = toSecret(await testLLMKey(providerId));
      set((s) => ({
        secrets: mergeSecret(s.secrets, tested),
        providerPhase: { ...s.providerPhase, [providerId]: "idle" },
        connectTarget: null,
      }));
    } catch (err) {
      set((s) => ({
        providerPhase: { ...s.providerPhase, [providerId]: "idle" },
        dialogError: formatSettingsError(err),
      }));
    }
  },

  runTest: async (providerId) => {
    set((s) => ({
      providerPhase: { ...s.providerPhase, [providerId]: "testing" },
    }));
    try {
      const tested = toSecret(await testLLMKey(providerId));
      set((s) => ({
        secrets: mergeSecret(s.secrets, tested),
        providerPhase: { ...s.providerPhase, [providerId]: "idle" },
      }));
    } catch (err) {
      set((s) => ({
        providerPhase: { ...s.providerPhase, [providerId]: "idle" },
        bootstrapError: formatSettingsError(err),
      }));
    }
  },

  removeSecret: async (providerId) => {
    set((s) => ({
      providerPhase: { ...s.providerPhase, [providerId]: "removing" },
    }));
    try {
      await disconnectLLMKey(providerId);
      set((s) => ({
        secrets: s.secrets.filter((x) => !(x.provider_id === providerId && x.key_name === DEFAULT_KEY_NAME)),
        providerPhase: { ...s.providerPhase, [providerId]: "idle" },
      }));
    } catch (err) {
      set((s) => ({
        providerPhase: { ...s.providerPhase, [providerId]: "idle" },
        bootstrapError: formatSettingsError(err),
      }));
    }
  },
}));

/** Visible providers on Settings — LLM + connector only (hide oauth until 5.13.5) */
export function visibleProviders(providers: ProviderMetadata[]): {
  llm: ProviderMetadata[];
  connectors: ProviderMetadata[];
} {
  const llm = providers.filter((p) => p.kind === "llm").sort((a, b) => a.id.localeCompare(b.id));
  const connectors = providers
    .filter((p) => p.kind === "connector")
    .sort((a, b) => a.id.localeCompare(b.id));
  return { llm, connectors };
}

export function secretForProvider(secrets: SecretMetadata[], providerId: string): SecretMetadata | undefined {
  return secrets.find((s) => s.provider_id === providerId && s.key_name === DEFAULT_KEY_NAME);
}
