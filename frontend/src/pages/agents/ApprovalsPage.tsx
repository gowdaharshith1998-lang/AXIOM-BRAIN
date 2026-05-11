import { useEffect, useMemo, useState } from "react";

import {
  approveApproval,
  denyApproval,
  listApprovals,
  type ApprovalRequest,
} from "@/lib/approvalsClient";

type Props = {
  initialStatus?: "pending" | "approved" | "denied" | "expired";
};

function formatJson(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}

export function ApprovalsPage({ initialStatus = "pending" }: Props) {
  const [status, setStatus] = useState(initialStatus);
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = useMemo(
    () => approvals.find((approval) => approval.id === selectedId) ?? null,
    [approvals, selectedId],
  );

  useEffect(() => {
    listApprovals(status).then(setApprovals).catch(() => setApprovals([]));
  }, [status]);

  useEffect(() => {
    const onEvent = (event: Event) => {
      const detail = (event as CustomEvent).detail as { type?: string; payload?: ApprovalRequest };
      if (!detail.payload?.id) return;
      if (detail.type === "approval_requested" && status === "pending") {
        setApprovals((rows) => [detail.payload as ApprovalRequest, ...rows]);
      }
      if (
        detail.type === "approval_approved" ||
        detail.type === "approval_denied" ||
        detail.type === "approval_expired"
      ) {
        setApprovals((rows) => rows.filter((row) => row.id !== detail.payload?.id));
      }
    };
    window.addEventListener("axiom:brain-event", onEvent);
    return () => window.removeEventListener("axiom:brain-event", onEvent);
  }, [status]);

  async function approveSelected() {
    if (!selected) return;
    const note = window.prompt("Approval note") ?? "";
    const updated = await approveApproval(selected.id, { by_user: "studio", note });
    setApprovals((rows) => rows.filter((row) => row.id !== updated.id));
  }

  async function denySelected() {
    if (!selected) return;
    const note = window.prompt("Denial reason") ?? "";
    if (!note.trim()) return;
    const updated = await denyApproval(selected.id, { by_user: "studio", note });
    setApprovals((rows) => rows.filter((row) => row.id !== updated.id));
  }

  return (
    <section className="min-h-full bg-[#050b14] px-8 py-8 text-[#dce8ff]">
      <div className="mb-5 flex items-center justify-between">
        <h1 className="text-[28px] font-semibold tracking-[0.08em]">Approvals</h1>
        <div className="flex gap-2">
          {(["pending", "approved", "denied", "expired"] as const).map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setStatus(item)}
              className={`rounded-md border px-3 py-2 text-[13px] ${status === item ? "border-[#3287ff] bg-[#102a55] text-white" : "border-[#1d3452] text-[#9fb0c8]"}`}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)_420px] gap-5">
        <div className="overflow-hidden rounded-lg border border-[#182c45]">
          {approvals.map((approval) => (
            <button
              key={approval.id}
              type="button"
              onClick={() => setSelectedId(approval.id)}
              className="grid w-full grid-cols-[150px_120px_minmax(0,1fr)_120px] items-center gap-3 border-b border-[#14263d] px-4 py-3 text-left hover:bg-[#0b1728]"
            >
              <span className="font-medium text-[#eef5ff]">{approval.agent_name}</span>
              <span className="text-[#9fb0c8]">{approval.intent}</span>
              <span className="truncate text-[#b7c7dd]">{approval.policy_id}</span>
              <span className="rounded bg-[#2a1f0c] px-2 py-1 text-center text-[#ffd98a]">
                {approval.status}
              </span>
            </button>
          ))}
          {approvals.length === 0 ? (
            <div className="px-4 py-10 text-center text-[#8ba8cb]">No approvals in this view.</div>
          ) : null}
        </div>

        <aside className="rounded-lg border border-[#182c45] bg-[#071225] p-4">
          {selected ? (
            <>
              <div className="mb-3 text-[18px] font-semibold">{selected.policy_id}</div>
              <div className="mb-3 text-[13px] text-[#9fb0c8]">{selected.reason}</div>
              <dl className="mb-4 grid grid-cols-[120px_1fr] gap-2 text-[13px]">
                <dt className="text-[#7fa2c8]">Role</dt>
                <dd>{selected.required_role ?? "none"}</dd>
                <dt className="text-[#7fa2c8]">Target</dt>
                <dd>{selected.target_entity_id ?? "none"}</dd>
                <dt className="text-[#7fa2c8]">Expires</dt>
                <dd>{selected.expires_at}</dd>
              </dl>
              <pre className="mb-4 max-h-[360px] overflow-auto rounded-md bg-[#030812] p-3 text-[12px] text-[#c9d7ea]">
                {formatJson(selected.proposed_action)}
              </pre>
              {selected.status === "pending" ? (
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={approveSelected}
                    className="rounded-md bg-[#0d6b4f] px-3 py-2 text-sm text-white"
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    onClick={denySelected}
                    className="rounded-md bg-[#7a1f2b] px-3 py-2 text-sm text-white"
                  >
                    Deny
                  </button>
                </div>
              ) : null}
            </>
          ) : (
            <div className="text-[#8ba8cb]">Select an approval.</div>
          )}
        </aside>
      </div>
    </section>
  );
}
