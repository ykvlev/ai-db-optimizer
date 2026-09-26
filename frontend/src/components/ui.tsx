import { useState, type ReactNode } from 'react'
import type { Severity } from '../api'

export function Card({ title, actions, children, className = '' }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`border border-line bg-panel ${className}`}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
          <h3 className="kicker text-text">{title}</h3>
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
    default: 'bg-transparent border-line hover:border-text text-text',
    primary: 'bg-text border-text text-bg hover:bg-accent hover:border-accent hover:text-black',
    ghost: 'bg-transparent border-transparent text-muted hover:text-text',
    danger: 'bg-transparent border-line text-bad hover:border-bad',
  }[variant]
  return (
    <button type={type} title={title} disabled={disabled} onClick={onClick}
      className={`inline-flex items-center gap-2 border px-3.5 py-1.5 text-[13px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${styles}`}>
      {children}
    </button>
  )
}

const sevStyles: Record<Severity, string> = {
  critical: 'bg-bad text-black border-bad',
  high: 'text-bad border-bad',
  medium: 'text-warn border-warn',
  low: 'text-text border-line',
  info: 'text-muted border-line',
}
const sevLabel: Record<Severity, string> = { critical: 'критично', high: 'высокая', medium: 'средняя', low: 'низкая', info: 'инфо' }

export function SeverityBadge({ severity }: { severity: Severity }) {
  const s = (severity in sevStyles ? severity : 'info') as Severity
  return <span className={`inline-block shrink-0 border px-1.5 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.1em] ${sevStyles[s]}`}>{sevLabel[s]}</span>
}

export function Tag({ children, tone = 'muted' }: { children: ReactNode; tone?: 'muted' | 'good' | 'bad' | 'warn' | 'accent' }) {
  const t = {
    muted: 'text-muted border-line',
    good: 'text-good border-good',
    bad: 'text-bad border-bad',
    warn: 'text-warn border-warn',
    accent: 'text-accent border-accent',
  }[tone]
  return <span className={`inline-flex items-center border px-1.5 py-0.5 text-[11px] font-semibold ${t}`}>{children}</span>
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="border-t-2 border-text bg-transparent pt-3">
      <div className="kicker text-muted">{label}</div>
      <div className="mt-2 text-[34px] font-bold leading-none tracking-tight tabular-nums">{value}</div>
      {hint && <div className="mt-1 text-[12px] text-muted">{hint}</div>}
    </div>
  )
}

export function Tabs<T extends string>({ tabs, active, onChange }: { tabs: { id: T; label: ReactNode }[]; active: T; onChange: (t: T) => void }) {
  return (
    <div className="flex gap-0 overflow-x-auto border-b border-line [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      {tabs.map(t => (
        <button key={t.id} onClick={() => onChange(t.id)}
          className={`-mb-px whitespace-nowrap border-b-2 px-2.5 py-2.5 text-[12.5px] font-semibold transition ${active === t.id ? 'border-accent text-text' : 'border-transparent text-muted hover:text-text'}`}>
          {t.label}
        </button>
      ))}
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="border border-dashed border-line p-6 text-center text-[13px] leading-relaxed text-muted">{children}</div>
}

export function ErrorBox({ children }: { children: ReactNode }) {
  return <div className="border-l-2 border-bad bg-bad/10 px-3 py-2 text-[13px] text-bad">{children}</div>
}

export function Spinner() {
  return <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
}

export function Code({ children }: { children: ReactNode }) {
  return <pre className="mono overflow-x-auto whitespace-pre-wrap border border-line bg-bg p-3 text-[12.5px] leading-relaxed">{children}</pre>
}

export const fmtMs = (v?: number | null) => v == null ? '—' : v >= 1000 ? `${(v / 1000).toFixed(2)} с` : `${v.toFixed(v < 10 ? 2 : 1)} мс`
export const fmtNum = (v?: number | null) => v == null ? '—' : Math.round(v).toLocaleString('ru-RU')

/** Блок команды с кнопкой «Скопировать». */
export function CopyBlock({ children, label }: { children: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard?.writeText(children).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) }).catch(() => {})
  }
  return (
    <div className="border border-line bg-panel">
      <div className="flex items-center justify-between gap-3 border-b border-line py-1 pl-3 pr-1">
        <span className="truncate text-[11.5px] text-muted">{label ?? 'Команда'}</span>
        <button onClick={copy}
          className={`shrink-0 px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.1em] ${copied ? 'text-accent' : 'text-muted hover:text-text'}`}>
          {copied ? 'Скопировано ✓' : 'Скопировать'}
        </button>
      </div>
      <pre className="mono overflow-x-auto px-3 py-2.5 text-[12.5px] leading-relaxed">{children}</pre>
    </div>
  )
}

/** Значок «?» с пояснением термина при наведении. */
export function Hint({ children }: { children: string }) {
  return (
    <span title={children} tabIndex={0}
      className="ml-1 inline-flex h-4 w-4 cursor-help items-center justify-center border border-line text-[10px] text-muted hover:border-text hover:text-text">?</span>
  )
}

/** Нумерованный шаг инструкции. */
export function Step({ n, title, children }: { n: number | string; title: ReactNode; children: ReactNode }) {
  return (
    <div className="flex gap-3">
      <div className="w-6 shrink-0 pt-0.5 text-[13px] font-bold tabular-nums text-accent">{String(n).padStart(2, '0')}</div>
      <div className="min-w-0 flex-1 space-y-2 pb-2">
        <div className="pt-0.5 text-[14px] font-semibold">{title}</div>
        <div className="space-y-2 text-[13px] leading-relaxed text-muted">{children}</div>
      </div>
    </div>
  )
}
