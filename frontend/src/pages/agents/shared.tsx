import type { ReactNode } from "react";

export function formatTime(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "Not recorded";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Not recorded" : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function hourBucket(value: string | null | undefined): string {
  if (!value) return "Unknown hour";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown hour";
  const iso = date.toISOString();
  return `${iso.slice(0, 10)} ${iso.slice(11, 13)}:00`;
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="agents-empty">{children}</div>;
}

export function AgentsSubPageShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <div className="agents-stage">
      <header className="agents-topbar">
        <div className="agents-title-block">
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
      </header>
      <main className="agents-content">{children}</main>
    </div>
  );
}
