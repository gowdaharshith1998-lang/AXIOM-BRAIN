import { useEffect, useMemo, useState } from "react";

import { getMcpStats, type MCPStats } from "@/lib/studioClient";
import { AgentsSubPageShell, EmptyState, formatTime } from "@/pages/agents/shared";

export function RuntimePage() {
  const [stats, setStats] = useState<MCPStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const toolCalls = useMemo(() => stats?.tools.reduce((total, tool) => total + tool.calls, 0) ?? 0, [stats]);
  const activeAgents = stats ? [...new Set([...(stats.active_agents ?? []), ...(stats.observed_agents ?? [])])] : [];
  const hasSignals = Boolean(toolCalls || activeAgents.length || stats?.recent_actions.length);

  useEffect(() => {
    getMcpStats()
      .then(setStats)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Unable to load runtime stats"));
  }, []);

  return (
    <AgentsSubPageShell title="Runtime" subtitle="Live MCP runtime stats from the backend.">
      {error ? <EmptyState>Unable to load runtime stats: {error}</EmptyState> : null}
      <section className="agents-panel">
        <div className="agents-panel-head">
          <h2>Runtime Summary</h2>
        </div>
        {stats && hasSignals ? (
          <>
            <div className="agents-drawer-summary">
              <span>Active agents: {activeAgents.length}</span>
              <span>Tool calls: {toolCalls}</span>
              <span>Last call: {formatTime(stats.last_tool_call)}</span>
            </div>
            <div className="agents-table">
              <div className="agents-table-head">
                <span>Tool</span>
                <span>Calls</span>
                <span>Last Called</span>
              </div>
              {stats.tools.map((tool) => (
                <div className="agents-table-row" key={tool.name}>
                  <span>{tool.name}</span>
                  <span>{tool.calls}</span>
                  <span>{formatTime(tool.last_called)}</span>
                </div>
              ))}
            </div>
            <div className="agents-drawer-summary">
              {activeAgents.map((agent) => <span key={agent}>{agent}</span>)}
            </div>
          </>
        ) : <EmptyState>No active runtime signals yet.</EmptyState>}
      </section>
    </AgentsSubPageShell>
  );
}
