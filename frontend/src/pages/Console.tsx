import { useCallback, useEffect, useState } from 'react'
import type { AskResult, ConsoleResult, Connection, DbOverview, ModelsInfo, PlanSummary, TableInfo } from '../api'
import { api } from '../api'
import { DbIntro, schemaOf } from '../components/DbIntro'
import { PlanView } from '../components/PlanTree'
import { ResultView } from '../components/ResultView'
import { setCompletionSchema, SqlEditor } from '../components/SqlEditor'
import { Button, Card, Empty, ErrorBox, Spinner, Tabs } from '../components/ui'

// История и избранное — удобство конкретного пользователя, хранятся в браузере
interface Saved { sql: string; at: string; conn: number | null; star?: boolean }
const KEY = 'aidbo.console.history'
const load = (): Saved[] => { try { return JSON.parse(localStorage.getItem(KEY) || '[]') } catch { return [] } }
const store = (v: Saved[]) => { try { localStorage.setItem(KEY, JSON.stringify(v)) } catch { /* хранилище недоступно */ } }

const SAMPLE_QUESTIONS = ['Сколько заказов в каждом статусе?', 'Топ-10 клиентов по сумме заказов', 'Как менялась выручка по месяцам?']

export function Console({ connections, models, onOptimize, onNavigate }: {
  connections: Connection[]; models: ModelsInfo | null
  onOptimize: (sql: string, connectionId: number | null) => void; onNavigate: (p: string) => void
}) {
  const [connId, setConnId] = useState<number | null>(null)
  const [sql, setSql] = useState('SELECT *\nFROM ')
  const [question, setQuestion] = useState('')
  const [model, setModel] = useState('')
  const [busy, setBusy] = useState<'run' | 'plan' | 'ask' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ConsoleResult | null>(null)
  const [answer, setAnswer] = useState<AskResult | null>(null)
  const [plan, setPlan] = useState<PlanSummary | null>(null)
  const [side, setSide] = useState<'history' | 'star'>('history')
  const [saved, setSaved] = useState<Saved[]>(load)

  useEffect(() => { if (connId == null && connections.length) setConnId(connections[0].id) }, [connections, connId])
  useEffect(() => { if (models?.default && !model) setModel(models.default) }, [models, model])
  // обзор базы: схемы, рабочая схема, сохранённый анализ; таблицы рабочей схемы → автодополнение
  const [overview, setOverview] = useState<DbOverview | null>(null)
  const [tables, setTables] = useState<TableInfo[]>([])
  const [introBusy, setIntroBusy] = useState(false)
  useEffect(() => {
    if (connId == null) return
    setOverview(null)
    api.consoleOverview(connId).then(setOverview).catch(() => setOverview(null))
    api.schema(connId).then(s => setTables(s.tables)).catch(() => setTables([]))
  }, [connId])
  const workSchema = overview?.selected ?? null
  useEffect(() => {
    setCompletionSchema(workSchema && overview ? tables.filter(t => schemaOf(t.name, overview.default) === workSchema) : tables)
  }, [tables, workSchema, overview])

  const choose = async (schemaName: string, analyze: boolean) => {
    if (connId == null) return
    setIntroBusy(true); setError(null)
    try {
      const r = await api.consoleProfile({ connection_id: connId, schema_name: schemaName, model: model || null, analyze })
      setOverview(o => o && { ...o, selected: r.selected, profile: r.profile ?? (analyze ? null : o.selected === r.selected ? o.profile : null) })
    } catch (e) { setError((e as Error).message) } finally { setIntroBusy(false) }
  }
  const runSuggested = (q: string) => { setSql(q); run(q) }

  const remember = useCallback((q: string) => {
    setSaved(prev => {
      const starred = prev.filter(s => s.star)
      const rest = prev.filter(s => !s.star && s.sql.trim() !== q.trim())
      const next = [...starred, { sql: q, at: new Date().toISOString(), conn: connId }, ...rest].slice(0, 60)
      store(next)
      return next
    })
  }, [connId])

  const run = useCallback(async (text = sql) => {
    if (connId == null || !text.trim()) return
    setBusy('run'); setError(null); setPlan(null)
    try { setResult(await api.consoleRun({ connection_id: connId, sql: text })); setAnswer(null); remember(text) }
    catch (e) { setError((e as Error).message) } finally { setBusy(null) }
  }, [connId, sql, remember])

  const explain = async () => {
    if (connId == null) return
    setBusy('plan'); setError(null)
    try { setPlan(await api.explain({ sql, connection_id: connId })) } catch (e) { setError((e as Error).message) } finally { setBusy(null) }
  }

  const ask = async () => {
    if (connId == null || !question.trim()) return
    setBusy('ask'); setError(null); setPlan(null)
    try {
      const a = await api.ask({ connection_id: connId, question, model: model || null, schema_name: workSchema })
      setAnswer(a); setResult(a.result); setSql(a.sql); remember(a.sql)
    } catch (e) { setError((e as Error).message) } finally { setBusy(null) }
  }

  const toggleStar = (i: number) => setSaved(prev => { const next = prev.map((s, k) => k === i ? { ...s, star: !s.star } : s); store(next); return next })
  const list = saved.map((s, i) => ({ ...s, i })).filter(s => side === 'star' ? s.star : true)
  const llm = (models?.models ?? []).filter(m => !m.startsWith('baseline'))

  if (!connections.length) return (
    <Card><Empty>Консоль работает с подключённой базой. Подключите свою или демонстрационную базу в разделе «Базы данных» — <button className="underline" onClick={() => onNavigate('databases')}>перейти</button>.</Empty></Card>
  )

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_300px]">
      <div className="min-w-0 space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="kicker text-stone">База</span>
          <select value={connId ?? ''} onChange={e => { setConnId(Number(e.target.value)); setResult(null); setAnswer(null); setPlan(null) }} className="max-w-[420px]">
            {connections.map(c => <option key={c.id} value={c.id}>{c.name} · {c.dbms}</option>)}
          </select>
          {workSchema && <span className="font-mono text-[12px] text-stone">схема {workSchema}</span>}
        </div>
        {overview && overview.schemas.length > 0 && (
          <DbIntro key={connId} overview={overview} busy={introBusy} hasModel={llm.length > 0} onChoose={choose} onRun={runSuggested} onShowEr={() => onNavigate(`databases/er/${connId}`)} />
        )}
        <div className="card flex flex-wrap items-center gap-2 p-3">
          <span className="kicker text-stone">Спросить базу</span>
          <input className="min-w-[260px] flex-1" value={question} onChange={e => setQuestion(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') ask() }} placeholder="Спросите на русском, например: сколько записей добавлено за последний месяц?" />
          {llm.length > 0 && (
            <select value={model} onChange={e => setModel(e.target.value)} className="max-w-[210px]">
              {llm.map(m => <option key={m} value={m}>{m.split(':').slice(1).join(':')}</option>)}
            </select>
          )}
          <Button variant="primary" onClick={ask} disabled={busy != null || !question.trim() || !llm.length}>{busy === 'ask' && <Spinner />} Спросить</Button>
          <div className="flex w-full flex-wrap gap-1.5 pt-1">
            {!llm.length
              ? <span className="text-[12px] text-stone">Нужна модель ИИ — настройка в разделе «Установка и помощь»</span>
              : connections.find(c => c.id === connId)?.database === 'shop' && SAMPLE_QUESTIONS.map(q => <button key={q} className="rounded-full px-2.5 py-0.5 text-[12px] text-charcoal shadow-[0_0_0_1px_#ebebeb] hover:text-obsidian" onClick={() => setQuestion(q)}>{q}</button>)}
          </div>
        </div>

        {answer && (
          <div className="card space-y-1 p-3 text-[13.5px]">
            <div className="text-obsidian">{answer.explanation}</div>
            <div className="font-mono text-[11.5px] text-stone">
              {answer.model.split(':').slice(1).join(':')} · {(answer.latency_ms / 1000).toFixed(1)} с
              {answer.attempts.length > 1 && ` · запрос исправлен после ошибки: ${answer.attempts[0].error}`}
            </div>
          </div>
        )}

        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" onClick={() => run()} disabled={busy != null} title="Ctrl+Enter">{busy === 'run' && <Spinner />} Выполнить</Button>
            <Button onClick={explain} disabled={busy != null}>{busy === 'plan' && <Spinner />} План</Button>
            <Button onClick={() => onOptimize(sql, connId)} disabled={!sql.trim()}>Оптимизировать</Button>
            <span className="ml-auto font-mono text-[11px] text-ash">ctrl+enter — выполнить · только чтение</span>
          </div>
          <SqlEditor value={sql} onChange={setSql} height={220} onRun={() => run()} />
        </div>

        {error && <ErrorBox>{error}</ErrorBox>}
        {plan && <Card title="План выполнения"><PlanView plan={plan} /></Card>}
        {result && <ResultView key={result.executed_sql + result.elapsed_ms} result={result} chart={answer?.chart} />}
        {!result && !error && <div className="text-[13px] text-stone">Напишите запрос и нажмите «Выполнить» или задайте вопрос на русском — ИИ составит запрос по структуре вашей базы. Выполняются только запросы на чтение; показываются первые 500 строк.</div>}
      </div>

      <aside className="card h-fit p-3">
        <Tabs tabs={[{ id: 'history', label: 'История' }, { id: 'star', label: 'Избранное' }]} active={side} onChange={setSide} />
        <div className="mt-3 max-h-[640px] space-y-1.5 overflow-auto">
          {!list.length && <div className="text-[12.5px] text-stone">{side === 'star' ? 'Отметьте запрос звёздочкой в истории' : 'Здесь появятся выполненные запросы'}</div>}
          {list.map(s => (
            <div key={s.i} className="group flex gap-2 rounded-md p-2 hover:bg-paper-white">
              <button className="min-w-0 flex-1 text-left" onClick={() => { setSql(s.sql); if (s.conn != null && connections.some(c => c.id === s.conn)) setConnId(s.conn) }}>
                <div className="line-clamp-3 whitespace-pre-wrap break-all font-mono text-[11.5px] text-obsidian">{s.sql}</div>
                <div className="mt-0.5 font-mono text-[10.5px] text-ash">{new Date(s.at).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</div>
              </button>
              <button onClick={() => toggleStar(s.i)} className={`text-[14px] ${s.star ? 'text-obsidian' : 'text-ash opacity-0 group-hover:opacity-100'}`} title="В избранное">{s.star ? '★' : '☆'}</button>
            </div>
          ))}
        </div>
      </aside>
    </div>
  )
}
