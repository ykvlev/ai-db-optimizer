import type { Issue } from '../api'
import { Empty, SeverityBadge, Tag } from './ui'

const sourceLabel = { rule: 'правило', plan: 'план', ai: 'ИИ' }

export function IssueList({ issues }: { issues: Issue[] }) {
  if (!issues.length) return <Empty>Проблем не обнаружено</Empty>
  return (
    <ul className="space-y-2">
      {issues.map((i, k) => (
        <li key={k} className="rounded-md border border-line bg-panel-2 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <SeverityBadge severity={i.severity} />
            <span className="font-semibold">{i.title}</span>
            <span className="mono text-[11px] text-muted">{i.code}</span>
            <span className="ml-auto"><Tag>{sourceLabel[i.source]}</Tag></span>
          </div>
          <p className="mt-1.5 text-[13px] leading-relaxed text-text/90">{i.description}</p>
          {i.suggestion && <p className="mt-1.5 text-[13px] text-good">→ {i.suggestion}</p>}
        </li>
      ))}
    </ul>
  )
}
