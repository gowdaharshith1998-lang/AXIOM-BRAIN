// HIDDEN-V2: replaced the watchdog-receipts feed with a unified runtime feed
// (skill runs + MCP tool calls + connector syncs) for YC company-brain positioning.
import { useEffect, useState } from "react";

import { requestRaw } from "@/lib/http";

type ActivityItem = {
  kind: "skill_run" | "mcp_tool_call" | "connector_sync";
  id: string;
  title: string;
  status: string;
  agent_name?: string;
  duration_ms?: number;
  at: string | null;
};

const KIND_LABEL: Record<ActivityItem["kind"], string> = {
  skill_run: "Skill",
  mcp_tool_call: "Tool",
  connector_sync: "Connector",
};

const KIND_COLOR: Record<ActivityItem["kind"], string> = {
  skill_run: "text-cyan-400 border-cyan-500/30 bg-cyan-500/10",
  mcp_tool_call: "text-blue-400 border-blue-500/30 bg-blue-500/10",
  connector_sync: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
};

export function ActivityPage() {
  const [items, setItems] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    requestRaw("/api/internal/agents/activity?limit=100")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        setItems(data.items ?? []);
        setLoading(false);
      })
      .catch((err) => {
        setError(String(err));
        setLoading(false);
      });
  }, []);

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold tracking-tight">Activity</h1>
      <p className="mt-1 text-sm text-white/60">
        Live runtime feed: skill runs, MCP tool calls, and connector syncs.
      </p>
      <div className="mt-6 space-y-2">
        {loading && <div className="text-white/50">Loading…</div>}
        {error && (
          <div className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
            Failed to load activity: {error}
          </div>
        )}
        {!loading && !error && items.length === 0 && (
          <div className="rounded-md border border-white/10 bg-white/5 p-4 text-sm text-white/60">
            No activity yet. Connect a source or run a skill to see the brain working.
          </div>
        )}
        {items.map((item) => (
          <div
            key={`${item.kind}:${item.id}`}
            className="flex items-center gap-4 rounded-md border border-white/10 bg-white/[0.02] p-3"
          >
            <span
              className={`inline-flex h-6 items-center rounded border px-2 font-mono text-xs ${KIND_COLOR[item.kind]}`}
            >
              {KIND_LABEL[item.kind]}
            </span>
            <div className="flex-1">
              <div className="text-sm text-white/90">{item.title}</div>
              <div className="text-xs text-white/50">
                {item.agent_name ? `${item.agent_name} · ` : ""}
                {item.status}
                {item.duration_ms ? ` · ${item.duration_ms}ms` : ""}
              </div>
            </div>
            <div className="font-mono text-xs text-white/40">
              {item.at ? new Date(item.at).toLocaleString() : "—"}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
