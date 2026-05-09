import { create } from "zustand";

import {
  VaultLockedError,
  deleteSecret,
  formatVaultError,
  listProviders,
  listSecrets,
  storeSecret,
  testSecret,
} from "@/lib/vaultClient";
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

function mergeSecret(list: SecretMetadata[], next: SecretMetadata): SecretMetadata[] {
  const without = list.filter((s) => !(s.provider_id === next.provider_id && s.key_name === next.key_name));
  return [...without, next].sort((a, b) => a.provider_id.localeCompare(b.provider_id) || a.key_name.localeCompare(b.key_name));
}

function recordLocked(err: unknown, set: (partial: Partial<SettingsState>) => void): boolean {
  if (err instanceof VaultLockedError) {
    set({ vaultLocked: true });
    return true;
  }
  return false;
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
      const [providers, secrets] = await Promise.all([listProviders(), listSecrets()]);
      set({
        providers,
        secrets,
        vaultLocked: false,
      });
    } catch (err) {
      if (recordLocked(err, set)) {
        set({ bootstrapError: null });
        return;
      }
      set({ bootstrapError: formatVaultError(err) });
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
      const stored = await storeSecret({
        provider_id: providerId,
        key_name: DEFAULT_KEY_NAME,
        plaintext,
      });
      set((s) => ({
        secrets: mergeSecret(s.secrets, stored),
        providerPhase: { ...s.providerPhase, [providerId]: "testing" },
      }));

      const tested = await testSecret(providerId, DEFAULT_KEY_NAME);
      set((s) => ({
        secrets: mergeSecret(s.secrets, tested.secret),
        providerPhase: { ...s.providerPhase, [providerId]: "idle" },
        connectTarget: null,
      }));
    } catch (err) {
      recordLocked(err, set);
      set((s) => ({
        providerPhase: { ...s.providerPhase, [providerId]: "idle" },
        dialogError: formatVaultError(err),
      }));
    }
  },

  runTest: async (providerId) => {
    set((s) => ({
      providerPhase: { ...s.providerPhase, [providerId]: "testing" },
    }));
    try {
      const tested = await testSecret(providerId, DEFAULT_KEY_NAME);
      set((s) => ({
        secrets: mergeSecret(s.secrets, tested.secret),
        providerPhase: { ...s.providerPhase, [providerId]: "idle" },
      }));
    } catch (err) {
      recordLocked(err, set);
      set((s) => ({
        providerPhase: { ...s.providerPhase, [providerId]: "idle" },
        bootstrapError: formatVaultError(err),
      }));
    }
  },

  removeSecret: async (providerId) => {
    set((s) => ({
      providerPhase: { ...s.providerPhase, [providerId]: "removing" },
    }));
    try {
      await deleteSecret(providerId, DEFAULT_KEY_NAME);
      set((s) => ({
        secrets: s.secrets.filter((x) => !(x.provider_id === providerId && x.key_name === DEFAULT_KEY_NAME)),
        providerPhase: { ...s.providerPhase, [providerId]: "idle" },
      }));
    } catch (err) {
      recordLocked(err, set);
      set((s) => ({
        providerPhase: { ...s.providerPhase, [providerId]: "idle" },
        bootstrapError: formatVaultError(err),
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
