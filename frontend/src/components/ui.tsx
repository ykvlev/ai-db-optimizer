import type { ReactNode } from 'react'
import type { Severity } from '../api'

export function Card({ title, actions, children, className = '' }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-lg border border-line bg-panel ${className}`}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
          <h3 className="text-[13px] font-semibold tracking-wide text-text">{title}</h3>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}

export function Button({ children, onClick, variant = 'default', disabled, title, type = 'button' }: {
  children: ReactNode; onClick?: () => void; variant?: 'default' | 'primary' | 'ghost' | 'danger'; disabled?: boolean; title?: string; type?: 'button' | 'submit'
}) {
  const styles = {
    default: 'bg-panel-2 border-line hover:border-muted text-text',
    primary: 'bg-accent border-accent text-white hover:brightness-110',
    ghost: 'bg-transparent border-transparent text-muted hover:text-text',
    danger: 'bg-transparent border-line text-bad hover:border-bad',
  }[variant]
  return (
    <button type={type} title={title} disabled={disabled} onClick={onClick}
      className={`inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-[13px] font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${styles}`}>
      {children}
    </button>
  )
}

const sevStyles: Record<Severity, string> = {
  critical: 'bg-crit/15 text-crit border-crit/40',
  high: 'bg-bad/15 text-bad border-bad/40',
  medium: 'bg-warn/15 text-warn border-warn/40',
  low: 'bg-accent/15 text-accent border-accent/40',
  info: 'bg-muted/15 text-muted border-muted/40',
}
const sevLabel: Record<Severity, string> = { critical: 'критично', high: 'высокая', medium: 'средняя', low: 'низкая', info: 'инфо' }

export function SeverityBadge({ severity }: { severity: Severity }) {
  const s = (severity in sevStyles ? severity : 'info') as Severity
  return <span className={`inline-block shrink-0 rounded border px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${sevStyles[s]}`}>{sevLabel[s]}</span>
}

export function Tag({ children, tone = 'muted' }: { children: ReactNode; tone?: 'muted' | 'good' | 'bad' | 'warn' | 'accent' }) {
  const t = {
    muted: 'text-muted border-line',
    good: 'text-good border-good/40 bg-good/10',
    bad: 'text-bad border-bad/40 bg-bad/10',
    warn: 'text-warn border-warn/40 bg-warn/10',
    accent: 'text-accent border-accent/40 bg-accent/10',
  }[tone]
  return <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[11px] font-medium ${t}`}>{children}</span>
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="rounded-lg border border-line bg-panel p-4">
      <div className="text-[12px] text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-1 text-[12px] text-muted">{hint}</div>}
    </div>
  )
}

export function Tabs<T extends string>({ tabs, active, onChange }: { tabs: { id: T; label: ReactNode }[]; active: T; onChange: (t: T) => void }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-line">
      {tabs.map(t => (
        <button key={t.id} onClick={() => onChange(t.id)}
          className={`whitespace-nowrap border-b-2 px-3 py-2 text-[13px] transition ${active === t.id ? 'border-accent text-text' : 'border-transparent text-muted hover:text-text'}`}>
          {t.label}
        </button>
      ))}
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-md border border-dashed border-line p-6 text-center text-[13px] text-muted">{children}</div>
}

export function ErrorBox({ children }: { children: ReactNode }) {
  return <div className="rounded-md border border-bad/40 bg-bad/10 px-3 py-2 text-[13px] text-bad">{children}</div>
}

export function Spinner() {
  return <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
}

export function Code({ children }: { children: ReactNode }) {
  return <pre className="mono overflow-x-auto whitespace-pre-wrap rounded-md border border-line bg-bg p-3 text-[12.5px] leading-relaxed">{children}</pre>
}

export const fmtMs = (v?: number | null) => v == null ? '—' : v >= 1000 ? `${(v / 1000).toFixed(2)} с` : `${v.toFixed(v < 10 ? 2 : 1)} мс`
export const fmtNum = (v?: number | null) => v == null ? '—' : Math.round(v).toLocaleString('ru-RU')
