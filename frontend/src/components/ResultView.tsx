import { useMemo, useState } from 'react'
import type { ChartSpec, ConsoleResult } from '../api'
import { Button, Tabs, fmtMs } from './ui'

type Cell = string | number | boolean | null

// Диаграмма напрашивается, если есть столбец-подпись и числовой столбец
export function guessChart(r: ConsoleResult): ChartSpec | null {
  if (r.rows.length < 2 || r.rows.length > 100 || r.columns.length < 2) return null
  if (r.rows.some(row => typeof row[0] === 'number')) return null  // первый столбец должен быть подписью, а не числом
  const numeric = r.columns.findIndex((_, i) => i > 0 && r.rows.every(row => typeof row[i] === 'number' || row[i] == null))
  if (numeric < 0) return null
  const dateLike = r.rows.every(row => typeof row[0] === 'string' && /^\d{4}-\d{2}/.test(row[0] as string))
  return { type: dateLike ? 'line' : 'bar', x: r.columns[0], y: r.columns[numeric] }
}

function toCsv(r: ConsoleResult) {
  const esc = (v: Cell) => v == null ? '' : /[",;\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v)
  return '﻿' + [r.columns, ...r.rows].map(row => row.map(esc).join(';')).join('\r\n')
}

function download(name: string, data: BlobPart, type: string) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([data], { type }))
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}

export function ResultTable({ result }: { result: ConsoleResult }) {
  return (
    <div className="max-h-[480px] overflow-auto rounded-md shadow-[0_0_0_1px_#ebebeb]">
      <table className="w-full border-collapse text-[12.5px]">
        <thead className="sticky top-0 bg-paper-white">
          <tr>
            <th className="w-10 border-b border-line px-2 py-1.5 text-right font-mono text-[11px] font-normal text-ash">#</th>
            {result.columns.map((c, i) => <th key={i} className="border-b border-line px-2 py-1.5 text-left font-mono text-[11.5px] font-medium text-obsidian">{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {result.rows.map((row, i) => (
            <tr key={i} className="hover:bg-paper-white">
              <td className="border-b border-line/60 px-2 py-1 text-right font-mono text-[11px] text-ash">{i + 1}</td>
              {row.map((v, j) => (
                <td key={j} className={`max-w-[360px] truncate border-b border-line/60 px-2 py-1 font-mono ${typeof v === 'number' ? 'text-right tabular-nums' : ''} ${v == null ? 'text-ash' : 'text-obsidian'}`} title={v == null ? 'NULL' : String(v)}>
                  {v == null ? 'NULL' : typeof v === 'number' && !Number.isInteger(v) ? v.toLocaleString('ru-RU', { maximumFractionDigits: 4 }) : String(v)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Chart({ result, spec }: { result: ConsoleResult; spec: ChartSpec }) {
  const xi = result.columns.indexOf(spec.x), yi = result.columns.indexOf(spec.y)
  const pts = result.rows.slice(0, 60).map(r => ({ label: String(r[xi] ?? '—').replace(/T00:00:00$/, ''), v: Number(r[yi] ?? 0) }))
  const W = 720, H = 300, L = 64, B = 64, T = 12
  const max = Math.max(...pts.map(p => p.v), 0) || 1
  const step = (W - L - 8) / Math.max(pts.length, 1)
  const y = (v: number) => T + (H - T - B) * (1 - v / max)
  const ticks = [0, 0.25, 0.5, 0.75, 1].map(k => k * max)
  const fmt = (v: number) => Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(1)} млн` : Math.abs(v) >= 1e3 ? `${(v / 1e3).toFixed(0)} тыс` : v.toFixed(v % 1 ? 1 : 0)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`${spec.y} по ${spec.x}`}>
      {ticks.map((t, i) => (
        <g key={i}>
          <line x1={L} x2={W - 4} y1={y(t)} y2={y(t)} stroke="#ebebeb" />
          <text x={L - 6} y={y(t) + 4} textAnchor="end" fontSize="10.5" fill="#8f8f8f" fontFamily="Geist Mono Variable, monospace">{fmt(t)}</text>
        </g>
      ))}
      {spec.type === 'bar'
        ? pts.map((p, i) => <rect key={i} x={L + i * step + step * 0.15} y={y(p.v)} width={step * 0.7} height={Math.max(0, H - B - y(p.v))} fill="#171717" rx="2"><title>{`${p.label}: ${p.v.toLocaleString('ru-RU')}`}</title></rect>)
        : <>
          <polyline fill="none" stroke="#297a3a" strokeWidth="2" points={pts.map((p, i) => `${L + i * step + step / 2},${y(p.v)}`).join(' ')} />
          {pts.map((p, i) => <circle key={i} cx={L + i * step + step / 2} cy={y(p.v)} r="3" fill="#297a3a"><title>{`${p.label}: ${p.v.toLocaleString('ru-RU')}`}</title></circle>)}
        </>}
      {pts.map((p, i) => (pts.length <= 24 || i % Math.ceil(pts.length / 24) === 0) && (
        <text key={i} transform={`translate(${L + i * step + step / 2},${H - B + 12}) rotate(35)`} fontSize="10.5" fill="#4d4d4d">{p.label.length > 14 ? p.label.slice(0, 13) + '…' : p.label}</text>
      ))}
    </svg>
  )
}

export function ResultView({ result, chart }: { result: ConsoleResult; chart?: ChartSpec | null }) {
  const spec = useMemo(() => chart ?? guessChart(result), [chart, result])
  const [view, setView] = useState<'table' | 'chart'>(chart ? 'chart' : 'table')
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        {spec && <Tabs tabs={[{ id: 'table', label: 'Таблица' }, { id: 'chart', label: 'График' }]} active={view} onChange={setView} />}
        <span className="font-mono text-[12px] text-stone">
          {result.row_count.toLocaleString('ru-RU')} {result.truncated ? '(показаны первые)' : ''} строк · {fmtMs(result.elapsed_ms)}
        </span>
        <span className="ml-auto" />
        <Button variant="ghost" onClick={() => download('result.csv', toCsv(result), 'text/csv;charset=utf-8')}>CSV</Button>
      </div>
      {!result.columns.length ? <div className="text-[13px] text-stone">Запрос не вернул столбцов</div>
        : view === 'chart' && spec ? <div className="card p-3"><Chart result={result} spec={spec} /></div>
          : <ResultTable result={result} />}
    </div>
  )
}

export { download }
