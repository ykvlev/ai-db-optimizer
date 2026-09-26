import { useCallback, useEffect, useState } from 'react'
import type { CompareDraft, Connection, Examples, ModelsInfo, Stats } from './api'
import { api } from './api'
import { Analyzer } from './pages/Analyzer'
import { Compare } from './pages/Compare'
import { Dashboard } from './pages/Dashboard'
import { Databases } from './pages/Databases'
import { Experiments } from './pages/Experiments'
import { History } from './pages/History'
import { Setup } from './pages/Setup'
import { Start } from './pages/Start'

const pages = [
  { id: 'start', label: 'Начало', group: 'Работа', desc: 'Что умеет программа и готова ли она к работе' },
  { id: 'analyzer', label: 'Анализ запроса', group: 'Работа', desc: 'Вставьте SQL — программа найдёт проблемы, а ИИ предложит более быструю версию и проверит её на базе' },
  { id: 'compare', label: 'Сравнение запросов', group: 'Работа', desc: 'Два варианта запроса: совпадает ли результат и какой из них быстрее' },
  { id: 'databases', label: 'Базы данных', group: 'Работа', desc: 'Подключения к базам и их структура: таблицы, колонки, индексы' },
  { id: 'experiments', label: 'Эксперименты', group: 'Исследования', desc: 'Набор запросов × несколько моделей: статистика, сравнение и отчёт' },
  { id: 'history', label: 'История', group: 'Исследования', desc: 'Все запуски анализа и оптимизации, выгрузка результатов' },
  { id: 'dashboard', label: 'Обзор', group: 'Исследования', desc: 'Сводные показатели по всем запускам' },
  { id: 'setup', label: 'Установка и помощь', group: 'Справка', desc: 'Как поставить программу на компьютер и подключить модель ИИ' },
] as const
type PageId = typeof pages[number]['id']
const groups = ['Работа', 'Исследования', 'Справка'] as const

function currentPage(): PageId {
  const h = window.location.hash.replace('#/', '').split('/')[0] as PageId
  return pages.some(p => p.id === h) ? h : 'start'
}

function Dot({ ok }: { ok: boolean | null }) {
  return <span className={`inline-block h-1.5 w-1.5 ${ok == null ? 'bg-muted' : ok ? 'bg-good' : 'bg-accent'}`} />
}

export default function App() {
  const [page, setPage] = useState<PageId>(currentPage)
  const [connections, setConnections] = useState<Connection[]>([])
  const [models, setModels] = useState<ModelsInfo | null>(null)
  const [examples, setExamples] = useState<Examples | null>(null)
  const [stats, setStats] = useState<Stats | null>(null)
  const [backendOk, setBackendOk] = useState<boolean | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  const loadConnections = useCallback(() => api.connections().then(setConnections).catch(() => {}), [])
  const refresh = useCallback(() => {
    setRefreshKey(k => k + 1)
    api.stats().then(setStats).catch(() => {})
  }, [])
  const probe = useCallback(() => {
    api.models().then(m => { setModels(m); setBackendOk(true) }).catch(() => setBackendOk(false))
    api.examples().then(setExamples).catch(() => {})
    loadConnections()
    refresh()
  }, [loadConnections, refresh])

  useEffect(() => {
    probe()
    const onHash = () => setPage(currentPage())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [probe])

  // пока сервер недоступен, проверяем его раз в 5 секунд — интерфейс оживёт сам после запуска
  useEffect(() => {
    if (backendOk !== false) return
    const t = setInterval(probe, 5000)
    return () => clearInterval(t)
  }, [backendOk, probe])

  const go = (p: string) => { window.location.hash = `#/${p}` }
  const [compareDraft, setCompareDraft] = useState<CompareDraft | null>(null)
  const sendToCompare = (d: Omit<CompareDraft, 'nonce'>) => { setCompareDraft({ ...d, nonce: Date.now() }); go('compare') }
  const meta = pages.find(p => p.id === page)!
  const llm = models?.providers.filter(p => p !== 'baseline') ?? []

  return (
    <div className="flex h-full">
      <aside className="flex w-60 shrink-0 flex-col border-r border-line bg-bg">
        <button onClick={() => go('start')} className="px-5 pb-6 pt-5 text-left">
          <div className="text-[19px] font-bold leading-[1.05] tracking-tight">AI Database<br />Optimizer</div>
          <div className="mt-2 h-[3px] w-8 bg-accent" />
        </button>
        <nav className="flex flex-col gap-5 px-3">
          {groups.map(g => (
            <div key={g}>
              <div className="kicker px-2 pb-1.5 text-muted">{g}</div>
              {pages.filter(p => p.group === g).map(p => {
                const active = page === p.id
                return (
                  <button key={p.id} onClick={() => go(p.id)}
                    className={`flex w-full items-center gap-3 border-l-2 px-2 py-1.5 text-left text-[13.5px] transition ${active ? 'border-accent font-semibold text-text' : 'border-transparent text-muted hover:text-text'}`}>
                    <span className="w-5 text-[11px] tabular-nums text-muted">{String(pages.indexOf(p) + 1).padStart(2, '0')}</span>{p.label}
                  </button>
                )
              })}
            </div>
          ))}
        </nav>
        <div className="mt-auto space-y-1.5 border-t border-line px-5 py-4 text-[12px] text-muted">
          <div className="flex items-center gap-2"><Dot ok={backendOk} /> Сервер: {backendOk == null ? '…' : backendOk ? 'работает' : 'недоступен'}</div>
          <div className="flex items-center gap-2"><Dot ok={models ? llm.length > 0 : null} /> ИИ: {models ? (llm.length ? llm.join(', ') : 'не настроен') : '…'}</div>
          <div className="flex items-center gap-2"><Dot ok={backendOk ? connections.length > 0 : null} /> Баз данных: {connections.length}</div>
        </div>
      </aside>

      <main className="min-w-0 flex-1 overflow-auto">
        <header className="sticky top-0 z-10 border-b border-line bg-bg/95 px-8 pb-4 pt-6 backdrop-blur">
          <h1 className="text-[26px] font-bold leading-none tracking-tight">{meta.label}</h1>
          <p className="mt-2 text-[13px] text-muted">{meta.desc}</p>
        </header>
        <div className="p-8">
          {backendOk === false && page !== 'setup' && (
            <div className="mb-6 flex flex-wrap items-center gap-4 border-l-2 border-accent bg-panel px-4 py-3">
              <div className="min-w-0 flex-1 text-[13px]">
                <div className="font-semibold">Сервер программы не запущен</div>
                <div className="text-muted">Запустите его (шаг 4 инструкции или scripts\start.ps1). Страница обновится сама, как только сервер ответит.</div>
              </div>
              <button className="border border-text px-3 py-1.5 text-[13px] font-semibold hover:border-accent hover:text-accent" onClick={() => go('setup')}>Открыть инструкцию</button>
            </div>
          )}
          <div hidden={page !== 'start'}><Start backendOk={backendOk} models={models} connections={connections} stats={stats} onNavigate={go} onConnectionsChange={loadConnections} /></div>
          <div hidden={page !== 'dashboard'}><Dashboard stats={stats} onNavigate={go} /></div>
          <div hidden={page !== 'analyzer'}><Analyzer connections={connections} models={models} examples={examples} onRun={refresh} onSendToCompare={sendToCompare} onNavigate={go} /></div>
          <div hidden={page !== 'compare'}><Compare connections={connections} onRun={refresh} draft={compareDraft} /></div>
          <div hidden={page !== 'experiments'}><Experiments connections={connections} models={models} onRun={refresh} /></div>
          <div hidden={page !== 'databases'}><Databases connections={connections} onChange={loadConnections} /></div>
          <div hidden={page !== 'history'}><History refreshKey={refreshKey} /></div>
          <div hidden={page !== 'setup'}><Setup /></div>
        </div>
      </main>
    </div>
  )
}
