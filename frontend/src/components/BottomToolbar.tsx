import { exportVisibleAsJson } from "@/lib/export";
import { useBrainStore } from "@/state/brain.store";

export function fpsColor(fps: number): string {
  if (fps >= 55) return "#22c55e";
  if (fps >= 30) return "#eab308";
  return "#ef4444";
}

export function BottomToolbar() {
  const fps = useBrainStore((s) => s.fps);
  const entities = useBrainStore((s) => s.entities);
  const edges = useBrainStore((s) => s.edges);

  const openSearch = () => {
    window.dispatchEvent(new Event("axiom:open-palette"));
  };

  const toggleFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void document.documentElement.requestFullscreen();
  };

  const exportJson = () => {
    exportVisibleAsJson({ entities, edges });
  };

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-5 z-20 flex flex-col items-center gap-3 font-mono text-xs text-white/75">
      <button
        type="button"
        onClick={openSearch}
        className="pointer-events-auto w-[min(480px,calc(100vw-32px))] rounded-full border border-white/10 bg-[#0a0c14]/70 px-4 py-2 text-left text-white/55 shadow-lg backdrop-blur transition hover:border-white/20 hover:text-white focus:outline-none focus:ring-2 focus:ring-white/30"
      >
        🔍 Find symbol, file, or path... <span className="float-right text-white/35">⌘K</span>
      </button>

      <div className="pointer-events-auto flex h-11 w-[min(640px,calc(100vw-24px))] items-center justify-between gap-3 rounded-full border border-white/10 bg-[#0a0c14]/75 px-4 shadow-2xl backdrop-blur">
        <span className="shrink-0 text-white/45">AXIOM v0.1</span>
        <button type="button" onClick={toggleFullscreen} className="rounded px-2 py-1 transition hover:bg-white/10 hover:text-white">
          ⛶ Fullscreen
        </button>
        <button type="button" className="rounded px-2 py-1 text-white transition hover:bg-white/10">
          ● Live
        </button>
        <button type="button" className="rounded px-2 py-1 transition hover:bg-white/10 hover:text-white">
          ⏱ Timeline
        </button>
        <button type="button" onClick={exportJson} className="rounded px-2 py-1 transition hover:bg-white/10 hover:text-white">
          ⬇ Export JSON
        </button>
        <span className="shrink-0 tabular-nums" style={{ color: fpsColor(fps) }}>
          {fps || 0} FPS
        </span>
      </div>
    </div>
  );
}
