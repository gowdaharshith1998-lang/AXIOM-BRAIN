import { useEffect, useMemo, useState } from "react";

import { useBrainStore, type WardenInsight, type WatchdogAlert } from "@/state/brain.store";

const severityRank = { critical: 3, warning: 2, info: 1 } as const;

function insightFromAlert(alert: WatchdogAlert): WardenInsight {
  return {
    insight_id: alert.alert_id,
    severity: alert.severity,
    message: alert.reason,
    confidence: 1,
    related_entity_ids: [alert.entity_id],
    recommended_actions: [alert.suggested_action],
    timestamp: alert.detected_at ?? new Date().toISOString(),
    demo: alert.demo_flag,
  };
}

async function fetchOpenWatchdogAlert(): Promise<WardenInsight | null> {
  const response = await fetch("/api/internal/watchdog/alerts?status=open&limit=50");
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const payload = (await response.json()) as { alerts?: WatchdogAlert[] };
  const [alert] = [...(payload.alerts ?? [])].sort((a, b) => {
    const severityDelta = severityRank[b.severity] - severityRank[a.severity];
    if (severityDelta !== 0) return severityDelta;
    return String(b.detected_at ?? "").localeCompare(String(a.detected_at ?? ""));
  });
  return alert ? insightFromAlert(alert) : null;
}

const noAlertInsight: WardenInsight = {
  insight_id: "no_watchdog_alerts",
  severity: "info",
  message: "No open watchdog alerts.",
  confidence: 1,
  related_entity_ids: [],
  recommended_actions: [],
  timestamp: "",
};

export function AIInsightCard() {
  const storeInsights = useBrainStore((s) => s.insights);
  const watchdogAlerts = useBrainStore((s) => s.watchdogAlerts);
  const [fetchedInsight, setFetchedInsight] = useState<WardenInsight | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (storeInsights.length || watchdogAlerts.length) return undefined;
    fetchOpenWatchdogAlert()
      .then((insight) => {
        if (!cancelled) setFetchedInsight(insight);
      })
      .catch(() => {
        if (!cancelled) setFetchedInsight(null);
      });
    return () => {
      cancelled = true;
    };
  }, [storeInsights.length, watchdogAlerts.length]);

  const insight = useMemo(() => {
    const [alert] = [...watchdogAlerts].sort((a, b) => severityRank[b.severity] - severityRank[a.severity]);
    if (alert) return insightFromAlert(alert);
    return storeInsights[0] ?? fetchedInsight ?? noAlertInsight;
  }, [fetchedInsight, storeInsights, watchdogAlerts]);

  const highlight = () => {
    if (!insight.related_entity_ids.length) return;
    window.dispatchEvent(
      new CustomEvent("axiom:highlight-entities", {
        detail: { ids: insight.related_entity_ids },
      }),
    );
  };
  return (
    <section className="mt-6 border-t border-white/10 pt-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-[10px] uppercase tracking-[0.22em] text-white/45">AI Insight</h2>
        <span className="text-[9px] text-white/35">WATCHDOG</span>
      </div>
      <div className={insight.severity === "critical" ? "text-[#fb7185]" : insight.severity === "warning" ? "text-[#eab308]" : "text-[#38bdf8]"}>
        {insight.insight_id === "no_watchdog_alerts" ? "WARDEN clear" : "WARDEN flagged"}
      </div>
      <p className="mt-3 text-white/70">{insight.message}</p>
      <div className="mt-3 text-[10px] text-white/40">
        Connected: {insight.related_entity_ids.length ? insight.related_entity_ids.join(", ") : "No related entities"}
      </div>
      <button
        type="button"
        onClick={highlight}
        disabled={!insight.related_entity_ids.length}
        className="mt-4 border border-white/10 px-3 py-2 text-left text-[10px] text-white/70 transition hover:border-white/25 hover:text-white disabled:cursor-not-allowed disabled:opacity-45"
      >
        {insight.recommended_actions[0] ?? "No action needed"}
      </button>
    </section>
  );
}
