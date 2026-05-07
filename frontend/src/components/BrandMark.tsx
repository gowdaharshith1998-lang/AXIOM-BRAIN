export function BrandMark() {
  return (
    <div className="pointer-events-none fixed left-1/2 top-6 z-20 flex -translate-x-1/2 items-center gap-2 rounded-full border border-white/10 bg-black/45 px-4 py-2 font-mono text-xs text-white/75 shadow-lg backdrop-blur">
      <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" className="text-white/70">
        <path
          d="M12 2.8 20 7.4v9.2l-8 4.6-8-4.6V7.4L12 2.8Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        />
      </svg>
      <span className="tracking-[0.4em]">AXIOM</span>
    </div>
  );
}
