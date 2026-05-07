import { useBrainStore, type WardenInsight } from "@/state/brain.store";

const FALLBACK: WardenInsight = {
  insight_id: "ins_demo",
  severity: "warning",
  message: "PR-341 modifies billing code without an RFC reference. This pattern is correlated with billing incidents in 7 of the last 12 deployments.",
  confidence: 0.87,
  related_entity_ids: [],
  recommended_actions: ["View recommended actions"],
  timestamp: "t",
};

export function AIInsightCard() {
  const insight = useBrainStore((s) => s.insights[0]) ?? FALLBACK;
  const highlight = () => {
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
        <span className="text-[9px] text-white/35">BETA</span>
      </div>
      <div className="text-[#eab308]">WARDEN flagged</div>
      <p className="mt-3 text-white/70">{insight.message} Confidence {insight.confidence.toFixed(2)}.</p>
      <div className="mt-3 text-[10px] text-white/40">
        Connected: {insight.related_entity_ids.length ? insight.related_entity_ids.join(", ") : "Refund Policy 2026, PaymentProcessor.ts, Stripe webhook handler"}
      </div>
      <button
        type="button"
        onClick={highlight}
        className="mt-4 border border-white/10 px-3 py-2 text-left text-[10px] text-white/70 transition hover:border-white/25 hover:text-white"
      >
        View recommended actions
      </button>
    </section>
  );
}
