import type { ProviderMetadata, SecretMetadata } from "@/lib/vaultTypes";
import type { ProviderUiPhase } from "@/state/settings.store";

import { StatusPill, type PillVariant } from "@/components/settings/StatusPill";

export type ProviderCardProps = {
  provider: ProviderMetadata;
  secret: SecretMetadata | undefined;
  phase: ProviderUiPhase;
  vaultLocked: boolean;
  onConnect: () => void;
  onTest: () => void;
  onRemove: () => void;
};

function initials(displayName: string): string {
  const parts = displayName.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return displayName.slice(0, 2).toUpperCase() || "??";
}

function formatRelativeTime(iso: string | null): string {
  if (!iso) return "Never";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "Never";
  const sec = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (sec < 45) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 48) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  return `${day}d ago`;
}

function pillVariant(secret: SecretMetadata | undefined, phase: ProviderUiPhase): PillVariant {
  if (phase === "testing" || phase === "saving") return "initializing";
  if (!secret) return "untested";
  const s = secret.status;
  if (s === "valid" || s === "invalid" || s === "expired" || s === "untested") return s;
  return "untested";
}

export function ProviderCard({
  provider,
  secret,
  phase,
  vaultLocked,
  onConnect,
  onTest,
  onRemove,
}: ProviderCardProps) {
  const connected = Boolean(secret);
  const busy = phase !== "idle";
  const variant = pillVariant(secret, phase);
  const invalidTooltip =
    secret?.status === "invalid"
      ? "Credential failed verification — replace the key or check provider status."
      : undefined;

  return (
    <article className="flex flex-col gap-4 rounded-xl border border-[#1a3550]/65 bg-[#06101b]/72 px-4 py-4 shadow-[0_12px_40px_rgba(0,0,0,0.35)] backdrop-blur-md sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-start gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-[#020711]/90 font-mono text-[12px] font-semibold text-[#E8F0FF]/90">
          {initials(provider.display_name)}
        </div>
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-mono text-[15px] font-semibold text-[#E8F0FF]">{provider.display_name}</h3>
            {connected ? (
              <StatusPill variant={variant} title={invalidTooltip} />
            ) : (
              <span className="font-mono text-[11px] uppercase tracking-wider text-[#6b7c99]">Not connected</span>
            )}
          </div>
          <p className="mt-1 font-mono text-[11px] text-[#7f90b3]">{provider.id}</p>
          {connected ? (
            <p className="mt-2 font-mono text-[12px] text-[#9aa8c4]">
              Last tested: <span className="text-[#c9d4ea]">{formatRelativeTime(secret!.last_tested_at)}</span>
            </p>
          ) : null}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 sm:justify-end">
        {!connected ? (
          <button
            type="button"
            disabled={vaultLocked || busy}
            onClick={onConnect}
            className="rounded-lg bg-[#00E5D8]/18 px-4 py-2 font-mono text-[13px] font-semibold text-[#00E5D8] shadow-[0_0_18px_rgba(0,229,216,0.18)] transition hover:bg-[#00E5D8]/26 disabled:cursor-not-allowed disabled:opacity-35"
          >
            Connect
          </button>
        ) : (
          <>
            <button
              type="button"
              disabled={vaultLocked || busy}
              onClick={onTest}
              className="rounded-lg border border-[#1a3550]/85 px-4 py-2 font-mono text-[13px] text-[#c9d4ea] transition hover:border-[#00E5D8]/45 hover:text-white disabled:opacity-35"
            >
              {phase === "testing" ? (
                <span className="inline-flex items-center gap-2">
                  <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-[#00E5D8]/30 border-t-[#00E5D8]" />
                  Testing…
                </span>
              ) : (
                "Test"
              )}
            </button>
            <button
              type="button"
              disabled={vaultLocked || busy}
              onClick={onRemove}
              className="rounded-lg border border-red-500/35 px-4 py-2 font-mono text-[13px] text-red-200/95 transition hover:border-red-400/55 hover:text-white disabled:opacity-35"
            >
              {phase === "removing" ? "Removing…" : "Remove"}
            </button>
          </>
        )}
      </div>
    </article>
  );
}
