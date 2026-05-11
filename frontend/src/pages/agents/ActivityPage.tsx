import { useEffect, useMemo, useState } from "react";

import { listRecentReceipts, type ReceiptRow } from "@/lib/agentsClient";
import { AgentsSubPageShell, EmptyState, formatTime, hourBucket } from "@/pages/agents/shared";

function countByDecision(receipts: ReceiptRow[]): Array<[string, number]> {
  const counts = new Map<string, number>();
  for (const receipt of receipts) counts.set(receipt.decision, (counts.get(receipt.decision) ?? 0) + 1);
  return Array.from(counts.entries()).sort(([left], [right]) => left.localeCompare(right));
}

function groupedByHour(receipts: ReceiptRow[]): Array<[string, ReceiptRow[]]> {
  const groups = new Map<string, ReceiptRow[]>();
  for (const receipt of receipts) {
    const key = hourBucket(receipt.created_at ?? receipt.timestamp);
    groups.set(key, [...(groups.get(key) ?? []), receipt]);
  }
  return Array.from(groups.entries()).sort(([left], [right]) => right.localeCompare(left));
}

export function ActivityPage() {
  const [receipts, setReceipts] = useState<ReceiptRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const decisionCounts = useMemo(() => countByDecision(receipts), [receipts]);
  const hourGroups = useMemo(() => groupedByHour(receipts), [receipts]);

  useEffect(() => {
    listRecentReceipts(50)
      .then(setReceipts)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Unable to load activity"));
  }, []);

  return (
    <AgentsSubPageShell title="Activity" subtitle="Recent receipt and agent action log from backend receipts.">
      {error ? <EmptyState>Unable to load activity: {error}</EmptyState> : null}
      <section className="agents-panel">
        <div className="agents-panel-head">
          <h2>Decision Distribution <span>{receipts.length}</span></h2>
        </div>
        {receipts.length ? (
          <div className="agents-drawer-summary">
            {decisionCounts.map(([decision, count]) => <span key={decision}>{decision}: {count}</span>)}
          </div>
        ) : <EmptyState>No recent receipt activity.</EmptyState>}
      </section>
      <section className="agents-panel">
        <div className="agents-panel-head">
          <h2>Receipt Log</h2>
        </div>
        {hourGroups.map(([hour, rows]) => (
          <div className="agents-table" key={hour}>
            <div className="agents-panel-head">
              <h2>{hour} <span>{rows.length} {rows.length === 1 ? "receipt" : "receipts"}</span></h2>
            </div>
            <div className="agents-table-head">
              <span>Action</span>
              <span>Agent</span>
              <span>Decision</span>
              <span>Time</span>
            </div>
            {rows.map((receipt) => (
              <div className="agents-table-row" key={receipt.receipt_id}>
                <span>{receipt.action_id}</span>
                <span>{receipt.agent_name}</span>
                <span>{receipt.decision}</span>
                <span>{formatTime(receipt.created_at ?? receipt.timestamp)}</span>
              </div>
            ))}
          </div>
        ))}
      </section>
    </AgentsSubPageShell>
  );
}
