import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import type { Connection, DatasetInfo, Dialect, ExperimentDetail, ExperimentMeta, ModelsInfo, Outcome } from '../api'
import { research } from '../api'
import { Button, Card, Code, Empty, ErrorBox, Spinner, Tag, fmtMs } from '../components/ui'

const OUTCOMES: Outcome[] = ['improved', 'unchanged', 'worse', 'invalid', 'error']
const outcomeName: Record<Outcome, string> = { improved: 'Улучшено', unchanged: 'Без изменений', worse: 'Ухудшено', invalid: 'Некорректно', error: 'Сбой вызова' }
const outcomeColor: Record<Outcome, string> = { improved: 'var(--color-good)', unchanged: 'var(--color-muted)', worse: 'var(--color-warn)', invalid: 'var(--color-bad)', error: '#8b7fe0' }
const statusName: Record<ExperimentMeta['status'], string> = { pending: 'в очереди', running: 'выполняется', done: 'завершён', cancelled: 'отменён', failed: 'ошибка', interrupted: 'прерван' }
const statusTone = (s: ExperimentMeta['status']) => s === 'done' ? 'good' : s === 'running' || s === 'pending' ? 'accent' : s === 'failed' ? 'bad' : 'warn'
const x = (v?: number | null) => v == null ? '—' : `${v.toFixed(2)}x`
const pct = (v?: number | null) => v == null ? '—' : `${v.toFixed(1)}%`

export function Experiments({ connections, models, onRun }: { connections: Connection[]; models: ModelsInfo | null; onRun: () => void }) {
  const [datasets, setDatasets] = useState<DatasetInfo[]>([])
  const [experiments, setExperiments] = useState<ExperimentMeta[]>([])
  // поддерживается прямая ссылка #/experiments/<id>
  const [selected, setSelectedState] = useState<number | null>(() => {
    const id = Number(window.location.hash.split('/')[2])
    return Number.isInteger(id) && id > 0 ? id : null
  })
  const setSelected = useCallback((id: number | null) => {
    setSelectedState(id)
    history.replaceState(null, '', id == null ? '#/experiments' : `#/experiments/${id}`)
  }, [])
  const [detail, setDetail] = useState<ExperimentDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showImport, setShowImport] = useState(false)

  const loadLists = useCallback(async () => {
    try {
      const [d, e] = await Promise.all([research.datasets(), research.experiments()])
      setDatasets(d); setExperiments(e)
    } catch (err) { setError((err as Error).message) }
  }, [])
  useEffect(() => { loadLists() }, [loadLists])

  const loadDetail = useCallback(async (id: number) => {
    try { setDetail(await research.experiment(id)) } catch (err) { setError((err as Error).message) }
  }, [])
  useEffect(() => { if (selected != null) loadDetail(selected) }, [selected, loadDetail])

  // пока эксперимент выполняется — обновляем прогресс
  const running = detail?.meta.running || experiments.some(e => e.running)
  useEffect(() => {
    if (!running) return
    const t = setInterval(() => { loadLists(); if (selected != null) loadDetail(selected); onRun() }, 4000)
    return () => clearInterval(t)
  }, [running, selected, loadLists, loadDetail, onRun])

  return (
    <div className="grid gap-4 2xl:grid-cols-[400px_1fr]">
      <div className="space-y-4">
        <NewExperiment datasets={datasets} connections={connections} models={models}
          onCreated={id => { loadLists(); setSelected(id) }} onError={setError} />

        <Card title="Эксперименты">
          {!experiments.length ? <Empty>Экспериментов пока нет</Empty> : (
            <ul className="space-y-1.5">{experiments.map(e => (
              <li key={e.id} onClick={() => setSelected(e.id)}
                className={`cursor-pointer rounded-md border p-2.5 text-[13px] ${selected === e.id ? 'border-accent bg-accent/10' : 'border-line bg-panel-2 hover:border-muted'}`}>
                <div className="flex items-center gap-2">
                  <span className="text-muted">#{e.id}</span><span className="truncate font-semibold">{e.name}</span>
                  <span className="ml-auto"><Tag tone={statusTone(e.status)}>{statusName[e.status]}</Tag></span>
                </div>
                <div className="mt-1 text-[11.5px] text-muted">{e.dataset_version} · {e.dbms} · {e.models.join(', ')}</div>
                <Progress done={e.progress_done} total={e.progress_total} />
              </li>
            ))}</ul>
          )}
        </Card>

        <Card title="Датасеты" actions={<Button variant="ghost" onClick={() => setShowImport(!showImport)}>{showImport ? 'Скрыть' : '+ Импорт'}</Button>}>
          {showImport && <ImportDataset onDone={() => { setShowImport(false); loadLists() }} onError={setError} />}
          <ul className="space-y-1.5 text-[13px]">{datasets.map(d => (
            <li key={d.id} className="rounded-md border border-line bg-panel-2 p-2.5">
              <div className="flex items-center gap-2"><span className="font-semibold">{d.version}</span><Tag>{d.dbms}</Tag>{d.builtin && <Tag tone="accent">встроенный</Tag>}<span className="ml-auto text-muted">{d.size} запр.</span></div>
              {d.description && <div className="mt-1 text-[12px] text-muted">{d.description}</div>}
            </li>
          ))}</ul>
        </Card>
        {error && <ErrorBox>{error}</ErrorBox>}
      </div>

      <div className="min-w-0">
        {!detail ? <Empty>Создайте эксперимент или выберите существующий</Empty>
          : <ExperimentView d={detail} onAction={async act => {
              try {
                if (act === 'cancel') await research.cancel(detail.meta.id)
                if (act === 'resume') await research.resume(detail.meta.id)
                if (act === 'delete') { await research.remove(detail.meta.id); setSelected(null); setDetail(null) }
                await loadLists(); if (act !== 'delete') await loadDetail(detail.meta.id)
              } catch (e) { setError((e as Error).message) }
            }} />}
      </div>
    </div>
  )
}

function Progress({ done, total }: { done: number; total: number }) {
  const p = total ? (done / total) * 100 : 0
  return (
    <div className="mt-1.5 flex items-center gap-2">
      <div className="h-1.5 flex-1 rounded bg-line"><div className="h-1.5 rounded bg-accent transition-all" style={{ width: `${p}%` }} /></div>
      <span className="text-[11px] tabular-nums text-muted">{done}/{total}</span>
    </div>
  )
}

function NewExperiment({ datasets, connections, models, onCreated, onError }: {
  datasets: DatasetInfo[]; connections: Connection[]; models: ModelsInfo | null; onCreated: (id: number) => void; onError: (e: string) => void
}) {
  const [connId, setConnId] = useState<number | null>(null)
  const [datasetId, setDatasetId] = useState<number | null>(null)
  const [chosen, setChosen] = useState<string[]>([])
  const [name, setName] = useState('')
  const [runs, setRuns] = useState(5)
  const [warmup, setWarmup] = useState(2)
  const [prompt, setPrompt] = useState('')
  const [busy, setBusy] = useState(false)

  const conn = connections.find(c => c.id === connId)
  const dbms: Dialect | undefined = conn?.dbms
  const fitting = datasets.filter(d => !dbms || d.dbms === dbms)
  const ds = datasets.find(d => d.id === datasetId)

  useEffect(() => { if (connId == null && connections.length) setConnId(connections[0].id) }, [connections, connId])
  useEffect(() => { if (!fitting.some(d => d.id === datasetId)) setDatasetId(fitting.find(d => d.version.includes('mini'))?.id ?? fitting[0]?.id ?? null) }, [fitting, datasetId])
  useEffect(() => { if (models && !chosen.length) setChosen([models.baseline, ...(models.default && models.default !== models.baseline ? [models.default] : [])]) }, [models, chosen.length])
  useEffect(() => { if (models && !prompt) setPrompt(models.prompts[0] ?? '') }, [models, prompt])

  const toggle = (m: string) => setChosen(c => c.includes(m) ? c.filter(v => v !== m) : [...c, m])
  const calls = (ds?.size ?? 0) * chosen.length

  const submit = async () => {
    if (connId == null || datasetId == null || !chosen.length) return
    setBusy(true)
    try {
      const r = await research.create({ name: name || `${ds?.version} × ${chosen.length} мод.`, dataset_id: datasetId, connection_id: connId, models: chosen, prompt_version: prompt || null, runs, warmup })
      onCreated(r.id)
    } catch (e) { onError((e as Error).message) } finally { setBusy(false) }
  }

  return (
    <Card title="Новый эксперимент">
      {!connections.length ? <Empty>Нужно подключение к БД (раздел «Базы данных»)</Empty> : (
        <div className="grid grid-cols-[90px_minmax(0,1fr)] items-center gap-2 text-[13px]">
          <label className="text-muted">Название</label><input value={name} onChange={e => setName(e.target.value)} placeholder="авто" />
          <label className="text-muted">БД</label>
          <select value={connId ?? ''} onChange={e => setConnId(Number(e.target.value))}>{connections.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
          <label className="text-muted">Датасет</label>
          <select value={datasetId ?? ''} onChange={e => setDatasetId(Number(e.target.value))}>{fitting.map(d => <option key={d.id} value={d.id}>{d.version} ({d.size})</option>)}</select>
          <label className="self-start pt-1 text-muted">Модели</label>
          <div className="min-w-0 space-y-1">{models?.models.map(m => (
            <label key={m} className="flex items-start gap-2"><input type="checkbox" className="mt-0.5 h-4 w-4 shrink-0" checked={chosen.includes(m)} onChange={() => toggle(m)} />
              <span className="min-w-0"><span className="mono break-all text-[12.5px]">{m}</span>
                {m === models.baseline && <span className="block text-[11px] text-muted">без ИИ, базовая линия</span>}</span></label>
          ))}</div>
          <label className="text-muted">Промпт</label>
          <select value={prompt} onChange={e => setPrompt(e.target.value)}>{models?.prompts.map(p => <option key={p}>{p}</option>)}</select>
          <label className="text-muted">Бенчмарк</label>
          <div className="flex gap-2 text-muted">прогонов <input type="number" min={1} max={50} value={runs} onChange={e => setRuns(Number(e.target.value))} className="w-14" />
            прогрев <input type="number" min={0} max={10} value={warmup} onChange={e => setWarmup(Number(e.target.value))} className="w-14" /></div>
        </div>
      )}
      <div className="mt-3 flex items-center gap-3">
        <Button variant="primary" onClick={submit} disabled={busy || !chosen.length || datasetId == null || connId == null}>{busy && <Spinner />} Запустить</Button>
        {calls > 0 && <span className="text-[12px] text-muted">{calls} пар «запрос × модель»</span>}
      </div>
      <p className="mt-2 text-[12px] text-muted">Эксперимент выполняется в фоне. Прерванный эксперимент можно продолжить — выполненные пары не повторяются.</p>
    </Card>
  )
}

function ImportDataset({ onDone, onError }: { onDone: () => void; onError: (e: string) => void }) {
  const [name, setName] = useState('')
  const [version, setVersion] = useState('')
  const [dbms, setDbms] = useState<Dialect>('mysql')
  const [text, setText] = useState('')
  const queries = useMemo(() => text.split(/;\s*(?:\n|$)/).map(s => s.trim()).filter(Boolean), [text])
  const submit = async () => {
    try {
      await research.createDataset({ name, version: version || `${name}-v1`, dbms, queries: queries.map(sql => ({ sql })) })
      onDone()
    } catch (e) { onError((e as Error).message) }
  }
  return (
    <div className="mb-3 space-y-2 rounded-md border border-line p-3 text-[13px]">
      <div className="flex gap-2"><input className="min-w-0 flex-1" placeholder="название" value={name} onChange={e => setName(e.target.value)} />
        <input className="w-32" placeholder="версия" value={version} onChange={e => setVersion(e.target.value)} />
        <select value={dbms} onChange={e => setDbms(e.target.value as Dialect)}><option value="mysql">MySQL</option><option value="postgres">PostgreSQL</option></select></div>
      <textarea className="mono h-40 w-full text-[12px]" placeholder="SELECT-запросы, каждый заканчивается ;" value={text} onChange={e => setText(e.target.value)} />
      <Button onClick={submit} disabled={!name || !queries.length}>Создать ({queries.length} запр.)</Button>
    </div>
  )
}

function OutcomeBars({ d }: { d: ExperimentDetail }) {
  return (
    <div className="space-y-2">
      {Object.entries(d.summary.models).map(([m, s]) => (
        <div key={m}>
          <div className="mono mb-0.5 text-[12px]">{m}</div>
          <div className="flex h-6 overflow-hidden rounded">
            {OUTCOMES.map(o => s.outcomes[o] > 0 && (
              <div key={o} title={`${outcomeName[o]}: ${s.outcomes[o]}`} style={{ width: `${(s.outcomes[o] / s.n) * 100}%`, background: outcomeColor[o] }}
                className="flex items-center justify-center text-[11px] font-semibold text-white">{s.outcomes[o]}</div>
            ))}
          </div>
        </div>
      ))}
      <div className="flex flex-wrap gap-3 pt-1 text-[11.5px] text-muted">{OUTCOMES.map(o => <span key={o}><span className="mr-1 inline-block h-2 w-2 rounded-sm" style={{ background: outcomeColor[o] }} />{outcomeName[o]}</span>)}</div>
    </div>
  )
}

function ExperimentView({ d, onAction }: { d: ExperimentDetail; onAction: (a: 'cancel' | 'resume' | 'delete') => void }) {
  const m = d.meta
  const [filter, setFilter] = useState<string>('all')
  const [open, setOpen] = useState<number | null>(null)
  const models = Object.keys(d.summary.models)
  const rows = d.results.filter(r => filter === 'all' || r.outcome === filter || r.model === filter)
  const base = `/api/experiments/${m.id}`
  return (
    <div className="space-y-4">
      <Card title={`#${m.id} · ${m.name}`} actions={<>
        {m.running && <Button variant="danger" onClick={() => onAction('cancel')}>Остановить</Button>}
        {!m.running && m.status !== 'done' && <Button onClick={() => onAction('resume')}>Продолжить</Button>}
        {!m.running && <Button variant="ghost" onClick={() => { if (confirm('Удалить эксперимент и его результаты?')) onAction('delete') }}>Удалить</Button>}
      </>}>
        <div className="flex flex-wrap items-center gap-2 text-[12px]">
          <Tag tone={statusTone(m.status)}>{statusName[m.status]}</Tag>
          <Tag>{m.dataset_version} · {m.n_queries} запросов</Tag><Tag>{m.dbms} {m.dbms_version}</Tag>
          {m.models.some(mm => !mm.startsWith('baseline:')) && <Tag>prompt {m.prompt_version}</Tag>}<Tag>прогрев {m.warmup}, прогонов {m.runs}</Tag><Tag>seed {m.database_seed}</Tag><Tag>app v{m.app_version}</Tag>
        </div>
        <Progress done={m.progress_done} total={m.progress_total} />
        {m.running && m.current_item && <p className="mt-1 text-[12px] text-muted"><Spinner /> {m.current_item}</p>}
        {m.error && <div className="mt-2"><ErrorBox>{m.error.split('\n')[0]}</ErrorBox></div>}
        <div className="mt-3 flex flex-wrap gap-2">
          <a href={`${base}/report`} target="_blank" rel="noreferrer"><Button variant="primary">Научный отчёт (HTML / PDF)</Button></a>
          <a href={`${base}/report.md`}><Button>⤓ Markdown</Button></a>
          {['csv', 'xlsx', 'json'].map(f => <a key={f} href={`${base}/export?format=${f}`}><Button variant="ghost">⤓ {f.toUpperCase()}</Button></a>)}
        </div>
      </Card>

      {!d.results.length ? <Empty>Результатов пока нет{m.running ? ' — первые появятся после обработки первого запроса' : ''}</Empty> : (<>
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Исходы по моделям"><OutcomeBars d={d} /></Card>
          <Card title="Автоматические выводы"><ul className="space-y-1.5 text-[13px] leading-relaxed">{d.conclusions.map((c, i) => <li key={i}>• {c}</li>)}</ul></Card>
        </div>

        <Card title="Сравнение моделей">
          <div className="overflow-x-auto">
            <table className="w-full text-[12.5px]">
              <thead className="text-left text-muted"><tr>
                <th className="py-1 pr-3 font-normal">Метрика</th>{models.map(mm => <th key={mm} className="mono pr-3 font-normal">{mm}</th>)}
              </tr></thead>
              <tbody>{([
                ['Запросов', s => String(s.n)],
                ['Предложено изменений', s => `${s.proposed} (${pct(s.proposed_pct)})`],
                ['Корректный SQL*', s => pct(s.correct_sql_pct)],
                ['Эквивалентный результат*', s => pct(s.equivalent_pct)],
                ['Ускорено*', s => pct(s.faster_pct)],
                ['Медиана ускорения', s => x(s.median_speedup) + (s.median_speedup_ci95 ? ` [${x(s.median_speedup_ci95[0])}; ${x(s.median_speedup_ci95[1])}]` : '')],
                ['Геометрическое среднее', s => x(s.geomean_speedup)],
                ['Медиана среди улучшенных', s => x(s.median_speedup_improved)],
                ['Максимальное ускорение', s => x(s.max_speedup)],
                ['Ухудшений', s => String(s.regressions)],
                ['Галлюцинаций схемы', s => String(s.hallucinations)],
                ['Среднее время ответа', s => s.avg_latency_ms == null ? '—' : fmtMs(s.avg_latency_ms)],
                ['Токены (вход → выход)', s => s.prompt_tokens ? `${s.prompt_tokens.toLocaleString('ru-RU')} → ${s.completion_tokens.toLocaleString('ru-RU')}` : '—'],
                ['Типы ошибок', s => Object.entries(s.error_types).map(([k, v]) => `${k}: ${v}`).join(', ') || '—'],
              ] as [string, (s: ExperimentDetail['summary']['models'][string]) => string][]).map(([label, f]) => (
                <tr key={label} className="border-t border-line"><td className="py-1.5 pr-3 text-muted">{label}</td>{models.map(mm => <td key={mm} className="pr-3 tabular-nums">{f(d.summary.models[mm])}</td>)}</tr>
              ))}</tbody>
            </table>
          </div>
          <p className="mt-2 text-[11.5px] text-muted">* доля среди запросов, где модель предложила изменённый SQL. Ускорение считается по кандидатам с эквивалентным результатом; в скобках — 95% bootstrap-интервал медианы.</p>
        </Card>

        <Card title="Результаты по запросам" actions={
          <select value={filter} onChange={e => setFilter(e.target.value)}>
            <option value="all">все</option>{OUTCOMES.map(o => <option key={o} value={o}>{outcomeName[o]}</option>)}{models.map(mm => <option key={mm} value={mm}>{mm}</option>)}
          </select>}>
          <div className="max-h-[560px] overflow-auto">
            <table className="w-full text-[12.5px]">
              <thead className="sticky top-0 bg-panel text-left text-muted"><tr>
                <th className="py-1 font-normal">Запрос</th><th className="font-normal">Модель</th><th className="font-normal">Исход</th><th className="font-normal">До → после</th><th className="font-normal">Ускорение</th><th className="font-normal">Ошибки</th>
              </tr></thead>
              <tbody>{rows.map(r => (<Fragment key={r.id}>
                <tr onClick={() => setOpen(open === r.id ? null : r.id)} className="cursor-pointer border-t border-line hover:bg-panel-2">
                  <td className="py-1.5 pr-2"><div className="mono text-[11.5px]">{r.key}</div><div className="text-[11px] text-muted">{r.title}</div></td>
                  <td className="mono pr-2 text-[11.5px]">{r.model}</td>
                  <td className="pr-2"><span className="rounded px-1.5 py-0.5 text-[11px] font-semibold text-white" style={{ background: outcomeColor[r.outcome] }}>{outcomeName[r.outcome]}</span></td>
                  <td className="pr-2 tabular-nums">{r.time_before_ms != null ? `${fmtMs(r.time_before_ms)} → ${fmtMs(r.time_after_ms)}` : '—'}</td>
                  <td className="pr-2 tabular-nums">{x(r.speedup)}</td>
                  <td className="text-[11px] text-bad">{r.error_types.join(', ')}</td>
                </tr>
                {open === r.id && <tr><td colSpan={6} className="pb-3"><ResultDetail runId={r.run_id} message={r.message} /></td></tr>}
              </Fragment>))}</tbody>
            </table>
          </div>
        </Card>
      </>)}
    </div>
  )
}

function ResultDetail({ runId, message }: { runId?: number | null; message?: string | null }) {
  const [sqls, setSqls] = useState<{ original: string; optimized?: string | null; summary?: string } | null>(null)
  useEffect(() => {
    if (runId == null) return
    fetch(`/api/runs/${runId}`).then(r => r.json()).then(d => {
      const res = d.result ?? {}
      setSqls({ original: d.sql, optimized: res.optimized_query, summary: res.ai?.summary })
    }).catch(() => {})
  }, [runId])
  return (
    <div className="space-y-2 rounded-md bg-bg p-3">
      {message && <p className="text-[12.5px]">{message}</p>}
      {sqls?.summary && <p className="text-[12.5px] text-muted">Модель: {sqls.summary}</p>}
      {sqls && <div className="grid gap-2 lg:grid-cols-2"><Code>{sqls.original}</Code><Code>{sqls.optimized ?? '— запрос не предложен —'}</Code></div>}
      {runId != null && <p className="text-[11px] text-muted">Запуск #{runId} — полные данные в «Истории».</p>}
    </div>
  )
}
