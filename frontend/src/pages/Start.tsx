import { useState } from 'react'
import type { Connection, ModelsInfo, Stats } from '../api'
import { api } from '../api'
import { Button, Spinner } from '../components/ui'

export const DEMO_CONNECTIONS = {
  mysql: { name: 'Демо MySQL', dbms: 'mysql', host: '127.0.0.1', port: 3307, database: 'shop', username: 'optimizer_ro', password: 'optimizer_ro' },
  postgres: { name: 'Демо PostgreSQL', dbms: 'postgres', host: '127.0.0.1', port: 5434, database: 'shop', username: 'optimizer_ro', password: 'optimizer_ro' },
} as const

type State = 'ok' | 'todo' | 'optional' | 'wait'

/** Строка чек-листа в стиле CLI-вывода: ✓ зелёным для готового, › для того, что нужно сделать. */
function Check({ state, title, children, action }: { state: State; title: string; children: React.ReactNode; action?: React.ReactNode }) {
  const mark = { ok: '✓', todo: '›', optional: '○', wait: '…' }[state]
  const tone = { ok: 'text-terminal-green', todo: 'text-obsidian', optional: 'text-smoke', wait: 'text-smoke' }[state]
  const label = { ok: 'готово', todo: 'нужно сделать', optional: 'необязательно', wait: 'проверка' }[state]
  return (
    <div className="grid items-start gap-x-3 gap-y-2 border-t border-line px-4 py-3 [header+&]:border-t-0 sm:grid-cols-[16px_1fr_auto]">
      <span className={`font-mono text-[14px] leading-6 ${tone}`}>{mark}</span>
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-3">
          <span className="text-[14px] font-medium text-obsidian">{title}</span>
          <span className={`kicker ${state === 'ok' ? 'text-terminal-green' : 'text-smoke'}`}>{label}</span>
        </div>
        <div className="mt-1 text-[13px] leading-[1.54] text-charcoal">{children}</div>
      </div>
      {action && <div className="sm:self-center">{action}</div>}
    </div>
  )
}

const STEPS = [
  ['Вставьте запрос', 'SQL-запрос или целый скрипт. Можно взять готовый пример.'],
  ['Система ищет проблемы', 'Разбирает запрос, смотрит схему и план выполнения, проверяет 17 правил.'],
  ['ИИ предлагает ускорение', 'Языковая модель переписывает запрос с учётом найденных проблем.'],
  ['Всё проверяется на базе', 'Совпадает ли результат и стал ли запрос быстрее — по реальным замерам.'],
]

const VERDICTS = [
  ['Принята', 'good', 'результат совпал с исходным, запрос быстрее минимум на 5 %. Можно применять.'],
  ['Отклонена', 'bad', 'модель ошиблась: изменился результат, запрос замедлился или обратился к несуществующим данным.'],
  ['Без изменений', 'muted', 'проблем не найдено или ускорение в пределах погрешности.'],
  ['Не проверено', 'warn', 'база не подключена — результат и скорость не проверялись.'],
] as const

export function Start({ backendOk, models, connections, stats, onNavigate, onConnectionsChange }: {
  backendOk: boolean | null; models: ModelsInfo | null; connections: Connection[]; stats: Stats | null
  onNavigate: (p: string) => void; onConnectionsChange: () => void
}) {
  const [busy, setBusy] = useState<string | null>(null)
  const [demoError, setDemoError] = useState<string | null>(null)
  const llm = models?.providers.filter(p => p !== 'baseline') ?? []
  const runs = stats?.runs_total ?? 0

  const connectDemo = async (kind: keyof typeof DEMO_CONNECTIONS) => {
    setBusy(kind); setDemoError(null)
    try { await api.connect({ ...DEMO_CONNECTIONS[kind] }); onConnectionsChange() }
    catch (e) { setDemoError((e as Error).message) } finally { setBusy(null) }
  }

  const median = stats?.median_speedup
  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
        <section className="card">
          <header className="flex items-center justify-between border-b border-line px-4 py-3">
            <h3 className="kicker text-obsidian">Готовность к работе</h3>
            <span className="kicker text-smoke">обновляется само</span>
          </header>
          <Check state={backendOk == null ? 'wait' : backendOk ? 'ok' : 'todo'} title="Сервер программы"
            action={backendOk === false && <Button onClick={() => onNavigate('setup')}>Инструкция</Button>}>
            {backendOk == null ? 'Проверяем…' : backendOk ? 'Запущен локально и отвечает.' : 'Не отвечает. Запустите сервер — шаг 04 в разделе «Установка и помощь».'}
          </Check>
          <Check state={!models ? 'wait' : llm.length ? 'ok' : 'optional'} title="Модель ИИ"
            action={models && !llm.length && <Button onClick={() => onNavigate('setup')}>Настроить</Button>}>
            {!models ? 'Проверяем…' : llm.length
              ? <>Подключено: {llm.join(', ')}. По умолчанию — <span className="font-mono text-[12px]">{models.default ?? '—'}</span>.</>
              : 'Не настроена. Анализ и оптимизация по правилам работают и без неё; для ИИ укажите ключ GigaChat или локальную модель.'}
          </Check>
          <Check state={connections.length ? 'ok' : 'todo'} title="База данных"
            action={!connections.length && backendOk && <div className="flex gap-2">
              <Button onClick={() => connectDemo('mysql')} disabled={!!busy}>{busy === 'mysql' && <Spinner />} Демо MySQL</Button>
              <Button onClick={() => connectDemo('postgres')} disabled={!!busy}>{busy === 'postgres' && <Spinner />} Демо PostgreSQL</Button>
            </div>}>
            {connections.length
              ? <>Подключено: {connections.map(c => c.name).join(', ')}.</>
              : 'Без базы программа проверяет только текст запроса. Подключите демо-базу одной кнопкой (нужен Docker) или свою в разделе «Базы данных».'}
            {demoError && <div className="mt-1 text-obsidian">✕ Не удалось подключиться: {demoError}. Проверьте, что Docker запущен (шаг 03 инструкции).</div>}
          </Check>
          <Check state={runs ? 'ok' : 'optional'} title="Первый анализ"
            action={!runs && <Button variant="primary" onClick={() => onNavigate('analyzer')}>Открыть</Button>}>
            {runs ? `Выполнено запусков: ${runs}.` : 'Откройте «Анализ запроса»: там уже вставлен пример. Нажмите «Анализировать», затем «Оптимизировать с ИИ».'}
          </Check>
        </section>

        <section className="card flex flex-col">
          <header className="border-b border-line px-4 py-3"><h3 className="kicker text-obsidian">Быстрые действия</h3></header>
          <div className="flex flex-1 flex-col divide-y divide-line">
            {[
              ['analyzer', 'Проанализировать запрос', 'найти проблемы и ускорить', 'alt 2'],
              ['compare', 'Сравнить два запроса', 'результат и скорость', 'alt 3'],
              ['databases', 'Подключить базу данных', 'MySQL или PostgreSQL', 'alt 4'],
              ['experiments', 'Запустить эксперимент', 'набор запросов × модели', 'alt 5'],
            ].map(([id, t, d, k]) => (
              <button key={id} onClick={() => onNavigate(id)} className="group flex items-center gap-3 px-4 py-3 text-left hover:bg-paper-white">
                <span className="min-w-0 flex-1">
                  <span className="block text-[14px] text-obsidian">{t}</span>
                  <span className="block text-[13px] text-stone">{d}</span>
                </span>
                <span className="font-mono text-[11px] text-ash">{k}</span>
                <span className="text-stone transition-transform group-hover:translate-x-0.5">→</span>
              </button>
            ))}
          </div>
        </section>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          ['запусков', stats ? String(stats.runs_total) : '…', 'анализ и оптимизация'],
          ['принято', stats ? String(stats.successful_optimizations) : '…', 'результат совпал, быстрее ≥ 5 %'],
          ['медиана ускорения', median != null ? `${median.toFixed(1).replace('.', ',')}x` : '—', 'по измеренным на базе'],
          ['проверено на базе', stats ? String(stats.verified_runs) : '…', 'с проверкой результата'],
        ].map(([l, v, h]) => (
          <div key={l} className="card p-4">
            <div className="kicker text-stone">{l}</div>
            <div className="mt-3 text-[30px] font-[450] leading-none tracking-[-0.05em] tabular-nums text-obsidian">{v}</div>
            <div className="mt-2 text-[13px] text-stone">{h}</div>
          </div>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
        <section className="card">
          <header className="border-b border-line px-4 py-3"><h3 className="kicker text-obsidian">Как это работает</h3></header>
          <ol className="grid sm:grid-cols-2 xl:grid-cols-4">
            {STEPS.map(([t, d], i) => (
              <li key={t} className="border-line p-4 sm:[&:nth-child(n+2)]:border-l">
                <div className="font-mono text-[11px] text-stone">{String(i + 1).padStart(2, '0')}</div>
                <div className="mt-2 text-[14px] font-medium text-obsidian">{t}</div>
                <div className="mt-1 text-[13px] leading-[1.54] text-charcoal">{d}</div>
              </li>
            ))}
          </ol>
        </section>
        <section className="card">
          <header className="border-b border-line px-4 py-3"><h3 className="kicker text-obsidian">Что означает вердикт</h3></header>
          <ul className="space-y-2.5 p-4">
            {VERDICTS.map(([name, tone, d]) => (
              <li key={name} className="grid grid-cols-[120px_1fr] gap-3 text-[13px] leading-[1.54]">
                <span className={`kicker self-start justify-self-start whitespace-nowrap rounded-sm px-1.5 py-px ${tone === 'good' ? 'text-terminal-green shadow-[0_0_0_1px_#297a3a]' : tone === 'bad' ? 'bg-obsidian text-white' : tone === 'warn' ? 'text-charcoal shadow-[0_0_0_1px_#c9c9c9]' : 'text-stone shadow-[0_0_0_1px_#ebebeb]'}`}>{name}</span>
                <span className="text-charcoal">{d}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}
