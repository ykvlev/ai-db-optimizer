import { useEffect, useState } from 'react'
import type { AnalyzeResponse, Comparison, Connection, Dialect, Examples, ModelsInfo, OptimizeResponse, SchemaInfo } from '../api'
import { api } from '../api'
import { ComparisonView } from '../components/ComparisonView'
import { IssueList } from '../components/IssueList'
import { PlanView } from '../components/PlanTree'
import { SqlDiff, SqlEditor } from '../components/SqlEditor'
import { Button, Card, Code, Empty, ErrorBox, SeverityBadge, Spinner, Tabs, Tag, fmtNum } from '../components/ui'

type Tab = 'problems' | 'parse' | 'plan' | 'schema' | 'ai' | 'benchmark'

const verdictUi: Record<OptimizeResponse['verdict'], { label: string; tone: 'good' | 'bad' | 'warn' | 'muted' }> = {
  accepted: { label: 'ОПТИМИЗАЦИЯ ПРИНЯТА', tone: 'good' },
  rejected: { label: 'ОПТИМИЗАЦИЯ ОТКЛОНЕНА', tone: 'bad' },
  unverified: { label: 'НЕ ПРОВЕРЕНО НА БД', tone: 'warn' },
  no_change: { label: 'БЕЗ ИЗМЕНЕНИЙ', tone: 'muted' },
  failed: { label: 'ОШИБКА', tone: 'bad' },
}

const factorNames: Record<string, string> = {
  equivalence: 'Эквивалентность', real_speedup: 'Реальное ускорение', rule_ai_agreement: 'Согласие правил и ИИ',
  plan_confirmed: 'Подтверждение планом', benchmark_stability: 'Стабильность бенчмарка',
}

export function Analyzer({ connections, models, examples, onRun }: {
  connections: Connection[]; models: ModelsInfo | null; examples: Examples | null; onRun: () => void
}) {
  const [dbms, setDbms] = useState<Dialect>('mysql')
  const [connId, setConnId] = useState<number | null>(null)
  const [connTouched, setConnTouched] = useState(false)
  // по умолчанию — первое подключение: без него нет плана, эквивалентности и бенчмарка
  useEffect(() => { if (!connTouched && connId == null && connections.length) setConnId(connections[0].id) }, [connections, connId, connTouched])
  const [model, setModel] = useState<string>('')
  const [sql, setSql] = useState('')
  const [ddl, setDdl] = useState('')
  const [showDdl, setShowDdl] = useState(false)
  const [tab, setTab] = useState<Tab>('problems')
  const [busy, setBusy] = useState<'analyze' | 'optimize' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null)
  const [opt, setOpt] = useState<OptimizeResponse | null>(null)
  const [plain, setPlain] = useState(false)
  const [ruleCmp, setRuleCmp] = useState<Comparison | null>(null)
  const [cmpBusy, setCmpBusy] = useState(false)

  const conn = connections.find(c => c.id === connId) ?? null
  useEffect(() => { if (conn) setDbms(conn.dbms) }, [conn])
  useEffect(() => { if (models?.default && !model) setModel(models.default) }, [models, model])
  useEffect(() => {
    if (examples && !sql) {
      setSql(examples.queries[0].mysql)
      setDdl(examples.ddl.mysql)
    }
  }, [examples, sql])

  const loadExample = (id: string) => {
    const ex = examples?.queries.find(q => q.id === id)
    if (!ex) return
    setSql(ex[dbms])
    if (!conn && examples) setDdl(examples.ddl[dbms])
  }

  const run = async (kind: 'analyze' | 'optimize') => {
    setBusy(kind); setError(null)
    const body = { sql, dbms, ddl: conn ? undefined : ddl, connection_id: connId }
    try {
      if (kind === 'analyze') {
        const r = await api.analyze(body)
        setAnalysis(r); setOpt(null); setRuleCmp(null); setTab('problems')
      } else {
        const r = await api.optimize({ ...body, model: model || null })
        setAnalysis(r.analysis); setOpt(r); setRuleCmp(null); setTab('ai')
      }
      onRun()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const verifyRewrite = async () => {
    if (!analysis?.rule_rewrite || connId == null) return
    setCmpBusy(true); setError(null)
    try {
      setRuleCmp(await api.compare({ original_sql: sql, optimized_sql: analysis.rule_rewrite, connection_id: connId }))
      setTab('benchmark')
      onRun()
    } catch (e) { setError((e as Error).message) } finally { setCmpBusy(false) }
  }

  const a = analysis
  const shownCmp = opt?.comparison ?? ruleCmp
  const issueCount = a?.issues.filter(i => i.code !== 'RULE_ERROR').length ?? 0
  const tabs: { id: Tab; label: React.ReactNode }[] = [
    { id: 'problems', label: <>Проблемы {a && <Tag tone={issueCount ? 'warn' : 'good'}>{issueCount}</Tag>}</> },
    { id: 'parse', label: 'Разбор запроса' },
    { id: 'plan', label: 'План выполнения' },
    { id: 'schema', label: 'Схема и индексы' },
    { id: 'ai', label: 'AI-оптимизация' },
    { id: 'benchmark', label: 'Бенчмарк' },
  ]

  return (
    <div className="grid h-full gap-4 xl:grid-cols-[minmax(420px,5fr)_7fr]">
      {/* ------------------------------------------------ левая колонка */}
      <div className="flex min-w-0 flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <select value={connId ?? ''} onChange={e => { setConnTouched(true); setConnId(e.target.value ? Number(e.target.value) : null) }} className={`min-w-0 flex-1 ${conn ? '' : 'border-warn text-warn'}`}>
            <option value="">Без подключения (офлайн-анализ)</option>
            {connections.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select value={dbms} disabled={!!conn} onChange={e => setDbms(e.target.value as Dialect)}>
            <option value="mysql">MySQL 8</option>
            <option value="postgres">PostgreSQL</option>
          </select>
          {examples && (
            <select value="" onChange={e => loadExample(e.target.value)}>
              <option value="">Примеры…</option>
              {examples.queries.map(q => <option key={q.id} value={q.id}>{q.title}</option>)}
            </select>
          )}
        </div>

        <SqlEditor value={sql} onChange={setSql} height={300} />

        {!conn && (
          <div>
            <button className="text-[12px] text-muted hover:text-text" onClick={() => setShowDdl(!showDdl)}>
              {showDdl ? '▾' : '▸'} DDL-схема таблиц {ddl.trim() ? '(задана)' : '(не задана)'}
            </button>
            {showDdl && <div className="mt-2"><SqlEditor value={ddl} onChange={setDdl} height={220} /></div>}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Button variant="default" onClick={() => run('analyze')} disabled={!!busy || !sql.trim()}>
            {busy === 'analyze' && <Spinner />} Анализировать
          </Button>
          <Button variant="primary" onClick={() => run('optimize')} disabled={!!busy || !sql.trim() || !models?.models.length}
            title={models?.models.length ? undefined : 'Не настроен LLM-провайдер (backend/.env)'}>
            {busy === 'optimize' && <Spinner />} Оптимизировать с помощью ИИ
          </Button>
          <select value={model} onChange={e => setModel(e.target.value)} disabled={!models?.models.length} className="min-w-0">
            {!models?.models.length && <option value="">LLM не настроен</option>}
            {models?.models.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
        {busy === 'optimize' && (
          <p className="text-[12px] text-muted">
            {conn ? 'Анализ → запрос к модели → проверки → эквивалентность → бенчмарк. С локальной моделью на CPU это занимает 2–5 минут.' : 'Анализ → запрос к модели → статические проверки. С локальной моделью на CPU это занимает 2–5 минут.'}
          </p>
        )}
        {!conn && (
          <p className="rounded-md border border-warn/40 bg-warn/10 px-3 py-2 text-[12px] text-warn">
            Офлайн-режим: запрос не выполняется на БД, поэтому нет плана выполнения, проверки эквивалентности и бенчмарка.
            {connections.length > 0 && ' Выберите подключение в списке выше.'}
          </p>
        )}
        {error && <ErrorBox>{error}</ErrorBox>}
      </div>

      {/* ------------------------------------------------ правая колонка */}
      <div className="min-w-0 rounded-lg border border-line bg-panel">
        <div className="px-3 pt-1"><Tabs tabs={tabs} active={tab} onChange={setTab} /></div>
        <div className="p-4">
          {!a && tab !== 'ai' && <Empty>Вставьте SQL и нажмите «Анализировать»</Empty>}

          {a && tab === 'problems' && (
            <div className="space-y-3">
              {!a.safety.allowed && <ErrorBox>Запрос не будет выполняться: {a.safety.reasons.join('; ')}</ErrorBox>}
              {a.safety.warnings.map((w, i) => <div key={i} className="text-[12px] text-warn">⚠ {w}</div>)}
              {a.parse_error && <ErrorBox>Ошибка разбора: {a.parse_error}</ErrorBox>}
              <IssueList issues={a.issues.filter(i => i.code !== 'RULE_ERROR')} />
              {a.rule_rewrite && (
                <Card title="Детерминированное переписывание (rule-based, без ИИ)" actions={conn &&
                  <Button onClick={verifyRewrite} disabled={cmpBusy}>{cmpBusy && <Spinner />} Проверить на БД</Button>}>
                  <ul className="mb-2 text-[13px] text-muted">{a.rule_rewrite_notes.map((n, i) => <li key={i}>• {n}</li>)}</ul>
                  <SqlDiff original={sql} modified={a.rule_rewrite} height={200} />
                </Card>
              )}
            </div>
          )}

          {a && tab === 'parse' && (a.parsed ? <ParsedView a={a} /> : <Empty>Запрос не разобран</Empty>)}

          {a && tab === 'plan' && (a.plan ? <PlanView plan={a.plan} /> :
            <Empty>{conn ? 'План недоступен (см. предупреждения во вкладке «Проблемы»)' : 'План выполнения доступен только при подключении к БД'}</Empty>)}

          {a && tab === 'schema' && <SchemaView schema={a.schema_info} tables={a.parsed?.tables ?? []} />}

          {tab === 'ai' && (opt ? (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <Tag tone={verdictUi[opt.verdict].tone}>{verdictUi[opt.verdict].label}</Tag>
                <span className="text-[13px]">{opt.verdict_reason}</span>
              </div>
              {opt.ai_error && <ErrorBox>{opt.ai_error}</ErrorBox>}
              {opt.error_types.length > 0 && (
                <div className="flex flex-wrap gap-1">{opt.error_types.map(e => <Tag key={e} tone="bad">{e}</Tag>)}</div>
              )}
              {opt.ai && (
                <>
                  <Card title="Анализ модели" actions={
                    opt.ai.plain_explanation && <Button variant="ghost" onClick={() => setPlain(!plain)}>{plain ? 'Технически' : 'Объяснить простыми словами'}</Button>
                  }>
                    <p className="text-[13.5px] leading-relaxed">{plain && opt.ai.plain_explanation ? opt.ai.plain_explanation : opt.ai.summary}</p>
                    {!plain && opt.ai.issues.length > 0 && (
                      <ul className="mt-3 space-y-1.5">{opt.ai.issues.map((i, k) => (
                        <li key={k} className="flex gap-2 text-[13px]"><SeverityBadge severity={(i.severity as never)} /><span><span className="mono text-[11px] text-muted">{i.type}</span> {i.description}</span></li>
                      ))}</ul>
                    )}
                  </Card>
                  {opt.optimized_query && (
                    <Card title="Исходный → оптимизированный SQL">
                      <SqlDiff original={sql} modified={opt.optimized_query} />
                      {opt.ai.explanation.length > 0 && <ul className="mt-3 space-y-1 text-[13px]">{opt.ai.explanation.map((e, i) => <li key={i}>• {e}</li>)}</ul>}
                    </Card>
                  )}
                  {opt.ai.recommended_indexes.length > 0 && (
                    <Card title="Рекомендованные индексы">
                      <p className="mb-2 text-[12px] text-muted">Индексы не создаются автоматически: система работает в режиме только чтения. Бенчмарк выполнен без них.</p>
                      <div className="space-y-2">{opt.ai.recommended_indexes.map((r, i) => (
                        <div key={i}><Code>{r.sql ?? `CREATE INDEX ON ${r.table} (${r.columns.join(', ')});`}</Code>{r.reason && <p className="mt-1 text-[12px] text-muted">{r.reason}</p>}</div>
                      ))}</div>
                    </Card>
                  )}
                </>
              )}
              <div className="grid gap-4 lg:grid-cols-2">
                <Card title="AI Confidence">
                  {opt.confidence?.confidence != null
                    ? <div className="text-3xl font-semibold">{Math.round(opt.confidence.confidence * 100)}%</div>
                    : <p className="text-[13px] text-muted">Не рассчитывается без фактической проверки результата на БД.</p>}
                  {opt.confidence && opt.confidence.factors.length > 0 && (
                    <ul className="mt-2 space-y-1 text-[12.5px]">{opt.confidence.factors.map(f => (
                      <li key={f.name} className="flex justify-between gap-3"><span className="text-muted">{factorNames[f.name] ?? f.name}: {f.detail}</span><span className="tabular-nums">{Math.round(f.value * 100)}%</span></li>
                    ))}</ul>
                  )}
                  {opt.ai?.confidence != null && <p className="mt-2 text-[12px] text-muted">Самооценка модели (не учитывается): {Math.round(opt.ai.confidence * 100)}%</p>}
                </Card>
                {opt.llm && (
                  <Card title="Вызов модели">
                    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[12.5px]">
                      <dt className="text-muted">Модель</dt><dd className="mono">{opt.llm.provider}:{opt.llm.model}</dd>
                      <dt className="text-muted">Промпт</dt><dd className="mono">{opt.llm.prompt_version}</dd>
                      <dt className="text-muted">Время ответа</dt><dd>{(opt.llm.latency_ms / 1000).toFixed(1)} с</dd>
                      <dt className="text-muted">Токены</dt><dd>{opt.llm.prompt_tokens ?? '—'} → {opt.llm.completion_tokens ?? '—'}</dd>
                      <dt className="text-muted">Запуск</dt><dd>#{opt.run_id}</dd>
                    </dl>
                  </Card>
                )}
              </div>
            </div>
          ) : <Empty>Нажмите «Оптимизировать с помощью ИИ». Модель получит структурированный контекст: запрос, схему, план и найденные правилами проблемы.</Empty>)}

          {tab === 'benchmark' && (shownCmp ? <ComparisonView cmp={shownCmp} /> :
            <Empty>{conn ? 'Бенчмарк выполняется после AI-оптимизации, если модель предложила новый запрос. Для ручного сравнения откройте раздел «Сравнение».' : 'Бенчмарк требует подключения к БД — без него реальные показатели не измеряются.'}</Empty>)}
        </div>
      </div>
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return <><dt className="py-1 text-muted">{label}</dt><dd className="mono py-1 text-[12.5px]">{children}</dd></>
}

function ParsedView({ a }: { a: AnalyzeResponse }) {
  const p = a.parsed!
  const list = (xs: string[]) => xs.length ? xs.join(', ') : '—'
  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-[160px_1fr] gap-x-4 text-[13px]">
        <Row label="Тип запроса">{p.query_type}{p.distinct && ' DISTINCT'}{p.union && ' + UNION'}</Row>
        <Row label="Таблицы">{list(p.tables)}</Row>
        <Row label="CTE">{list(p.cte)}</Row>
        <Row label="JOIN">{p.joins.length ? p.joins.map((j, i) => <div key={i}>{j.kind} {j.table}{j.alias && j.alias !== j.table ? ` ${j.alias}` : ''}{j.condition ? ` ON ${j.condition}` : ''}</div>) : '—'}</Row>
        <Row label="WHERE">{p.where_conditions.length ? p.where_conditions.map((w, i) => <div key={i}>{w}</div>) : '—'}</Row>
        <Row label="GROUP BY">{list(p.group_by)}</Row>
        <Row label="HAVING">{p.having ?? '—'}</Row>
        <Row label="ORDER BY">{list(p.order_by)}</Row>
        <Row label="LIMIT / OFFSET">{p.limit ?? '—'} / {p.offset ?? '—'}</Row>
        <Row label="Подзапросы">{p.subqueries} (коррелированных: {p.correlated_subqueries})</Row>
        <Row label="Агрегаты">{list(p.aggregations)}</Row>
        <Row label="Функции">{list(p.functions)}</Row>
        <Row label="Колонки">{list(p.columns)}</Row>
        <Row label="Узлов AST">{p.node_count}</Row>
      </dl>
      <div><div className="mb-1 text-[12px] text-muted">Нормализованный SQL</div><Code>{p.normalized_sql}</Code></div>
    </div>
  )
}

export function SchemaView({ schema, tables }: { schema: SchemaInfo; tables?: string[] }) {
  if (!schema.tables.length) return <Empty>Схема неизвестна. Подключите БД или вставьте DDL — это включит проверки индексов и типов.</Empty>
  const used = new Set((tables ?? []).map(t => t.toLowerCase()))
  const sorted = [...schema.tables].sort((x, y) => Number(used.has(y.name.toLowerCase())) - Number(used.has(x.name.toLowerCase())))
  return (
    <div className="space-y-3">
      <div className="text-[12px] text-muted">Источник: {schema.source === 'live' ? 'подключение к БД' : 'DDL'}</div>
      {sorted.map(t => (
        <details key={t.name} open={used.has(t.name.toLowerCase())} className="rounded-md border border-line bg-panel-2">
          <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-3 py-2">
            <span className="mono font-semibold">{t.name}</span>
            {used.has(t.name.toLowerCase()) && <Tag tone="accent">в запросе</Tag>}
            {t.row_count != null && <span className="text-[12px] text-muted">~{fmtNum(t.row_count)} строк</span>}
            {t.size_bytes != null && <span className="text-[12px] text-muted">{(t.size_bytes / 1048576).toFixed(1)} МБ</span>}
          </summary>
          <div className="grid gap-4 border-t border-line p-3 lg:grid-cols-2">
            <table className="text-[12.5px]"><tbody>
              {t.columns.map(c => (
                <tr key={c.name}><td className="mono pr-3">{c.name}</td><td className="mono pr-3 text-muted">{c.type}</td><td className="text-muted">{c.nullable ? 'NULL' : 'NOT NULL'}</td></tr>
              ))}
            </tbody></table>
            <div className="space-y-1 text-[12.5px]">
              {t.indexes.map(i => (
                <div key={i.name} className="mono"><span className={i.primary ? 'text-warn' : i.unique ? 'text-accent' : 'text-good'}>{i.primary ? 'PK' : i.unique ? 'UQ' : 'IX'}</span> {i.name} ({i.columns.join(', ')})</div>
              ))}
              {t.foreign_keys.map((f, k) => <div key={k} className="mono text-muted">FK ({f.columns.join(', ')}) → {f.ref_table}({f.ref_columns.join(', ')})</div>)}
              {!t.indexes.length && <div className="text-muted">Индексов нет</div>}
            </div>
          </div>
        </details>
      ))}
    </div>
  )
}
