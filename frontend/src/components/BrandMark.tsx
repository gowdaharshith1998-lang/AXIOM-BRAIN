export function BrandMark() {
  return (
    <div className="font-mono text-white/85">
      <div className="flex items-center gap-2">
        <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" className="text-white/70">
          <path
            d="M12 2.8 20 7.4v9.2l-8 4.6-8-4.6V7.4L12 2.8Z"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          />
        </svg>
        <span className="text-sm font-semibold tracking-[0.32em]">AXIOM</span>
      </div>
      <div className="mt-1 text-[10px] tracking-normal text-white/45">Your company, brought to life</div>
    </div>
  );
}
