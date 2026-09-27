import { useEffect, useState } from 'react'
import type { DbOverview } from '../api'
import { Button, Spinner } from './ui'

export const schemaOf = (table: string, def: string) => table.includes('.') ? table.slice(0, table.lastIndexOf('.')) : def

// «Знакомство с базой»: выбор рабочей схемы, анализ базы моделью и готовые запросы
export function DbIntro({ overview, busy, hasModel, onChoose, onRun }: {
  overview: DbOverview
  busy: boolean
  hasModel: boolean
  onChoose: (schema: string, analyze: boolean) => void
  onRun: (sql: string) => void
}) {
  const { schemas, selected, profile } = overview
  const [pick, setPick] = useState<string>(selected ?? schemas[0]?.name ?? '')
  const [changing, setChanging] = useState(false)
  useEffect(() => { setPick(selected ?? schemas[0]?.name ?? ''); setChanging(false) }, [selected, schemas])

  const chooser = (
    <div className="flex flex-wrap gap-2">
      {schemas.map(s => (
        <button key={s.name} onClick={() => setPick(s.name)}
          className={`rounded-md px-3 py-2 text-left text-[13px] transition-shadow ${pick === s.name ? 'bg-obsidian text-white' : 'shadow-[0_0_0_1px_#ebebeb] hover:shadow-[0_0_0_1px_#a8a8a8]'}`}>
          <div className="font-mono">{s.name}{s.default && <span className={pick === s.name ? 'text-ash' : 'text-stone'}> · по умолчанию</span>}</div>
          <div className={`text-[11.5px] ${pick === s.name ? 'text-ash' : 'text-stone'}`}>{s.tables} табл. · ~{s.rows.toLocaleString('ru-RU')} строк</div>
        </button>
      ))}
    </div>
  )
  const actions = (
    <div className="flex flex-wrap items-center gap-2">
      <Button variant="primary" onClick={() => onChoose(pick, true)} disabled={busy || !pick || !hasModel}>{busy && <Spinner />} Проанализировать с ИИ</Button>
      <Button onClick={() => onChoose(pick, false)} disabled={busy || !pick}>Выбрать без анализа</Button>
      {busy && <span className="text-[12.5px] text-stone">Модель изучает структуру и проверяет запросы на базе — 10–30 секунд</span>}
      {!hasModel && <span className="text-[12.5px] text-stone">Для анализа нужна модель ИИ</span>}
    </div>
  )

  // первое открытие базы или смена схемы
  if (!selected || changing) return (
    <div className="card space-y-3 p-4">
      <div>
        <div className="kicker text-stone">{selected ? 'Смена рабочей схемы' : 'Знакомство с базой'}</div>
        <p className="mt-1 text-[13.5px] text-charcoal">
          {schemas.length > 1
            ? 'В базе несколько схем. Выберите рабочую — консоль, подсказки и ИИ будут работать с её таблицами.'
            : 'База открыта в консоли впервые.'} ИИ посмотрит на структуру (не на данные), объяснит, что это за база, и предложит готовые запросы.
        </p>
      </div>
      {schemas.length > 1 && chooser}
      {actions}
      {changing && <button className="text-[12.5px] text-stone underline" onClick={() => setChanging(false)}>Отмена</button>}
    </div>
  )

  return (
    <details className="card p-4" open>
      <summary className="flex cursor-pointer flex-wrap items-center gap-2">
        <span className="kicker text-stone">О базе</span>
        <span className="font-mono text-[12.5px] text-obsidian">схема {selected}</span>
        <span className="ml-auto" />
        <button className="text-[12.5px] text-stone underline" onClick={e => { e.preventDefault(); setChanging(true) }}>сменить схему</button>
        {hasModel && <button className="text-[12.5px] text-stone underline" disabled={busy} onClick={e => { e.preventDefault(); onChoose(selected, true) }}>{busy ? 'анализ…' : profile ? 'обновить анализ' : 'проанализировать'}</button>}
      </summary>
      {!profile ? <p className="mt-3 text-[13px] text-stone">Анализа ещё нет — нажмите «проанализировать», и ИИ предложит готовые запросы для этой схемы.</p> : (
        <div className="mt-3 space-y-4">
          <p className="text-[14px] leading-[1.5] text-obsidian">{profile.summary}</p>
          {profile.entities.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {profile.entities.map(e => (
                <span key={e.table} className="rounded-md px-2 py-1 text-[12px] shadow-[0_0_0_1px_#ebebeb]">
                  <span className="font-mono text-obsidian">{e.table.split('.').pop()}</span> <span className="text-stone">— {e.meaning}</span>
                </span>
              ))}
            </div>
          )}
          {profile.relations.length > 0 && <div className="text-[12.5px] text-stone">Связи: {profile.relations.join(' · ')}</div>}
          {profile.queries.length > 0 && (
            <div>
              <div className="kicker mb-2 text-stone">Готовые запросы — щелчок запускает</div>
              <div className="grid gap-2 md:grid-cols-2">
                {profile.queries.map((q, i) => (
                  <button key={i} onClick={() => onRun(q.sql)} className="rounded-md p-3 text-left shadow-[0_0_0_1px_#ebebeb] transition-shadow hover:shadow-[0_0_0_1px_#171717]">
                    <div className="text-[13.5px] font-medium text-obsidian">{q.title}</div>
                    <div className="mt-0.5 text-[12.5px] text-stone">{q.description}</div>
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="font-mono text-[11px] text-ash">
            {profile.model.split(':').slice(1).join(':')} · {new Date(profile.created_at).toLocaleString('ru-RU', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })}
            {profile.rejected > 0 && ` · отброшено запросов с ошибками: ${profile.rejected}`} · нужен другой запрос — спросите выше
          </div>
        </div>
      )}
    </details>
  )
}
