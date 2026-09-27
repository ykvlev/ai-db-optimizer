import type { PlanNode, PlanSummary } from '../api'
import { Tag, fmtMs, fmtNum } from './ui'

function tone(type: string): 'bad' | 'warn' | 'good' | 'muted' {
  const t = type.toLowerCase()
  if (t.includes('full table') || t.includes('seq scan')) return 'bad'
  if (t.includes('full index') || t.includes('sort') || t.includes('filesort')) return 'warn'
  if (t.includes('index') || t.includes('lookup') || t.includes('const')) return 'good'
  return 'muted'
}

function Node({ node, depth }: { node: PlanNode; depth: number }) {
  const color = { bad: 'border-bad/60', warn: 'border-warn/60', good: 'border-good/60', muted: 'border-line' }[tone(node.type)]
  return (
    <div className={depth ? 'ml-5 border-l border-line pl-4' : ''}>
      <div className={`my-1.5 rounded-md border-l-4 ${color} bg-panel-2 px-3 py-2`}>
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{node.type}</span>
          {node.table && <span className="mono text-obsidian">{node.table}</span>}
          {node.index && <Tag tone="good">idx: {node.index}</Tag>}
        </div>
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[12px] text-stone">
          {node.rows != null && <span>строк (оценка): <b className="text-text">{fmtNum(node.rows)}</b></span>}
          {node.actual_rows != null && <span>строк (факт): <b className="text-text">{fmtNum(node.actual_rows)}</b></span>}
          {node.cost != null && <span>cost: <b className="text-text">{node.cost.toLocaleString('ru-RU')}</b></span>}
          {node.time_ms != null && <span>время: <b className="text-text">{fmtMs(node.time_ms)}</b></span>}
        </div>
        {node.filter && <div className="mono mt-1 break-all text-[11.5px] text-stone">условие: {node.filter}</div>}
        {node.extra.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">{node.extra.map((e, i) => <Tag key={i}>{e}</Tag>)}</div>
        )}
      </div>
      {node.children.map((c, i) => <Node key={i} node={c} depth={depth + 1} />)}
    </div>
  )
}

export function PlanView({ plan }: { plan: PlanSummary }) {
  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-2 text-[12px]">
        <Tag tone="accent">{plan.dbms === 'mysql' ? 'EXPLAIN FORMAT=JSON' : plan.analyzed ? 'EXPLAIN ANALYZE, BUFFERS' : 'EXPLAIN'}</Tag>
        {plan.total_cost != null && <Tag>total cost: {plan.total_cost.toLocaleString('ru-RU')}</Tag>}
        {plan.estimated_rows_examined != null && <Tag>просматривается строк: {fmtNum(plan.estimated_rows_examined)}</Tag>}
        {plan.full_scans.length > 0 && <Tag tone="bad">полные сканирования: {plan.full_scans.join(', ')}</Tag>}
        {plan.uses_filesort && <Tag tone="warn">сортировка</Tag>}
        {plan.uses_temporary && <Tag tone="warn">временная таблица</Tag>}
      </div>
      {plan.root && <Node node={plan.root} depth={0} />}
      <details className="mt-3">
        <summary className="cursor-pointer text-[12px] text-stone">Исходный план (JSON)</summary>
        <pre className="mono mt-2 max-h-96 overflow-auto rounded-md border border-line bg-bg p-3 text-[11.5px]">{JSON.stringify(plan.raw, null, 2)}</pre>
      </details>
    </div>
  )
}
