import { useState } from 'react'
import type { AuditReport, ModelsInfo, TopQueries } from '../api'
import { api } from '../api'
import { download } from './ResultView'
import { Button, CopyBlock, Empty, ErrorBox, Spinner, Tag, fmtMs } from './ui'

const SEV = { high: { label: 'важно', tone: 'bad' }, medium: { label: 'стоит исправить', tone: 'warn' }, low: { label: 'к сведению', tone: 'muted' } } as const

export function AuditView({ connectionId }: { connectionId: number }) {
  const [report, setReport] = useState<AuditReport | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const run = async () => {
    setBusy(true); setError(null)
    try { setReport(await api.audit(connectionId)) } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  const fixes = report?.findings.filter(f => f.fix_sql && !f.fix_sql.startsWith('--')).map(f => f.fix_sql!).join('\n') ?? ''

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="primary" onClick={run} disabled={busy}>{busy && <Spinner />} {report ? 'Проверить заново' : 'Провести аудит'}</Button>
        <span className="text-[13px] text-stone">Ключи, индексы, типы данных и статистика планировщика. База не изменяется — исправления нужно выполнить самим.</span>
      </div>
      {error && <ErrorBox>{error}</ErrorBox>}
      {report && (
        <>
          <div className="grid gap-3 sm:grid-cols-4">
            <div className="card p-3"><div className="kicker text-stone">оценка</div><div className="mt-1 text-[28px] font-[450] tracking-[-0.04em]">{report.score}<span className="text-[14px] text-stone"> / 100</span></div></div>
            {(['high', 'medium', 'low'] as const).map(s => (
              <div key={s} className="card p-3"><div className="kicker text-stone">{SEV[s].label}</div><div className="mt-1 text-[28px] font-[450] tracking-[-0.04em]">{report.counts[s]}</div></div>
            ))}
          </div>
          {!report.usage_stats && <p className="text-[12.5px] text-stone">Статистика использования индексов недоступна (нет прав на performance_schema) — проверка неиспользуемых индексов пропущена.</p>}
          {!report.findings.length ? <Empty>Проблем не найдено: у всех таблиц есть ключи, внешние ключи проиндексированы, лишних индексов нет.</Empty> : (
            <div className="space-y-2">
              {report.findings.map((f, i) => (
                <details key={i} className="card p-3" open={f.severity === 'high' && i < 5}>
                  <summary className="flex cursor-pointer flex-wrap items-center gap-2 text-[14px]">
                    <Tag tone={SEV[f.severity].tone}>{SEV[f.severity].label}</Tag>
                    <span className="font-mono text-[12.5px] text-stone">{f.table}</span>
                    <span className="text-obsidian">{f.title}</span>
                  </summary>
                  <p className="mt-2 text-[13px] text-charcoal">{f.detail}</p>
                  {f.fix_sql && <div className="mt-2"><CopyBlock>{f.fix_sql}</CopyBlock></div>}
                </details>
              ))}
            </div>
          )}
          {fixes && <div className="flex justify-end"><Button onClick={() => download('audit_fixes.sql', `-- Исправления по аудиту базы. Проверьте перед выполнением!\n${fixes}\n`, 'text/plain;charset=utf-8')}>Скачать все исправления (.sql)</Button></div>}
        </>
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

export function DocsView({ connectionId, models, getErPng }: { connectionId: number; models: ModelsInfo | null; getErPng: () => Promise<string | null> }) {
  const [describe, setDescribe] = useState(false)
  const [withEr, setWithEr] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const llm = (models?.models ?? []).filter(m => !m.startsWith('baseline'))
  const build = async () => {
    setBusy(true); setError(null)
    try {
      const er = withEr ? await getErPng() : null
      const blob = await api.docs(connectionId, { describe, model: models?.default ?? null, er_png: er })
      download('Описание_базы_данных.docx', blob, blob.type)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <div className="max-w-2xl space-y-4 text-[13.5px]">
      <p className="text-charcoal">Документ Word с описанием базы: перечень таблиц, структура каждой таблицы (поля, типы, ключи, индексы) и связи между таблицами.
        Оформление по ГОСТ 2.105: Times New Roman 14, поля 30/10/20/20 мм, подписи таблиц «Таблица N – …». Подходит для пояснительной записки, курсовой и документации проекта.</p>
      <label className="flex items-center gap-2"><input type="checkbox" checked={withEr} onChange={e => setWithEr(e.target.checked)} /> Вставить схему связей (ER-диаграмму) рисунком</label>
      <label className={`flex items-center gap-2 ${llm.length ? '' : 'opacity-50'}`}>
        <input type="checkbox" checked={describe} disabled={!llm.length} onChange={e => setDescribe(e.target.checked)} />
        Описать назначение таблиц и полей с помощью ИИ {models?.default && llm.length > 0 && <span className="font-mono text-[12px] text-stone">({models.default.split(':').slice(1).join(':')})</span>}
      </label>
      {describe && <p className="text-[12.5px] text-stone">Модель видит только имена таблиц, столбцов и связи — не данные. Описания нужно проверить: модель может ошибиться в назначении.</p>}
      <Button variant="primary" onClick={build} disabled={busy}>{busy && <Spinner />} Скачать .docx</Button>
      {busy && describe && <span className="ml-3 text-[12.5px] text-stone">ИИ описывает таблицы — это может занять до минуты</span>}
      {error && <ErrorBox>{error}</ErrorBox>}
    </div>
  )
}
