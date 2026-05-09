import { useMemo, useState } from "react";

import type { ProviderMetadata } from "@/lib/vaultTypes";
import type { ProviderUiPhase } from "@/state/settings.store";

export type AddKeyDialogProps = {
  provider: ProviderMetadata;
  vaultLocked: boolean;
  phase: ProviderUiPhase;
  dialogError: string | null;
  onCancel: () => void;
  onSaveAndTest: (plaintext: string) => Promise<void>;
};

export function AddKeyDialog({
  provider,
  vaultLocked,
  phase,
  dialogError,
  onCancel,
  onSaveAndTest,
}: AddKeyDialogProps) {
  const fields = provider.credential_shape;
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(fields.map((f) => [f.name, ""])),
  );
  const [showSecret, setShowSecret] = useState(false);

  const busy = phase === "saving" || phase === "testing";

  const plaintextPayload = useMemo(() => {
    if (fields.length === 1) return values[fields[0].name] ?? "";
    return JSON.stringify(
      Object.fromEntries(fields.map((f) => [f.name, values[f.name] ?? ""])),
    );
  }, [fields, values]);

  const canSubmit = useMemo(() => {
    if (vaultLocked || busy) return false;
    return fields.every((f) => (values[f.name] ?? "").trim().length > 0);
  }, [busy, fields, values, vaultLocked]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    await onSaveAndTest(plaintextPayload);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/72 backdrop-blur-sm px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="connect-dialog-title"
        className="w-full max-w-md rounded-xl border border-[#1a3550]/80 bg-[#06101b]/95 p-6 shadow-[0_0_60px_rgba(0,0,0,0.55)]"
      >
        <h3 id="connect-dialog-title" className="font-mono text-lg font-semibold text-[#E8F0FF]">
          Connect {provider.display_name}
        </h3>
        <p className="mt-2 text-[13px] leading-snug text-[#9aa8c4]">
          Credentials stay encrypted server-side. They never appear in the UI after you close this dialog.
        </p>

        <form onSubmit={(ev) => void handleSubmit(ev)} className="mt-6 space-y-4">
          {fields.map((field) => {
            const id = `cred-${provider.id}-${field.name}`;
            return (
              <div key={field.name}>
                <label htmlFor={id} className="block font-mono text-[11px] uppercase tracking-wider text-[#8d9bbb]">
                  {field.label}
                </label>
                <input
                  id={id}
                  name={field.name}
                  type={field.secret ? (showSecret ? "text" : "password") : "text"}
                  autoComplete="off"
                  value={values[field.name] ?? ""}
                  onChange={(ev) =>
                    setValues((prev) => ({
                      ...prev,
                      [field.name]: ev.target.value,
                    }))
                  }
                  className="mt-1.5 w-full rounded-lg border border-[#1a3550]/80 bg-[#020711]/90 px-3 py-2 font-mono text-[13px] text-[#E8F0FF] outline-none ring-[#00E5D8]/25 placeholder:text-[#5f6f90] focus:border-[#00E5D8]/55 focus:ring-2"
                />
                {field.secret ? (
                  <label className="mt-2 flex cursor-pointer items-center gap-2 text-[12px] text-[#9aa8c4]">
                    <input
                      type="checkbox"
                      className="accent-[#00E5D8]"
                      checked={showSecret}
                      onChange={(ev) => setShowSecret(ev.target.checked)}
                    />
                    Show value
                  </label>
                ) : null}
              </div>
            );
          })}

          <p className="text-[12px] text-[#7f90b3]">
            Get your key at{" "}
            <a href={provider.docs_url} target="_blank" rel="noreferrer" className="text-[#00E5D8] hover:underline">
              docs ↗
            </a>
          </p>

          {dialogError ? (
            <p className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 font-mono text-[12px] text-red-200">
              {dialogError}
            </p>
          ) : null}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onCancel}
              disabled={busy}
              className="rounded-lg border border-[#1a3550]/80 px-4 py-2 font-mono text-[13px] text-[#c9d4ea] transition hover:border-[#2f486b]/90 hover:text-white disabled:opacity-40"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!canSubmit}
              className="inline-flex items-center gap-2 rounded-lg bg-[#00E5D8]/18 px-4 py-2 font-mono text-[13px] font-semibold text-[#00E5D8] shadow-[0_0_22px_rgba(0,229,216,0.22)] transition hover:bg-[#00E5D8]/26 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {busy ? (
                <>
                  <Spinner />
                  Testing…
                </>
              ) : (
                "Save & Test"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Spinner() {
  return (
    <svg className="h-4 w-4 animate-spin text-[#00E5D8]" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" fill="none" opacity="0.25" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" fill="none" strokeLinecap="round" />
    </svg>
  );
}
