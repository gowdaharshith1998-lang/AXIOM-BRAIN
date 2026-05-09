import { AxiomGlyph } from "@/components/AxiomGlyph";

export function TopHeader() {
  return (
    <header className="fixed left-1/2 top-4 z-30 -translate-x-1/2 rounded-2xl border border-[#274057]/70 bg-[#07111d]/68 px-8 py-3 shadow-[0_18px_60px_rgba(0,0,0,0.32),0_0_36px_rgba(0,229,216,0.08)] backdrop-blur-xl">
      <div className="flex items-center gap-5">
        <AxiomGlyph className="h-8 w-8 text-[#E8F0FF]" />
        <div className="font-mono text-[24px] font-semibold tracking-[0.46em] text-[#E8F0FF]">AXIOM</div>
        <div className="h-7 w-px bg-white/12" />
        <div className="flex items-center gap-2 font-mono text-xs font-semibold uppercase tracking-[0.12em] text-[#45f0a1]">
          <span className="h-2 w-2 rounded-full bg-[#45f0a1] shadow-[0_0_12px_#45f0a1]" />
          LIVE
        </div>
      </div>
    </header>
  );
}
