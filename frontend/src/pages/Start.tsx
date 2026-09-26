import { useState } from 'react'
import type { Connection, ModelsInfo, Stats } from '../api'
import { api } from '../api'
import { Button, Card, Spinner } from '../components/ui'

export const DEMO_CONNECTIONS = {
  mysql: { name: 'Демо MySQL', dbms: 'mysql', host: '127.0.0.1', port: 3307, database: 'shop', username: 'optimizer_ro', password: 'optimizer_ro' },
  postgres: { name: 'Демо PostgreSQL', dbms: 'postgres', host: '127.0.0.1', port: 5434, database: 'shop', username: 'optimizer_ro', password: 'optimizer_ro' },
} as const

type State = 'ok' | 'todo' | 'optional' | 'wait'

function Check({ state, title, children, action }: { state: State; title: string; children: React.ReactNode; action?: React.ReactNode }) {
  const label = { ok: 'Готово', todo: 'Нужно сделать', optional: 'Необязательно', wait: 'Проверка…' }[state]
  const tone = { ok: 'text-good', todo: 'text-accent', optional: 'text-muted', wait: 'text-muted' }[state]
  return (
    <div className="grid items-start gap-3 border-t border-line py-4 sm:grid-cols-[130px_1fr_auto]">
      <div className={`kicker pt-0.5 ${tone}`}>{state === 'ok' ? '■ ' : '□ '}{label}</div>
      <div className="min-w-0 flex-1">
        <div className="text-[13.5px] font-semibold">{title}</div>
        <div className="mt-0.5 text-[12.5px] leading-relaxed text-muted">{children}</div>
      </div>
      {action && <div className="shrink-0 self-center">{action}</div>}
    </div>
  )
}

const STEPS = [
  { t: 'Вставьте запрос', d: 'SQL-запрос или целый скрипт. Можно взять готовый пример.' },
  { t: 'Система ищет проблемы', d: 'Разбирает запрос, смотрит схему и план выполнения, проверяет 17 правил.' },
  { t: 'ИИ предлагает ускорение', d: 'Языковая модель переписывает запрос с учётом найденных проблем.' },
  { t: 'Всё проверяется на базе', d: 'Совпадает ли результат и стал ли запрос быстрее — по реальным замерам.' },
]

const VERDICTS = [
  ['Оптимизация принята', 'good', 'результат совпал с исходным, запрос стал быстрее минимум на 5 %. Можно применять.'],
  ['Оптимизация отклонена', 'bad', 'модель ошиблась: изменился результат, запрос замедлился или обратился к несуществующим данным. Применять нельзя.'],
  ['Без изменений', 'muted', 'проблем не найдено или ускорение в пределах погрешности.'],
  ['Не проверено на БД', 'warn', 'база не подключена, поэтому результат и скорость не проверялись. Подключите базу, чтобы получить надёжный вердикт.'],
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

  return (
    <div className="mx-auto max-w-5xl space-y-12 pb-16">
      <section className="grid gap-8 pt-2 lg:grid-cols-[1fr_280px]">
        <div>
        <div className="kicker text-accent">Оптимизация SQL-запросов с проверкой</div>
        <h2 className="mt-3 text-[44px] font-bold leading-[1.02] tracking-[-0.02em]">Ускоряйте SQL-запросы с&nbsp;ИИ.<br /><span className="text-muted">Точно зная, что ничего не сломалось.</span></h2>
        <p className="mt-5 max-w-2xl text-[14.5px] leading-relaxed text-muted">
          Программа находит причины медленной работы запроса, просит языковую модель предложить более быструю версию
          и проверяет её на вашей базе данных: совпадает ли результат и насколько запрос реально ускорился.
          Базы данных только читаются — ничего не изменяется.
        </p>
        <div className="mt-6 flex flex-wrap gap-2">
          <Button variant="primary" onClick={() => onNavigate('analyzer')}>Попробовать на примере →</Button>
          <Button onClick={() => onNavigate('setup')}>Как установить и настроить</Button>
        </div>
        </div>
        <div className="space-y-5 border-l border-line pl-6 lg:pt-8">
          {[['17', 'правил анализа'], ['2', 'СУБД: MySQL и PostgreSQL'], ['4', 'проверки каждой рекомендации ИИ']].map(([v, l]) => (
            <div key={l}><div className="text-[40px] font-bold leading-none tracking-tight">{v}</div><div className="mt-1 text-[12.5px] text-muted">{l}</div></div>
          ))}
        </div>
      </section>

      <section>
        <h3 className="kicker mb-4">Как это работает</h3>
        <div className="grid gap-px bg-line sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((s, i) => (
            <div key={s.t} className="bg-bg p-5 pl-0 pr-6 sm:pl-5 first:sm:pl-0">
              <div className="text-[32px] font-bold leading-none tabular-nums text-accent">{String(i + 1).padStart(2, '0')}</div>
              <div className="mt-4 text-[15px] font-semibold leading-snug">{s.t}</div>
              <div className="mt-2 text-[12.5px] leading-relaxed text-muted">{s.d}</div>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h3 className="kicker mb-1">Готовность к работе</h3>
        <div className="border-b border-line">
          <Check state={backendOk == null ? 'wait' : backendOk ? 'ok' : 'todo'} title="Сервер программы"
            action={backendOk === false && <Button onClick={() => onNavigate('setup')}>Инструкция</Button>}>
            {backendOk == null ? 'Проверяем…' : backendOk ? 'Запущен и отвечает.' : 'Не отвечает. Запустите сервер (backend) — инструкция в разделе «Установка».'}
          </Check>
          <Check state={!models ? 'wait' : llm.length ? 'ok' : 'optional'} title="Модель искусственного интеллекта"
            action={models && !llm.length && <Button onClick={() => onNavigate('setup')}>Настроить</Button>}>
            {!models ? 'Проверяем…' : llm.length
              ? <>Подключено: {llm.join(', ')} · моделей: {models.models.filter(m => m !== models.baseline).length}. По умолчанию — <span className="mono">{models.default ?? '—'}</span>.</>
              : 'Не настроена. Анализ, поиск проблем и оптимизация по правилам работают и без неё; для ИИ-оптимизации укажите ключ GigaChat, YandexGPT или локальную модель Ollama.'}
          </Check>
          <Check state={connections.length ? 'ok' : 'todo'} title="База данных"
            action={!connections.length && backendOk && <div className="flex gap-2">
              <Button onClick={() => connectDemo('mysql')} disabled={!!busy}>{busy === 'mysql' && <Spinner />} Демо MySQL</Button>
              <Button onClick={() => connectDemo('postgres')} disabled={!!busy}>{busy === 'postgres' && <Spinner />} Демо PostgreSQL</Button>
            </div>}>
            {connections.length
              ? <>Подключено: {connections.map(c => c.name).join(', ')}.</>
              : <>Без базы программа только ищет проблемы в тексте запроса. Подключите демо-базу интернет-магазина одной кнопкой (нужен запущенный Docker) или свою в разделе «Базы данных».</>}
            {demoError && <div className="mt-1 text-bad">Не удалось подключиться: {demoError}. Проверьте, что Docker запущен и выполнена команда из шага 3 инструкции.</div>}
          </Check>
          <Check state={runs ? 'ok' : 'optional'} title="Первый анализ"
            action={!runs && <Button variant="primary" onClick={() => onNavigate('analyzer')}>Открыть</Button>}>
            {runs ? `Выполнено запусков: ${runs}. Результаты — в разделах «История» и «Обзор».` : 'Откройте «Анализ запроса»: там уже вставлен пример. Нажмите «Анализировать», затем «Оптимизировать с помощью ИИ».'}
          </Check>
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Что означают результаты">
          <ul className="space-y-2.5">
            {VERDICTS.map(([name, tone, d]) => (
              <li key={name} className="text-[13px] leading-relaxed">
                <span className={`mr-1.5 border px-1.5 py-0.5 text-[11px] font-semibold ${tone === 'good' ? 'border-good text-good' : tone === 'bad' ? 'border-bad text-bad' : tone === 'warn' ? 'border-warn text-warn' : 'border-line text-muted'}`}>{name}</span>
                <span className="text-muted">— {d}</span>
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Разделы программы">
          <ul className="space-y-2 text-[13px]">
            {[
              ['analyzer', 'Анализ запроса', 'главный инструмент: найти проблемы и ускорить запрос'],
              ['compare', 'Сравнение запросов', 'проверить свой вариант запроса против исходного'],
              ['databases', 'Базы данных', 'подключить базу и посмотреть её таблицы и индексы'],
              ['experiments', 'Эксперименты', 'прогнать набор запросов через несколько моделей и получить отчёт'],
              ['history', 'История', 'все запуски, выгрузка результатов'],
            ].map(([id, t, d]) => (
              <li key={id}><button className="font-semibold text-text underline decoration-line underline-offset-4 hover:decoration-accent" onClick={() => onNavigate(id)}>{t}</button><span className="text-muted"> — {d}</span></li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  )
}
