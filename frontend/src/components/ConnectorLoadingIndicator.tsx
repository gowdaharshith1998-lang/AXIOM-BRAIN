import { useConnectorsStore } from "@/state/connectors.store";

export function ConnectorLoadingIndicator() {
  const loading = useConnectorsStore((s) => s.loading);
  const error = useConnectorsStore((s) => s.error);

  if (!loading && !error) return null;

  return (
    <div
      className="flex items-center gap-2 rounded-md border border-[#1d3452] bg-[#071328]/90 px-3 py-1.5 text-[11px] text-[#9fb0c8]"
      role="status"
      aria-live="polite"
    >
      {loading ? (
        <>
          <span className="h-2 w-2 animate-pulse rounded-full bg-[#4b9aff]" aria-hidden />
          <span>Checking connectors…</span>
        </>
      ) : (
        <span className="text-[#f6b770]">Connectors: {error}</span>
      )}
    </div>
  );
}
