import { useEffect, useState } from "react";

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

const KIND_COLOUR: Record<ActivityItem["kind"], string> = {
  skill_run: "text-cyan-400 border-cyan-500/30 bg-cyan-500/10",
  mcp_tool_call: "text-blue-400 border-blue-500/30 bg-blue-500/10",
  connector_sync: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
};

export function RecentActivityFeed() {
  const [items, setItems] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/internal/agents/activity?limit=12")
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
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
    <section className="rounded-xl border border-[#1a2f4a] bg-[#06101f]/50">
      <div className="border-b border-[#1a2f4a] px-4 py-3">
        <h2 className="text-[13px] font-semibold uppercase tracking-[0.14em] text-[#7fa2c8]">Recent activity</h2>
      </div>
      <div className="divide-y divide-[#132339]">
        {loading ? <div className="px-4 py-6 text-sm text-[#7fa2c8]">Loading activity…</div> : null}
        {error ? (
          <div className="px-4 py-6 text-sm text-red-300">Could not load activity: {error}</div>
        ) : null}
        {!loading && !error && items.length === 0 ? (
          <div className="px-4 py-6 text-sm text-[#8ba8cb]">
            No activity yet. Connect a source or run a skill to see the brain working.
          </div>
        ) : null}
        {items.map((item) => (
          <div key={`${item.kind}:${item.id}`} className="flex items-center gap-3 px-4 py-3">
            <span
              className={`inline-flex h-6 shrink-0 items-center rounded border px-2 font-mono text-[10px] ${KIND_COLOUR[item.kind]}`}
            >
              {KIND_LABEL[item.kind]}
            </span>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm text-[#eef5ff]">{item.title}</div>
              <div className="truncate text-xs text-[#8ba8cb]">
                {item.agent_name ? `${item.agent_name} · ` : ""}
                {item.status}
                {item.duration_ms ? ` · ${item.duration_ms}ms` : ""}
              </div>
            </div>
            <div className="shrink-0 font-mono text-[11px] text-[#7fa2c8]">
              {item.at ? new Date(item.at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—"}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
