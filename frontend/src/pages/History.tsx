import { useEffect, useState } from 'react'
import type { Comparison, OptimizeResponse, RunRow } from '../api'
import { api } from '../api'
import { ComparisonView } from '../components/ComparisonView'
import { IssueList } from '../components/IssueList'
import { Button, Card, Code, Empty, Tag } from '../components/ui'

type Detail = Awaited<ReturnType<typeof api.run>>

const verdictTone = (v?: string | null) => v === 'accepted' ? 'good' : v === 'rejected' || v === 'failed' ? 'bad' : v === 'unverified' ? 'warn' : 'muted'
const kindName: Record<string, string> = { analyze: 'анализ', optimize: 'AI-оптимизация', compare: 'сравнение' }

export function History({ refreshKey }: { refreshKey: number }) {
  const [rows, setRows] = useState<RunRow[]>([])
  const [detail, setDetail] = useState<Detail | null>(null)

  useEffect(() => { api.runs(200).then(setRows).catch(() => setRows([])) }, [refreshKey])

  const open = async (id: number) => setDetail(await api.run(id))

  const result = detail?.result as (Partial<OptimizeResponse> & Partial<Comparison> & { issues?: never }) | undefined
  const cmp: Comparison | null | undefined = detail?.kind === 'compare' ? (result as unknown as Comparison) : result?.comparison

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(520px,1fr)_1fr]">
      <Card title="Запуски" actions={
        <div className="flex gap-2">
          {['csv', 'xlsx', 'json'].map(f => <a key={f} href={`/api/export/runs?format=${f}`}><Button variant="ghost">⤓ {f.toUpperCase()}</Button></a>)}
        </div>
      }>
        {!rows.length ? <Empty>История пуста</Empty> : (
          <div className="max-h-[calc(100vh-180px)] overflow-auto">
            <table className="w-full text-[12.5px]">
              <thead className="sticky top-0 bg-panel text-left text-stone">
                <tr><th className="py-1.5 font-normal">#</th><th className="font-normal">Тип</th><th className="font-normal">Запрос</th><th className="font-normal">Итог</th><th className="font-normal">Ускорение</th></tr>
              </thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.id} onClick={() => open(r.id)} className={`cursor-pointer border-t border-line hover:bg-panel-2 ${detail?.id === r.id ? 'bg-panel-2' : ''}`}>
                    <td className="py-1.5 pr-2 text-stone">{r.id}</td>
                    <td className="pr-2">{kindName[r.kind] ?? r.kind}<div className="text-[11px] text-stone">{r.dbms}{r.model ? ` · ${r.model}` : ''}</div></td>
                    <td className="mono max-w-[280px] truncate pr-2 text-[11.5px]" title={r.sql}>{r.sql}</td>
                    <td className="pr-2">{r.verdict ? <Tag tone={verdictTone(r.verdict)}>{r.verdict}</Tag> : r.equivalent != null ? <Tag tone={r.equivalent ? 'good' : 'bad'}>{r.equivalent ? 'эквивалентен' : 'отличается'}</Tag> : <span className="text-stone">{r.issues} пробл.</span>}</td>
                    <td className="tabular-nums">{r.speedup != null ? `${r.speedup.toFixed(2)}x` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="min-w-0 space-y-4">
        {!detail ? <Empty>Выберите запуск</Empty> : (
          <>
            <Card title={`Запуск #${detail.id} · ${kindName[detail.kind] ?? detail.kind}`}>
              <div className="mb-2 flex flex-wrap gap-2 text-[12px]">
                <Tag>{new Date(detail.started_at).toLocaleString('ru-RU')}</Tag>
                <Tag>{detail.dbms} {detail.dbms_version ?? ''}</Tag>
                <Tag>app v{detail.app_version}</Tag>
                {detail.model && <Tag tone="accent">{detail.model}</Tag>}
                {detail.prompt_version && <Tag>prompt {detail.prompt_version}</Tag>}
              </div>
              <Code>{detail.sql}</Code>
              {result?.verdict_reason && <p className="mt-2 text-[13px]"><Tag tone={verdictTone(result.verdict)}>{result.verdict}</Tag> {result.verdict_reason}</p>}
              {result?.optimized_query && <div className="mt-3"><div className="mb-1 text-[12px] text-stone">Оптимизированный запрос</div><Code>{result.optimized_query}</Code></div>}
            </Card>
            {detail.kind === 'analyze' && Array.isArray((result as { issues?: unknown })?.issues) && (
              <Card title="Проблемы"><IssueList issues={(result as unknown as { issues: never[] }).issues} /></Card>
            )}
            {cmp && <ComparisonView cmp={cmp} />}
          </>
        )}
      </div>
    </div>
  )
}
