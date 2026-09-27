import { useState, type ReactNode } from 'react'
import type { Severity } from '../api'

/** Bordered Card: белая поверхность, глубина — двойное кольцо-обводка (shadow-subtle), без теней. */
export function Card({ title, actions, children, className = '' }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <h3 className="kicker text-text">{title}</h3>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}

/** Кнопки: Filled Black (primary), Ghost Outline (default), текстовая (ghost). Радиус 6px. */
export function Button({ children, onClick, variant = 'default', disabled, title, type = 'button' }: {
  children: ReactNode; onClick?: () => void; variant?: 'default' | 'primary' | 'ghost' | 'danger'; disabled?: boolean; title?: string; type?: 'button' | 'submit'
}) {
  const styles = {
    default: 'bg-white text-charcoal shadow-[0_0_0_1px_#ebebeb] hover:text-obsidian hover:shadow-[0_0_0_1px_#c9c9c9]',
    primary: 'bg-obsidian text-white hover:bg-charcoal',
    ghost: 'bg-transparent text-charcoal hover:text-obsidian hover:bg-[#f2f2f2]',
    danger: 'bg-white text-charcoal shadow-[0_0_0_1px_#ebebeb] hover:text-obsidian hover:shadow-[0_0_0_1px_#171717]',
  }[variant]
  return (
    <button type={type} title={title} disabled={disabled} onClick={onClick}
      className={`inline-flex h-8 items-center gap-2 rounded-md px-3 text-[14px] font-normal transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${styles}`}>
      {children}
    </button>
  )
}

const sevStyles: Record<Severity, string> = {
  critical: 'bg-obsidian text-white',
  high: 'bg-obsidian text-white',
  medium: 'text-obsidian shadow-[0_0_0_1px_#171717]',
  low: 'text-stone shadow-[0_0_0_1px_#ebebeb]',
  info: 'text-graphite shadow-[0_0_0_1px_#ebebeb]',
}
const sevLabel: Record<Severity, string> = { critical: 'критично', high: 'высокая', medium: 'средняя', low: 'низкая', info: 'инфо' }

export function SeverityBadge({ severity }: { severity: Severity }) {
  const s = (severity in sevStyles ? severity : 'info') as Severity
  return <span className={`kicker inline-block shrink-0 rounded-sm px-1.5 py-px !text-[10px] ${sevStyles[s]}`}>{sevLabel[s]}</span>
}

/** Метка: моноширинная, монохромная; единственный цвет — Terminal Green для успеха. */
export function Tag({ children, tone = 'muted' }: { children: ReactNode; tone?: 'muted' | 'good' | 'bad' | 'warn' | 'accent' }) {
  const t = {
    muted: 'text-stone shadow-[0_0_0_1px_#ebebeb]',
    good: 'text-terminal-green shadow-[0_0_0_1px_#297a3a]',
    bad: 'bg-obsidian text-white',
    warn: 'text-charcoal shadow-[0_0_0_1px_#c9c9c9]',
    accent: 'text-obsidian shadow-[0_0_0_1px_#171717]',
  }[tone]
  return <span className={`inline-flex items-center rounded-sm px-1.5 py-px font-mono text-[11px] ${t}`}>{children}</span>
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="card p-4">
      <div className="kicker text-stone">{label}</div>
      <div className="mt-3 text-[30px] font-[450] leading-none tracking-[-0.05em] tabular-nums">{value}</div>
      {hint && <div className="mt-2 text-[13px] text-stone">{hint}</div>}
    </div>
  )
}

export function Tabs<T extends string>({ tabs, active, onChange }: { tabs: { id: T; label: ReactNode }[]; active: T; onChange: (t: T) => void }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-line [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      {tabs.map(t => (
        <button key={t.id} onClick={() => onChange(t.id)}
          className={`-mb-px flex items-center gap-1.5 whitespace-nowrap border-b-2 px-2.5 py-2.5 text-[14px] transition-colors ${active === t.id ? 'border-obsidian text-obsidian' : 'border-transparent text-stone hover:text-obsidian'}`}>
          {t.label}
        </button>
      ))}
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-md border border-dashed border-ash p-6 text-center text-[13px] leading-relaxed text-stone">{children}</div>
}

export function ErrorBox({ children }: { children: ReactNode }) {
  return <div className="rounded-md bg-white px-3 py-2 text-[13px] text-obsidian shadow-[0_0_0_1px_#171717]"><span className="mr-1.5 font-mono">✕</span>{children}</div>
}

export function Spinner() {
  return <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-[1.5px] border-current border-t-transparent" />
}

export function Code({ children }: { children: ReactNode }) {
  return <pre className="mono overflow-x-auto whitespace-pre-wrap rounded-md bg-white p-3 text-[12.5px] leading-[1.6] shadow-[0_0_0_1px_#ebebeb]">{children}</pre>
}

export const fmtMs = (v?: number | null) => v == null ? '—' : v >= 1000 ? `${(v / 1000).toFixed(2)} с` : `${v.toFixed(v < 10 ? 2 : 1)} мс`
export const fmtNum = (v?: number | null) => v == null ? '—' : Math.round(v).toLocaleString('ru-RU')

/** CLI Output Panel: команда с префиксом «›» и кнопкой копирования. */
export function CopyBlock({ children, label }: { children: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard?.writeText(children).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) }).catch(() => {})
  }
  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b border-line py-1 pl-4 pr-1.5">
        <span className="kicker truncate text-stone">{label ?? 'Терминал'}</span>
        <button onClick={copy} className={`kicker shrink-0 rounded-sm px-2 py-1 ${copied ? 'text-terminal-green' : 'text-stone hover:text-obsidian'}`}>
          {copied ? '✓ Скопировано' : 'Скопировать'}
        </button>
      </div>
      <pre className="mono overflow-x-auto px-4 py-3 text-[12.5px] leading-[1.6]">
        {children.split('\n').map((l, i) => (
          <div key={i}><span className="mr-2.5 select-none text-smoke">{/^[A-Z_]+=/.test(l) || /^(CREATE|GRANT)/.test(l) ? ' ' : '›'}</span>{l}</div>
        ))}
      </pre>
    </div>
  )
}

/** Значок «?» с пояснением термина при наведении. */
export function Hint({ children }: { children: string }) {
  return (
    <span title={children} tabIndex={0}
      className="ml-1 inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full font-mono text-[10px] text-stone shadow-[0_0_0_1px_#ebebeb] hover:text-obsidian">?</span>
  )
}

/** Нумерованный шаг инструкции. */
export function Step({ n, title, children }: { n: number | string; title: ReactNode; children: ReactNode }) {
  return (
    <div className="flex gap-3">
      <div className="w-6 shrink-0 pt-0.5 font-mono text-[12px] tabular-nums text-stone">{String(n).padStart(2, '0')}</div>
      <div className="min-w-0 flex-1 space-y-2 pb-2">
        <div className="text-[14px] font-medium text-obsidian">{title}</div>
        <div className="space-y-2 text-[13px] leading-relaxed text-charcoal">{children}</div>
      </div>
    </div>
  )
}
