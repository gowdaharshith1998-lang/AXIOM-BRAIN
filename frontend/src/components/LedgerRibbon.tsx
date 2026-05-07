import { useBrainStore } from "@/state/brain.store";

function shortHash(value: string): string {
  return `0x${value.slice(0, 4)}...${value.slice(-4)}`;
}

export function LedgerRibbon() {
  const receipts = useBrainStore((s) => s.receipts);
  const rows = receipts.slice(0, 5);
  const root = rows[0]?.merkle_root ?? "8c2d000000000000000000000000ff04";
  return (
    <aside className="fixed bottom-28 right-[336px] z-30 w-[300px] border border-white/10 bg-[#0a0c14]/75 p-3 font-mono text-[10px] text-white/70 shadow-2xl backdrop-blur">
      <div className="mb-2 flex justify-between text-white/85">
        <span className="uppercase tracking-[0.2em]">Ledger</span>
        <span>{receipts.length || 89}</span>
      </div>
      <div className="space-y-1">
        {(rows.length ? rows : fallbackRows()).map((receipt) => (
          <div key={receipt.receipt_id} className="grid grid-cols-[88px_42px_54px_1fr] gap-1 animate-[axiom-ledger-slide_350ms_ease-out]">
            <span>{shortHash(receipt.receipt_id)}</span>
            <span className={receipt.decision === "deny" ? "text-[#ef4444]" : "text-[#22c55e]"}>{receipt.decision}</span>
            <span>{receipt.agent_name}</span>
            <span className="text-white/35">now</span>
          </div>
        ))}
      </div>
      <div className="mt-3 truncate text-white/40">merkle root {shortHash(root)}</div>
    </aside>
  );
}

function fallbackRows() {
  return [
    { receipt_id: "7a3f000000000000000000000000e2c9", decision: "allow" as const, agent_name: "claude", merkle_root: "8c2d000000000000000000000000ff04", action_id: "demo", timestamp: "t" },
    { receipt_id: "4b810000000000000000000000009d12", decision: "allow" as const, agent_name: "cursor", merkle_root: "8c2d000000000000000000000000ff04", action_id: "demo2", timestamp: "t" },
    { receipt_id: "9f2a0000000000000000000000001b83", decision: "deny" as const, agent_name: "gpt-5", merkle_root: "8c2d000000000000000000000000ff04", action_id: "demo3", timestamp: "t" },
  ];
}
