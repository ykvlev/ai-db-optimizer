import { useEffect, useState } from 'react'
import type { Comparison, Connection } from '../api'
import { api } from '../api'
import { ComparisonView } from '../components/ComparisonView'
import { SqlEditor } from '../components/SqlEditor'
import { Button, Empty, ErrorBox, Spinner } from '../components/ui'

export function Compare({ connections, onRun }: { connections: Connection[]; onRun: () => void }) {
  const [connId, setConnId] = useState<number | null>(null)
  const [original, setOriginal] = useState("SELECT id, user_id, total\nFROM orders\nWHERE DATE(created_at) = '2025-03-15'\nORDER BY id")
  const [optimized, setOptimized] = useState("SELECT id, user_id, total\nFROM orders\nWHERE created_at >= '2025-03-15' AND created_at < '2025-03-16'\nORDER BY id")
  const [runs, setRuns] = useState(5)
  const [warmup, setWarmup] = useState(2)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<Comparison | null>(null)

  useEffect(() => { if (connId == null && connections.length) setConnId(connections[0].id) }, [connections, connId])

  const run = async () => {
    if (connId == null) return
    setBusy(true); setError(null)
    try {
      setResult(await api.compare({ original_sql: original, optimized_sql: optimized, connection_id: connId, runs, warmup }))
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
        <label className="text-[13px] text-muted">прогонов <input type="number" min={1} max={50} value={runs} onChange={e => setRuns(Number(e.target.value))} className="w-16" /></label>
        <label className="text-[13px] text-muted">прогрев <input type="number" min={0} max={10} value={warmup} onChange={e => setWarmup(Number(e.target.value))} className="w-16" /></label>
        <Button variant="primary" onClick={run} disabled={busy || connId == null}>{busy && <Spinner />} Сравнить</Button>
      </div>
      {!connections.length && <Empty>Сравнение выполняет оба запроса на реальной БД. Добавьте подключение в разделе «Базы данных».</Empty>}
      <div className="grid gap-4 lg:grid-cols-2">
        <div><div className="mb-1 text-[12px] font-semibold tracking-wider text-muted">ORIGINAL</div><SqlEditor value={original} onChange={setOriginal} height={220} /></div>
        <div><div className="mb-1 text-[12px] font-semibold tracking-wider text-muted">OPTIMIZED</div><SqlEditor value={optimized} onChange={setOptimized} height={220} /></div>
      </div>
      {error && <ErrorBox>{error}</ErrorBox>}
      {result && <ComparisonView cmp={result} />}
    </div>
  )
}
