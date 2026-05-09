export function AxiomGlyph({ className = "h-6 w-6" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} fill="none" aria-hidden="true">
      <path d="M16 3.5 27 9.75v12.5L16 28.5 5 22.25V9.75L16 3.5Z" stroke="currentColor" strokeWidth="2.4" />
      <path d="M16 9.5 21.5 12.7v6.6L16 22.5l-5.5-3.2v-6.6L16 9.5Z" stroke="currentColor" strokeWidth="1.4" opacity="0.55" />
    </svg>
  );
}
