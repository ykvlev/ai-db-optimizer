import { useEffect, useMemo, useState } from 'react'
import type { AuditApplyResult, AuditCategory, AuditExplanation, AuditFinding, AuditReport, ModelsInfo, TopQueries } from '../api'
import { api } from '../api'
import { download } from './ResultView'
import { Button, Empty, ErrorBox, Spinner, Tag, fmtMs } from './ui'

const SEV = { high: { label: 'важно', tone: 'bad' }, medium: { label: 'стоит исправить', tone: 'warn' }, low: { label: 'мелочь', tone: 'muted' } } as const
const KIND = {
  safe: { label: 'проверено на данных', tone: 'good' },
  check: { label: 'проверьте перед применением', tone: 'warn' },
  manual: { label: 'нужно решение разработчика', tone: 'muted' },
} as const
const CAT_ORDER: AuditCategory[] = ['integrity', 'indexes', 'types', 'stats']

// модель по умолчанию для разборов и описаний: GigaChat, если настроен (быстрее локальной)
export function preferredModel(models: ModelsInfo | null): string | null {
  const llm = (models?.models ?? []).filter(m => !m.startsWith('baseline'))
  return llm.find(m => m === 'gigachat:GigaChat-2-Pro') ?? llm.find(m => m.startsWith('gigachat:')) ?? models?.default ?? llm[0] ?? null
}

function ModelSelect({ models, value, onChange }: { models: ModelsInfo | null; value: string; onChange: (v: string) => void }) {
  const llm = (models?.models ?? []).filter(m => !m.startsWith('baseline'))
  if (!llm.length) return null
  return (
    <select value={value} onChange={e => onChange(e.target.value)} className="max-w-[220px]">
      {llm.map(m => <option key={m} value={m}>{m.split(':').slice(1).join(':')}{m.startsWith('ollama:') ? ' (локально, медленно)' : ''}</option>)}
    </select>
  )
}

function Bar({ value }: { value: number }) {
  return <div className="h-1.5 rounded-full bg-paper-white"><div className={`h-1.5 rounded-full ${value >= 85 ? 'bg-terminal-green' : value >= 60 ? 'bg-obsidian' : 'bg-warn'}`} style={{ width: `${value}%` }} /></div>
}

function FindingCard({ f, checked, onToggle, result }: { f: AuditFinding; checked: boolean; onToggle: () => void; result?: { ok: boolean; error: string | null } }) {
  const [showSql, setShowSql] = useState(false)
  return (
    <div className="rounded-md p-3 shadow-[0_0_0_1px_#ebebeb]">
      <div className="flex flex-wrap items-start gap-2">
        {f.fix_sql
          ? <input type="checkbox" className="mt-1 h-4 w-4" checked={checked} onChange={onToggle} title="Исправить" />
          : <span className="mt-1 inline-block h-4 w-4" />}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[14px] font-medium text-obsidian">{f.title}</span>
            <span className="font-mono text-[12px] text-stone">{f.table}</span>
            <Tag tone={SEV[f.severity].tone}>{SEV[f.severity].label}</Tag>
            {result && (result.ok ? <Tag tone="good">исправлено</Tag> : <Tag tone="bad">не применено</Tag>)}
          </div>
          <p className="mt-1.5 text-[13px] text-charcoal"><span className="text-stone">Почему это плохо: </span>{f.why}</p>
          <p className="mt-1 text-[13px] text-charcoal"><span className="text-stone">{f.fix_sql ? 'После исправления: ' : 'Что сделать: '}</span>{f.effect}</p>
          {f.note && <p className="mt-1 text-[12.5px] text-stone">{f.note}</p>}
          {result && !result.ok && result.error && <p className="mt-1 font-mono text-[12px] text-bad">{result.error}</p>}
          {f.fix_sql && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Tag tone={KIND[f.fix_kind].tone}>{KIND[f.fix_kind].label}</Tag>
              <button className="text-[12px] text-stone underline" onClick={() => setShowSql(v => !v)}>{showSql ? 'скрыть SQL' : 'показать SQL'}</button>
            </div>
          )}
          {showSql && f.fix_sql && <pre className="mt-2 overflow-auto rounded-md bg-paper-white p-2 font-mono text-[12px]">{f.fix_sql}</pre>}
        </div>
      </div>
    </div>
  )
}

export function AuditView({ connectionId, scope, models, username, onFixed }: {
  connectionId: number; scope: string | null; models: ModelsInfo | null; username: string; onFixed: () => void
}) {
  const [report, setReport] = useState<AuditReport | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [explain, setExplain] = useState<AuditExplanation | null>(null)
  const [explainBusy, setExplainBusy] = useState(false)
  const [model, setModel] = useState('')
  const [applyOpen, setApplyOpen] = useState(false)
  const [creds, setCreds] = useState({ username, password: '' })
  const [agree, setAgree] = useState(false)
  const [applyBusy, setApplyBusy] = useState(false)
  const [applied, setApplied] = useState<(AuditApplyResult & { after?: number }) | null>(null)
  useEffect(() => { if (!model) setModel(preferredModel(models) ?? '') }, [models, model])

  const run = async (keepApplied = false) => {
    setBusy(true); setError(null); setExplain(null)
    if (!keepApplied) setApplied(null)
    try {
      const r = await api.audit(connectionId, scope)
      setReport(r)
      setPicked(new Set(r.findings.filter(f => f.fix_sql && f.fix_kind === 'safe').map(f => f.id)))  // проверенные — отмечены сразу
      return r
    } catch (e) { setError((e as Error).message); return null } finally { setBusy(false) }
  }

  const toggle = (id: string) => setPicked(p => { const n = new Set(p); if (n.has(id)) n.delete(id); else n.add(id); return n })
  const chosen = report?.findings.filter(f => picked.has(f.id) && f.fix_sql) ?? []
  const byCat = useMemo(() => {
    const m = new Map<AuditCategory, AuditFinding[]>()
    for (const f of report?.findings ?? []) m.set(f.category, [...(m.get(f.category) ?? []), f])
    return m
  }, [report])
  const resultById = new Map((applied?.results ?? []).map(r => [r.id, r]))

  const doExplain = async () => {
    setExplainBusy(true); setError(null)
    try { setExplain(await api.auditExplain(connectionId, { schema_name: scope, model: model || null })) }
    catch (e) { setError((e as Error).message) } finally { setExplainBusy(false) }
  }

  const doApply = async () => {
    setApplyBusy(true); setError(null)
    try {
      const res = await api.auditApply(connectionId, { ids: chosen.map(f => f.id), schema_name: scope, username: creds.username, password: creds.password })
      setApplyOpen(false); setCreds(c => ({ ...c, password: '' })); setAgree(false)
      onFixed()
      const after = await run(true)
      setApplied({ ...res, after: after?.score })
    } catch (e) { setError((e as Error).message) } finally { setApplyBusy(false) }
  }

  const script = chosen.map(f => `-- ${f.table}: ${f.title}\n${f.fix_sql}`).join('\n\n')

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="primary" onClick={() => run()} disabled={busy}>{busy && <Spinner />} {report ? 'Проверить заново' : `Провести аудит ${scope ? `схемы ${scope}` : 'всей базы'}`}</Button>
        <span className="text-[13px] text-stone">Ключи, связи, индексы, типы данных и статистика. Сама проверка ничего не меняет в базе.</span>
      </div>
      {error && <ErrorBox>{error}</ErrorBox>}

      {applied && (
        <div className={`card p-4 text-[14px] ${applied.failed ? '' : 'shadow-[0_0_0_1px_#297a3a]'}`}>
          {applied.failed
            ? <>Исправления не применены{applied.rolled_back ? ' — транзакция откатана, база не изменилась' : ''}. Ошибка отмечена у замечания ниже.</>
            : <>Применено исправлений: {applied.applied}. Оценка: <b>{applied.before}</b> → <b>{applied.after ?? '…'}</b></>}
        </div>
      )}

      {report && (
        <>
          <div className="grid gap-3 lg:grid-cols-[260px_1fr]">
            <div className="card p-4">
              <div className="kicker text-stone">оценка {scope ? `схемы ${scope}` : 'базы'}</div>
              <div className="mt-1 text-[40px] font-[450] leading-none tracking-[-0.04em]">{report.score}<span className="text-[16px] text-stone"> / 100</span></div>
              <div className="mt-1 text-[14px] text-obsidian">{report.verdict}</div>
              <div className="mt-2 text-[12.5px] text-stone">{report.tables} табл. · замечаний {report.findings.length} · исправимо {report.fixable}</div>
            </div>
            <div className="card space-y-3 p-4">
              {CAT_ORDER.map(k => {
                const c = report.categories[k]
                return (
                  <div key={k}>
                    <div className="flex items-baseline gap-2 text-[13.5px]">
                      <span className="text-obsidian">{c.title}</span>
                      <span className="font-mono text-[11.5px] text-ash">вес {Math.round(c.weight * 100)} %</span>
                      <span className="ml-auto font-mono text-[13px] text-obsidian">{c.score}</span>
                    </div>
                    <div className="mt-1"><Bar value={c.score} /></div>
                    <div className="mt-1 text-[12px] text-stone">{c.issues ? `${c.issues} замечаний в ${c.tables_affected} табл. · ` : 'замечаний нет · '}{c.about}</div>
                  </div>
                )
              })}
              <details className="text-[12.5px] text-stone"><summary className="cursor-pointer">Как считается оценка</summary><p className="mt-1">{report.how}</p></details>
            </div>
          </div>

          <div className="card space-y-3 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="kicker text-stone">Разбор от ИИ</span>
              <span className="ml-auto" />
              <ModelSelect models={models} value={model} onChange={setModel} />
              <Button onClick={doExplain} disabled={explainBusy || !model}>{explainBusy && <Spinner />} {explain ? 'Разобрать заново' : 'Объяснить простыми словами'}</Button>
            </div>
            {explain ? (
              <div className="space-y-3 text-[13.5px]">
                <p className="leading-[1.55] text-obsidian">{explain.summary}</p>
                {!!explain.good?.length && <div><div className="text-stone">Что сделано хорошо:</div><ul className="mt-1 list-disc pl-5">{explain.good.map((g, i) => <li key={i}>{g}</li>)}</ul></div>}
                {!!explain.priorities?.length && <div><div className="text-stone">С чего начать:</div>
                  <ol className="mt-1 list-decimal space-y-1.5 pl-5">{explain.priorities.map((p, i) => <li key={i}><b className="font-medium">{p.title}.</b> {p.why}{p.tables?.length ? <span className="font-mono text-[12px] text-stone"> ({p.tables.join(', ')})</span> : null}</li>)}</ol></div>}
                <div className="font-mono text-[11px] text-ash">{explain.model.split(':').slice(1).join(':')}</div>
              </div>
            ) : <p className="text-[12.5px] text-stone">Модель получит только результаты аудита (не данные) и объяснит, что важно именно для этой базы и в каком порядке исправлять.</p>}
          </div>

          {!report.findings.length ? <Empty>Замечаний нет: у всех таблиц есть ключи, связи объявлены, лишних индексов нет, типы данных подходящие.</Empty> : (
            CAT_ORDER.filter(k => byCat.get(k)?.length).map(k => (
              <div key={k} className="space-y-2">
                <div className="flex items-baseline gap-2 pt-2">
                  <h3 className="text-[16px] font-[450] tracking-[-0.02em] text-obsidian">{report.categories[k].title}</h3>
                  <span className="text-[12.5px] text-stone">{report.categories[k].about}</span>
                </div>
                {byCat.get(k)!.map(f => <FindingCard key={f.id} f={f} checked={picked.has(f.id)} onToggle={() => toggle(f.id)} result={resultById.get(f.id)} />)}
              </div>
            ))
          )}

          {report.fixable > 0 && (
            <div className="sticky bottom-0 z-10 flex flex-wrap items-center gap-2 rounded-md bg-white/95 p-3 shadow-[0_0_0_1px_#ebebeb,0_-4px_16px_rgba(0,0,0,0.04)] backdrop-blur">
              <span className="text-[13.5px] text-obsidian">Выбрано исправлений: {chosen.length} из {report.fixable}</span>
              <button className="text-[12.5px] text-stone underline" onClick={() => setPicked(new Set(report.findings.filter(f => f.fix_sql).map(f => f.id)))}>все</button>
              <button className="text-[12.5px] text-stone underline" onClick={() => setPicked(new Set(report.findings.filter(f => f.fix_sql && f.fix_kind === 'safe').map(f => f.id)))}>только проверенные</button>
              <button className="text-[12.5px] text-stone underline" onClick={() => setPicked(new Set())}>снять</button>
              <span className="ml-auto" />
              <Button onClick={() => download(`fixes_${scope ?? 'database'}.sql`, `-- Исправления по аудиту (${scope ? `схема ${scope}` : 'вся база'})\n\n${script}\n`, 'text/plain;charset=utf-8')} disabled={!chosen.length}>Скачать скрипт</Button>
              <Button variant="primary" onClick={() => setApplyOpen(true)} disabled={!chosen.length}>Исправить выбранное</Button>
            </div>
          )}
        </>
      )}

      {applyOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={() => !applyBusy && setApplyOpen(false)}>
          <div className="card w-full max-w-lg space-y-3 bg-white p-5" onClick={e => e.stopPropagation()}>
            <div className="text-[18px] font-[450] tracking-[-0.03em]">Исправить {chosen.length} {chosen.length === 1 ? 'замечание' : 'замечаний'}</div>
            <p className="text-[13px] text-charcoal">
              Программа работает с базой только на чтение, поэтому для изменений нужен пользователь с правами на изменение структуры
              (владелец таблиц). Пароль используется один раз и нигде не сохраняется.
            </p>
            <div className="grid grid-cols-[90px_1fr] items-center gap-2 text-[13px]">
              <label className="text-stone">Пользователь</label><input value={creds.username} onChange={e => setCreds(c => ({ ...c, username: e.target.value }))} />
              <label className="text-stone">Пароль</label><input type="password" value={creds.password} onChange={e => setCreds(c => ({ ...c, password: e.target.value }))} autoFocus />
            </div>
            <p className="text-[12.5px] text-stone">В PostgreSQL все изменения выполняются одной транзакцией: при любой ошибке база останется как была. В MySQL изменения структуры фиксируются сразу — выполнение остановится на первой ошибке.</p>
            <label className="flex items-start gap-2 text-[13px]"><input type="checkbox" className="mt-0.5" checked={agree} onChange={e => setAgree(e.target.checked)} /> Я понимаю, что структура базы будет изменена, и скачал(а) скрипт или сделал(а) резервную копию, если база важная</label>
            <div className="flex justify-end gap-2 pt-1">
              <Button onClick={() => setApplyOpen(false)} disabled={applyBusy}>Отмена</Button>
              <Button variant="primary" onClick={doApply} disabled={applyBusy || !agree || !creds.username}>{applyBusy && <Spinner />} Применить</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export function TopQueriesView({ connectionId, onOptimize }: { connectionId: number; onOptimize: (sql: string) => void }) {
  const [data, setData] = useState<TopQueries | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const load = async () => {
    setBusy(true); setError(null)
    try { setData(await api.topQueries(connectionId)) } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  const total = data?.queries.reduce((s, q) => s + q.total_ms, 0) || 1

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="primary" onClick={load} disabled={busy}>{busy && <Spinner />} {data ? 'Обновить' : 'Показать'}</Button>
        <span className="text-[13px] text-stone">Запросы, которые реально выполнялись в базе, по суммарному времени. Оптимизировать стоит сверху вниз.</span>
      </div>
      {error && <ErrorBox>{error}</ErrorBox>}
      {data && !data.available && (
        <div className="card space-y-2 p-4 text-[13.5px]">
          <div className="text-obsidian">Статистика запросов недоступна: {data.reason}</div>
          <div className="text-stone">Как включить:</div>
          {data.hint.map((h, i) => <div key={i} className="font-mono text-[12.5px]">{i + 1}. {h}</div>)}
        </div>
      )}
      {data?.available && !data.queries.length && <Empty>Запросов пока нет — статистика накапливается, пока с базой работают приложения.</Empty>}
      {data?.available && data.queries.map((q, i) => (
        <div key={i} className="card space-y-2 p-3">
          <div className="flex flex-wrap items-center gap-3 font-mono text-[12px] text-stone">
            <span className="text-obsidian">{fmtMs(q.total_ms)}</span><span>всего · {(100 * q.total_ms / total).toFixed(0)} %</span>
            <span>{q.calls.toLocaleString('ru-RU')} вызовов</span><span>в среднем {fmtMs(q.mean_ms)}</span>
            {q.rows_examined != null && <span>прочитано строк {q.rows_examined.toLocaleString('ru-RU')}</span>}
            <span className="ml-auto" />
            <Button onClick={() => onOptimize(q.query)} title={q.runnable ? '' : 'В тексте есть параметры ($1, ?) — подставьте значения перед анализом'}>Оптимизировать</Button>
          </div>
          <div className="h-1 rounded-full bg-paper-white"><div className="h-1 rounded-full bg-obsidian" style={{ width: `${100 * q.total_ms / total}%` }} /></div>
          <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-all font-mono text-[12px] text-obsidian">{q.query}</pre>
          {!q.runnable && <div className="text-[12px] text-stone">Текст нормализован СУБД: вместо значений стоят параметры — подставьте их перед анализом.</div>}
        </div>
      ))}
    </div>
  )
}

export function DocsView({ connectionId, scope, models, getErPng }: { connectionId: number; scope: string | null; models: ModelsInfo | null; getErPng: () => Promise<string | null> }) {
  const [describe, setDescribe] = useState(false)
  const [withEr, setWithEr] = useState(true)
  const [withAudit, setWithAudit] = useState(true)
  const [model, setModel] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { if (!model) setModel(preferredModel(models) ?? '') }, [models, model])
  const build = async () => {
    setBusy(true); setError(null)
    try {
      const er = withEr ? await getErPng() : null
      const blob = await api.docs(connectionId, { describe, model: model || null, er_png: er, schema_name: scope, include_audit: withAudit })
      download(`Описание_${scope ?? 'базы_данных'}.docx`, blob, blob.type)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <div className="max-w-2xl space-y-4 text-[13.5px]">
      <p className="text-charcoal">
        Отчёт в Word {scope ? <>по схеме <span className="font-mono">{scope}</span></> : 'по всей базе'} (область выбирается вверху страницы). Оформление по ГОСТ 2.105 и 7.32:
        Times New Roman 14, поля 30/10/20/20 мм, номера страниц, «Таблица N – …» над таблицами, «Рисунок N – …» под рисунком.
      </p>
      <div className="card p-3 text-[13px] text-charcoal">
        <div className="kicker mb-1.5 text-stone">Разделы отчёта</div>
        1 Общие сведения (СУБД, число таблиц и строк, объём) · 2 Перечень таблиц · 3 Структура таблиц · 4 Связи: схема данных и таблица внешних ключей · 5 Индексы{withAudit ? ' · 6 Оценка структуры: оценки по направлениям, замечания и рекомендации' : ''}
      </div>
      <label className="flex items-center gap-2"><input type="checkbox" checked={withEr} onChange={e => setWithEr(e.target.checked)} /> Схема данных (ER-диаграмма в нотации IDEF1X) — такая же, как на вкладке «ER-диаграмма»</label>
      <label className="flex items-center gap-2"><input type="checkbox" checked={withAudit} onChange={e => setWithAudit(e.target.checked)} /> Результаты аудита структуры</label>
      <div className="flex flex-wrap items-center gap-2">
        <label className={`flex items-center gap-2 ${model ? '' : 'opacity-50'}`}>
          <input type="checkbox" checked={describe} disabled={!model} onChange={e => setDescribe(e.target.checked)} />
          Описать назначение таблиц и полей с помощью ИИ
        </label>
        {describe && <ModelSelect models={models} value={model} onChange={setModel} />}
      </div>
      {describe && <p className="text-[12.5px] text-stone">Модель видит только имена таблиц, столбцов и связи — не данные. Описания стоит проверить. GigaChat отвечает за несколько секунд, локальная модель — заметно дольше.</p>}
      <Button variant="primary" onClick={build} disabled={busy}>{busy && <Spinner />} Скачать .docx</Button>
      {busy && describe && <span className="ml-3 text-[12.5px] text-stone">ИИ описывает таблицы…</span>}
      {error && <ErrorBox>{error}</ErrorBox>}
    </div>
  )
}
