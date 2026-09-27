import { useState } from 'react'
import type { BenchmarkStats, Comparison } from '../api'
import { PlanView } from './PlanTree'
import { Card, Empty, ErrorBox, Tabs, Tag, fmtMs, fmtNum } from './ui'

const scoreNames: Record<string, string> = {
  speed: 'Скорость', query_cost: 'Стоимость плана', rows_examined: 'Просмотренные строки',
  index_usage: 'Использование индексов', stability: 'Стабильность', complexity: 'Сложность SQL',
}

function RunsChart({ a, b }: { a: BenchmarkStats; b: BenchmarkStats }) {
  const max = Math.max(...a.times_ms, ...b.times_ms, 0.001)
  const n = Math.max(a.times_ms.length, b.times_ms.length)
  const w = 520, h = 140, pad = 24, gw = (w - pad) / n
  return (
    <svg viewBox={`0 0 ${w} ${h + 18}`} className="w-full max-w-[560px]" role="img" aria-label="Время по прогонам">
      <line x1={pad} y1={h} x2={w} y2={h} stroke="var(--color-line)" />
      {Array.from({ length: n }).map((_, i) => {
        const x = pad + i * gw
        const ha = ((a.times_ms[i] ?? 0) / max) * (h - 8)
        const hb = ((b.times_ms[i] ?? 0) / max) * (h - 8)
        const bw = Math.min(18, gw / 2 - 4)
        return (
          <g key={i}>
            <rect x={x + gw / 2 - bw - 1} y={h - ha} width={bw} height={ha} rx={2} fill="var(--color-muted)">
              <title>исходный, прогон {i + 1}: {fmtMs(a.times_ms[i])}</title>
            </rect>
            <rect x={x + gw / 2 + 1} y={h - hb} width={bw} height={hb} rx={2} fill="var(--color-accent)">
              <title>оптимизированный, прогон {i + 1}: {fmtMs(b.times_ms[i])}</title>
            </rect>
            <text x={x + gw / 2} y={h + 14} textAnchor="middle" fontSize="10" fill="var(--color-muted)">{i + 1}</text>
          </g>
        )
      })}
      <text x={0} y={10} fontSize="10" fill="var(--color-muted)">{fmtMs(max)}</text>
    </svg>
  )
}

function StatsTable({ a, b }: { a: BenchmarkStats; b: BenchmarkStats }) {
  const rows: [string, (s: BenchmarkStats) => string][] = [
    ['Медиана', s => fmtMs(s.median_ms)],
    ['Среднее', s => fmtMs(s.mean_ms)],
    ['Минимум', s => fmtMs(s.min_ms)],
    ['Максимум', s => fmtMs(s.max_ms)],
    ['Станд. отклонение', s => fmtMs(s.stdev_ms)],
    ['Строк возвращено', s => fmtNum(s.rows_returned)],
    ['Строк просмотрено', s => fmtNum(s.rows_examined)],
    ['Чтений с диска (блоки)', s => fmtNum(s.disk_reads)],
    ['Попаданий в буфер', s => fmtNum(s.buffer_hits)],
  ]
  return (
    <table className="w-full text-[13px]">
      <thead><tr className="text-left text-stone"><th className="py-1 font-normal"></th><th className="font-normal">Исходный</th><th className="font-normal">Оптимизированный</th></tr></thead>
      <tbody>
        {rows.filter(([, f]) => f(a) !== '—' || f(b) !== '—').map(([label, f]) => (
          <tr key={label} className="border-t border-line"><td className="py-1.5 text-stone">{label}</td><td className="tabular-nums">{f(a)}</td><td className="tabular-nums">{f(b)}</td></tr>
        ))}
      </tbody>
    </table>
  )
}

export function ComparisonView({ cmp }: { cmp: Comparison }) {
  const [planTab, setPlanTab] = useState<'original' | 'optimized'>('original')
  const eq = cmp.equivalence
  const a = cmp.benchmark_original, b = cmp.benchmark_optimized
  const faster = cmp.speedup != null && cmp.speedup >= 1
  return (
    <div className="space-y-4">
      {cmp.errors.map((e, i) => <ErrorBox key={i}>{e}</ErrorBox>)}

      {a && b && cmp.speedup != null && (
        <div className="rounded-lg border border-line bg-panel-2 p-5">
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <span className="text-3xl font-medium tabular-nums">{fmtMs(a.median_ms)} → {fmtMs(b.median_ms)}</span>
            <span className={`text-xl font-medium ${faster ? 'text-good' : 'text-bad'}`}>
              {faster ? `${cmp.speedup.toFixed(2)}x быстрее` : `${(1 / cmp.speedup).toFixed(2)}x медленнее`}
            </span>
            {cmp.improvement_pct != null && <span className="text-stone">({cmp.improvement_pct > 0 ? '−' : '+'}{Math.abs(cmp.improvement_pct)}% времени)</span>}
          </div>
          <div className="mt-1 text-[12px] text-stone">
            Медиана {a.runs} прогонов после {a.warmup} прогревочных; запуски исходного и оптимизированного запроса чередовались.
            Время измерено на клиенте и включает передачу результата.
          </div>
          {cmp.plan_changes.length > 0 && (
            <ul className="mt-3 space-y-0.5 text-[13px]">{cmp.plan_changes.map((c, i) => <li key={i} className="mono">• {c}</li>)}</ul>
          )}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Эквивалентность результата">
          <div className="flex items-center gap-2">
            {eq.status === 'equivalent' && <Tag tone="good">РЕЗУЛЬТАТ СОВПАДАЕТ</Tag>}
            {eq.status === 'different' && <Tag tone="bad">РЕЗУЛЬТАТ ИЗМЕНИЛСЯ — REJECT</Tag>}
            {eq.status === 'error' && <Tag tone="bad">ОШИБКА</Tag>}
            {eq.status === 'skipped' && <Tag>не проверялась</Tag>}
            {eq.order_sensitive && eq.order_match != null && (
              <Tag tone={eq.order_match ? 'good' : 'warn'}>порядок {eq.order_match ? 'совпадает' : 'отличается'}</Tag>
            )}
          </div>
          {eq.checksum_original && (
            <div className="mono mt-3 space-y-0.5 text-[12px] text-stone">
              <div>исходный: {eq.rows_original} строк, checksum {eq.checksum_original}</div>
              <div>оптимизированный: {eq.rows_optimized} строк, checksum {eq.checksum_optimized}</div>
            </div>
          )}
          {eq.details.map((d, i) => <p key={i} className="mt-2 text-[13px] text-warn">{d}</p>)}
          {eq.sample_only_in_original.length > 0 && (
            <div className="mt-2 text-[12px]"><div className="text-stone">Только в исходном (пример):</div>
              <pre className="mono overflow-x-auto text-[11.5px]">{eq.sample_only_in_original.map(r => JSON.stringify(r)).join('\n')}</pre></div>
          )}
          {eq.sample_only_in_optimized.length > 0 && (
            <div className="mt-2 text-[12px]"><div className="text-stone">Только в оптимизированном (пример):</div>
              <pre className="mono overflow-x-auto text-[11.5px]">{eq.sample_only_in_optimized.map(r => JSON.stringify(r)).join('\n')}</pre></div>
          )}
          <p className="mt-3 text-[12px] text-stone">
            Проверка эмпирическая — на текущих данных БД: сравниваются мультимножества строк (контрольная сумма), число колонок и порядок при ORDER BY.
          </p>
        </Card>

        <Card title="Optimization Score">
          {cmp.score?.score != null ? (
            <>
              <div className="text-3xl font-medium tabular-nums">{cmp.score.score}<span className="text-base text-stone"> / 100</span></div>
              <div className="mt-3 space-y-2">
                {cmp.score.components.map(c => (
                  <div key={c.name}>
                    <div className="flex justify-between text-[12px]"><span>{scoreNames[c.name] ?? c.name} <span className="text-stone">· вес {Math.round(c.weight * 100)}%</span></span><span className="tabular-nums">{c.value}</span></div>
                    <div className="mt-0.5 h-1.5 rounded bg-line"><div className="h-1.5 rounded bg-text" style={{ width: `${c.value}%` }} /></div>
                    <div className="text-[11.5px] text-stone">{c.detail}</div>
                  </div>
                ))}
              </div>
            </>
          ) : <Empty>{cmp.score?.note ?? 'Нет данных для расчёта'}</Empty>}
        </Card>
      </div>

      {a && b && (
        <Card title="Бенчмарк">
          <div className="grid gap-6 lg:grid-cols-2">
            <div>
              <div className="mb-2 flex gap-3 text-[12px] text-stone">
                <span><span className="mr-1 inline-block h-2 w-2 rounded-sm bg-muted" />исходный</span>
                <span><span className="mr-1 inline-block h-2 w-2 rounded-sm bg-accent" />оптимизированный</span>
              </div>
              <RunsChart a={a} b={b} />
            </div>
            <StatsTable a={a} b={b} />
          </div>
        </Card>
      )}

      {(cmp.plan_original || cmp.plan_optimized) && (
        <Card title="Планы выполнения">
          <Tabs tabs={[{ id: 'original', label: 'Исходный' }, { id: 'optimized', label: 'Оптимизированный' }]} active={planTab} onChange={setPlanTab} />
          <div className="mt-3">
            {planTab === 'original' && cmp.plan_original && <PlanView plan={cmp.plan_original} />}
            {planTab === 'optimized' && cmp.plan_optimized && <PlanView plan={cmp.plan_optimized} />}
          </div>
        </Card>
      )}
    </div>
  )
}
