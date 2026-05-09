import { useEffect } from "react";

import { AddKeyDialog } from "@/components/settings/AddKeyDialog";
import { ProviderCard } from "@/components/settings/ProviderCard";
import { SectionHeader } from "@/components/settings/SectionHeader";
import {
  secretForProvider,
  useSettingsStore,
  visibleProviders,
} from "@/state/settings.store";

export function SettingsPage() {
  const providers = useSettingsStore((s) => s.providers);
  const secrets = useSettingsStore((s) => s.secrets);
  const vaultLocked = useSettingsStore((s) => s.vaultLocked);
  const bootstrapError = useSettingsStore((s) => s.bootstrapError);
  const providerPhase = useSettingsStore((s) => s.providerPhase);
  const connectTarget = useSettingsStore((s) => s.connectTarget);
  const dialogError = useSettingsStore((s) => s.dialogError);

  const loadSettingsData = useSettingsStore((s) => s.loadSettingsData);
  const openConnectDialog = useSettingsStore((s) => s.openConnectDialog);
  const closeConnectDialog = useSettingsStore((s) => s.closeConnectDialog);
  const saveAndTestNewKey = useSettingsStore((s) => s.saveAndTestNewKey);
  const runTest = useSettingsStore((s) => s.runTest);
  const removeSecret = useSettingsStore((s) => s.removeSecret);

  useEffect(() => {
    void loadSettingsData();
  }, [loadSettingsData]);

  const { llm, connectors } = visibleProviders(providers);

  return (
    <div className="h-full overflow-y-auto px-8 pb-24 pt-8">
      <header className="mb-6 border-b border-[#1a3550]/55 pb-6">
        <h1 className="font-mono text-2xl font-semibold tracking-tight text-[#E8F0FF]">Settings</h1>
        <p className="mt-2 max-w-2xl text-[14px] leading-relaxed text-[#9aa8c4]">
          Manage API keys for LLMs and connectors. Keys are encrypted at rest; only status metadata is shown here.
        </p>
      </header>

      {vaultLocked ? (
        <div
          role="alert"
          className="mb-8 rounded-xl border border-amber-500/45 bg-amber-500/10 px-4 py-4 font-mono text-[13px] text-amber-100"
        >
          Vault is locked. Run{" "}
          <code className="rounded bg-black/30 px-1.5 py-0.5 text-[12px] text-[#00E5D8]">
            python -m axiom.cli vault init
          </code>{" "}
          and reload.
        </div>
      ) : null}

      {bootstrapError && !vaultLocked ? (
        <div className="mb-6 rounded-xl border border-red-500/45 bg-red-500/10 px-4 py-3 font-mono text-[13px] text-red-100">
          {bootstrapError}
        </div>
      ) : null}

      <SectionHeader title="API Keys" subtitle="Language model providers used by classification and agents." />
      <div className="flex flex-col gap-3">
        {llm.map((p) => (
          <ProviderCard
            key={p.id}
            provider={p}
            secret={secretForProvider(secrets, p.id)}
            phase={providerPhase[p.id] ?? "idle"}
            vaultLocked={vaultLocked}
            onConnect={() => openConnectDialog(p)}
            onTest={() => void runTest(p.id)}
            onRemove={() => {
              if (window.confirm(`Remove ${p.display_name} credential?`)) void removeSecret(p.id);
            }}
          />
        ))}
      </div>

      <SectionHeader title="Connectors" subtitle="Integrations for ingestion and workflows." />
      <div className="flex flex-col gap-3">
        {connectors.map((p) => (
          <ProviderCard
            key={p.id}
            provider={p}
            secret={secretForProvider(secrets, p.id)}
            phase={providerPhase[p.id] ?? "idle"}
            vaultLocked={vaultLocked}
            onConnect={() => openConnectDialog(p)}
            onTest={() => void runTest(p.id)}
            onRemove={() => {
              if (window.confirm(`Remove ${p.display_name} credential?`)) void removeSecret(p.id);
            }}
          />
        ))}
      </div>

      {connectTarget ? (
        <AddKeyDialog
          provider={connectTarget}
          vaultLocked={vaultLocked}
          phase={providerPhase[connectTarget.id] ?? "idle"}
          dialogError={dialogError}
          onCancel={() => closeConnectDialog()}
          onSaveAndTest={async (plaintext) => {
            await saveAndTestNewKey(connectTarget.id, plaintext);
          }}
        />
      ) : null}
    </div>
  );
}
