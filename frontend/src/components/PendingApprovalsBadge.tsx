import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { listApprovals, type ApprovalRequest } from "@/lib/approvalsClient";

export function PendingApprovalsBadge() {
  const [count, setCount] = useState(0);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    listApprovals("pending")
      .then((rows) => {
        if (!cancelled) setCount(rows.length);
      })
      .catch(() => {
        if (!cancelled) setCount(0);
      });

    const onEvent = (event: Event) => {
      const detail = (event as CustomEvent).detail as { type?: string; payload?: ApprovalRequest };
      if (detail.type === "approval_requested") setCount((value) => value + 1);
      if (
        detail.type === "approval_approved" ||
        detail.type === "approval_denied" ||
        detail.type === "approval_expired"
      ) {
        setCount((value) => Math.max(0, value - 1));
      }
    };
    window.addEventListener("axiom:brain-event", onEvent);
    return () => {
      cancelled = true;
      window.removeEventListener("axiom:brain-event", onEvent);
    };
  }, []);

  return (
    <button
      type="button"
      aria-label="Pending approvals"
      onClick={() => navigate("/agents/approvals")}
      className="flex h-[38px] items-center gap-2 rounded-lg border border-[#3b2f15] bg-[#211708] px-3 text-[13px] text-[#ffd98a]"
    >
      <span className="h-2 w-2 rounded-full bg-[#ffbd4a]" />
      <span>{count}</span>
    </button>
  );
}
