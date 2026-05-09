import { useBrainStore } from "@/state/brain.store";

const tabs = ["Graph", "Flow", "Governance", "Timeline", "Search", "Receipts", "Agent Console"];

export function StatusFooter() {
  const fps = useBrainStore((s) => s.fps);
  return (
    <footer className="fixed bottom-0 left-[84px] right-0 z-30 flex h-8 items-center justify-between border-t border-[#1a3550]/55 bg-[#050a12]/74 px-5 font-mono text-[11px] text-[#E8F0FF]/58 backdrop-blur-xl">
      <div className="text-[#E8F0FF]/45">AXIOM v0.1</div>
      <nav className="flex items-center gap-5">
        {tabs.map((tab) => (
          <button key={tab} type="button" className={tab === "Graph" ? "text-[#00E5D8]" : "transition hover:text-[#E8F0FF]/80"}>
            {tab}
          </button>
        ))}
      </nav>
      <div className="flex items-center gap-4">
        <span>{Math.round(fps || 0)} FPS</span>
        <span className="flex items-center gap-2 text-[#45f0a1]">
          <span className="h-1.5 w-1.5 rounded-full bg-[#45f0a1]" />
          All systems operational
        </span>
      </div>
    </footer>
  );
}
