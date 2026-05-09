import type { SecretStatus } from "@/lib/vaultTypes";

export type PillVariant = SecretStatus | "initializing";

const VARIANT_CLASSES: Record<PillVariant, string> = {
  untested: "border-[#6b7c99]/70 bg-[#0f172a]/80 text-[#c9d4ea]",
  valid: "border-[#00E5D8]/55 bg-[#00E5D8]/10 text-[#00E5D8]",
  invalid: "border-red-500/55 bg-red-500/10 text-red-300",
  expired: "border-amber-500/55 bg-amber-500/10 text-amber-200",
  initializing: "border-[#00E5D8]/40 bg-[#00E5D8]/6 text-[#9cfbf5] animate-pulse",
};

const LABELS: Record<PillVariant, string> = {
  untested: "Untested",
  valid: "Valid",
  invalid: "Invalid",
  expired: "Expired",
  initializing: "Testing…",
};

export type StatusPillProps = {
  variant: PillVariant;
  title?: string;
};

export function StatusPill({ variant, title }: StatusPillProps) {
  return (
    <span
      title={title}
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 font-mono text-[11px] tracking-wide ${VARIANT_CLASSES[variant]}`}
    >
      {LABELS[variant]}
    </span>
  );
}
