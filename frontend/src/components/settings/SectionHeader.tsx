export type SectionHeaderProps = {
  title: string;
  subtitle?: string;
};

export function SectionHeader({ title, subtitle }: SectionHeaderProps) {
  return (
    <header className="mb-4 mt-10 first:mt-0">
      <h2 className="font-mono text-[13px] font-semibold uppercase tracking-[0.22em] text-[#8d9bbb]">
        {title}
      </h2>
      {subtitle ? <p className="mt-1 max-w-2xl text-[13px] leading-snug text-[#a9b7d6]/85">{subtitle}</p> : null}
    </header>
  );
}
