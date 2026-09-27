import { useEffect, useState } from 'react'
import type { Comparison, CompareDraft, Connection } from '../api'
import { api } from '../api'
import { ComparisonView } from '../components/ComparisonView'
import { SqlEditor } from '../components/SqlEditor'
import { Button, Empty, ErrorBox, Spinner } from '../components/ui'

export function Compare({ connections, onRun, draft }: { connections: Connection[]; onRun: () => void; draft?: CompareDraft | null }) {
  const [connId, setConnId] = useState<number | null>(null)
  const [original, setOriginal] = useState("SELECT id, user_id, total\nFROM orders\nWHERE DATE(created_at) = '2025-03-15'\nORDER BY id")
  const [optimized, setOptimized] = useState("SELECT id, user_id, total\nFROM orders\nWHERE created_at >= '2025-03-15' AND created_at < '2025-03-16'\nORDER BY id")
  const [runs, setRuns] = useState(5)
  const [warmup, setWarmup] = useState(2)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<Comparison | null>(null)

  useEffect(() => { if (connId == null && connections.length) setConnId(connections[0].id) }, [connections, connId])

  // пара запросов из SQL Analyzer: подставляем и сразу сравниваем на выбранной БД
  useEffect(() => {
    if (!draft) return
    const c = draft.connectionId ?? connId
    setOriginal(draft.original); setOptimized(draft.optimized); setResult(null); setFrom(draft.source)
    if (draft.connectionId != null) setConnId(draft.connectionId)
    if (c != null) run(draft.original, draft.optimized, c)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft?.nonce])

  const [from, setFrom] = useState<string | null>(null)

  const run = async (o = original, n = optimized, c = connId) => {
    if (c == null) return
    setBusy(true); setError(null)
    try {
      setResult(await api.compare({ original_sql: o, optimized_sql: n, connection_id: c, runs, warmup }))
      onRun()
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <select value={connId ?? ''} onChange={e => setConnId(Number(e.target.value))} disabled={!connections.length}>
          {!connections.length && <option value="">Нет подключений</option>}
          {connections.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <label className="text-[13px] text-stone">прогонов <input type="number" min={1} max={50} value={runs} onChange={e => setRuns(Number(e.target.value))} className="w-16" /></label>
        <label className="text-[13px] text-stone">прогрев <input type="number" min={0} max={10} value={warmup} onChange={e => setWarmup(Number(e.target.value))} className="w-16" /></label>
        <Button variant="primary" onClick={() => run()} disabled={busy || connId == null}>{busy && <Spinner />} Сравнить</Button>
      </div>
      {from && <p className="text-[12px] text-stone">Запросы переданы из SQL Analyzer ({from}).{busy ? ' Выполняется сравнение: проверка эквивалентности и бенчмарк…' : ''}</p>}
      {!connections.length && <Empty>Сравнение выполняет оба запроса на реальной БД. Добавьте подключение в разделе «Базы данных».</Empty>}
      <div className="grid gap-4 lg:grid-cols-2">
        <div><div className="mb-1 text-[12px] font-medium tracking-wider text-stone">ORIGINAL</div><SqlEditor value={original} onChange={setOriginal} height={220} /></div>
        <div><div className="mb-1 text-[12px] font-medium tracking-wider text-stone">OPTIMIZED</div><SqlEditor value={optimized} onChange={setOptimized} height={220} /></div>
      </div>
      {error && <ErrorBox>{error}</ErrorBox>}
      {result && <ComparisonView cmp={result} />}
    </div>
  )
}
