export const navItems = [
  ["/graph", "Graph"],
  ["/explore", "Explore"],
  ["/insights", "Insights"],
  ["/agents", "Agents"],
  ["/skills", "Skills"],
  ["/settings", "Settings"],
] as const;

export const agentNavItems = [
  ["/graph", "Graph"],
  ["/explore", "Explore"],
  ["/insights", "Insights"],
  ["/agents", "Agents"],
  ["/skills", "Skills"],
  ["/agents/activity", "Activity"],
  ["/settings", "Settings"],
] as const;

export function NavIcon({ label }: { label: string }) {
  const common = "h-5 w-5 text-current";
  if (label === "Graph") {
    return (
      <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7">
        <path d="M6 6h.01M18 6h.01M6 18h.01M18 18h.01M7 6h10M6 7v10M18 7v10M7 18h10" />
      </svg>
    );
  }
  if (label === "Agents") {
    return (
      <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7">
        <path d="M16 11a4 4 0 1 0-4-4 4 4 0 0 0 4 4ZM8 13a3 3 0 1 0-3-3 3 3 0 0 0 3 3Zm8 1c-3.3 0-6 1.6-6 3.5V20h12v-2.5c0-1.9-2.7-3.5-6-3.5ZM8 14c-2.8 0-5 1.2-5 2.8V19h5" />
      </svg>
    );
  }
  if (label === "Skills") {
    return (
      <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7">
        <path d="M12 3 4 7v10l8 4 8-4V7l-8-4Zm0 8 8-4M12 11 4 7m8 4v10" />
        <path d="M8.5 13.5 12 15l3.5-1.5" />
      </svg>
    );
  }
  if (label === "Explore") {
    return (
      <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7">
        <circle cx="12" cy="12" r="8" />
        <path d="m15 9-2 5-5 2 2-5 5-2Z" />
      </svg>
    );
  }
  if (label === "Insights") {
    return (
      <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7">
        <path d="M4 19V8m5 11V5m5 14v-8m6 8H3" />
      </svg>
    );
  }
  if (label === "Activity") {
    return (
      <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7">
        <path d="M4 12h4l2-6 4 12 2-6h4" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7">
      <circle cx="12" cy="12" r="3.5" />
      <path d="m19 12 2-1-1-3-2-.3-.7-1.8 1.2-1.7-2.3-2.3-1.7 1.2-1.8-.7L12 1 9 2l-.3 2-1.8.7-1.7-1.2L2.9 5.8l1.2 1.7L3.4 9.3 1.5 9.6v3l1.9.3.7 1.8-1.2 1.7 2.3 2.3 1.7-1.2 1.8.7.3 2h3l.3-2 1.8-.7 1.7 1.2 2.3-2.3-1.2-1.7.7-1.8 2-.3Z" />
    </svg>
  );
}
