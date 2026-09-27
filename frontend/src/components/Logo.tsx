/** Знак AI Database Optimizer: три строки таблицы, каждая короче предыдущей — время запроса падает. */
export function LogoMark({ size = 20, className = '' }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden="true">
      <rect x="2" y="3" width="20" height="4.5" rx="1" fill="#000" />
      <rect x="2" y="9.75" width="13.5" height="4.5" rx="1" fill="#000" />
      <rect x="2" y="16.5" width="7" height="4.5" rx="1" fill="#000" />
    </svg>
  )
}

export function Logo() {
  return (
    <span className="inline-flex items-center gap-2.5">
      <LogoMark size={20} />
      <span className="flex flex-col leading-none">
        <span className="text-[14px] font-medium tracking-[-0.01em] text-text">Optimizer</span>
        <span className="mt-0.5 font-mono text-[8px] font-semibold uppercase tracking-[0.12em] text-muted">AI · Database</span>
      </span>
    </span>
  )
}
