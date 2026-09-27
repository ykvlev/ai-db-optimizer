import { useCallback, useEffect, useRef, useState } from 'react'
import type { AnalyzerDraft, CompareDraft, Connection, Examples, ModelsInfo, Stats } from './api'
import { api } from './api'
import { Analyzer } from './pages/Analyzer'
import { Compare } from './pages/Compare'
import { Console } from './pages/Console'
import { Dashboard } from './pages/Dashboard'
import { Databases } from './pages/Databases'
import { Experiments } from './pages/Experiments'
import { History } from './pages/History'
import { Setup } from './pages/Setup'
import { Start } from './pages/Start'
import { Logo } from './components/Logo'

// В режиме разработки интерфейс (Vite, :5173) и сервер (:8000) разные; в Docker сервер сам раздаёт интерфейс
const SERVER_HOST = window.location.port === '5173' ? 'localhost:8000' : window.location.host

const pages = [
  { id: 'start', label: 'Начало', group: 'Главная', desc: 'Состояние программы и быстрые действия' },
  { id: 'console', label: 'Консоль', group: 'Работа', desc: 'Запросы к вашей базе и вопросы на русском: ИИ составит SQL по структуре базы, результат — таблицей или графиком' },
  { id: 'analyzer', label: 'Анализ запроса', group: 'Работа', desc: 'Вставьте SQL — программа найдёт проблемы, а ИИ предложит более быструю версию и проверит её на базе' },
  { id: 'compare', label: 'Сравнение запросов', group: 'Работа', desc: 'Два варианта запроса: совпадает ли результат и какой из них быстрее' },
  { id: 'databases', label: 'Базы данных', group: 'Работа', desc: 'Подключения, структура, аудит, медленные запросы, ER-диаграмма и описание базы в Word' },
  { id: 'experiments', label: 'Эксперименты', group: 'Исследования', desc: 'Набор запросов × несколько моделей: статистика, сравнение и отчёт' },
  { id: 'history', label: 'История', group: 'Исследования', desc: 'Все запуски анализа и оптимизации, выгрузка результатов' },
  { id: 'dashboard', label: 'Обзор', group: 'Исследования', desc: 'Сводные показатели по всем запускам' },
  { id: 'setup', label: 'Установка и помощь', group: 'Справка', desc: 'Как поставить программу на компьютер и подключить модель ИИ' },
] as const
type PageId = typeof pages[number]['id']

function currentPage(): PageId {
  const h = window.location.hash.replace('#/', '').split('/')[0] as PageId
  return pages.some(p => p.id === h) ? h : 'start'
}

function Dot({ ok }: { ok: boolean | null }) {
  return <span className={`inline-block h-1.5 w-1.5 rounded-full ${ok == null ? 'bg-ash' : ok ? 'bg-terminal-green' : 'bg-obsidian'}`} />
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
  // новый раздел открывается с начала, а не с прокрутки предыдущего
  const scrollRef = useRef<HTMLDivElement>(null)
  useEffect(() => { scrollRef.current?.scrollTo({ top: 0 }) }, [page])
  const [compareDraft, setCompareDraft] = useState<CompareDraft | null>(null)
  const sendToCompare = (d: Omit<CompareDraft, 'nonce'>) => { setCompareDraft({ ...d, nonce: Date.now() }); go('compare') }
  const [analyzerDraft, setAnalyzerDraft] = useState<AnalyzerDraft | null>(null)
  const sendToAnalyzer = (sql: string, connectionId: number | null) => { setAnalyzerDraft({ sql, connectionId, nonce: Date.now() }); go('analyzer') }
  const meta = pages.find(p => p.id === page)!
  const llm = models?.providers.filter(p => p !== 'baseline') ?? []

  // быстрый переход Alt+1…8 между разделами, как в настольных инструментах
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!e.altKey || e.ctrlKey || e.metaKey) return
      const n = Number(e.key)
      if (n >= 1 && n <= pages.length) { e.preventDefault(); window.location.hash = `#/${pages[n - 1].id}` }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const groups = ['Главная', 'Работа', 'Исследования', 'Справка'] as const

  return (
    <div className="flex h-full">
      <aside className="flex w-[232px] shrink-0 flex-col border-r border-line bg-white">
        <div className="flex h-12 items-center border-b border-line px-4">
          <button onClick={() => go('start')} aria-label="Начало"><Logo /></button>
        </div>
        <div className="border-b border-line px-3 py-3">
          <div className="flex items-center gap-2 rounded-md bg-paper-white px-2.5 py-2 shadow-[0_0_0_1px_#ebebeb]">
            <Dot ok={backendOk} />
            <div className="min-w-0 flex-1 leading-tight">
              <div className="truncate text-[13px] text-obsidian">Локальная установка</div>
              <div className="truncate font-mono text-[11px] text-stone">{SERVER_HOST}</div>
            </div>
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto px-2 py-3">
          {groups.map(g => {
            const items = pages.filter(p => p.group === g)
            return (
              <div key={g} className="mb-3">
                {g !== 'Главная' && <div className="kicker px-2 pb-1 pt-2 text-smoke">{g}</div>}
                {items.map(p => {
                  const active = page === p.id
                  return (
                    <button key={p.id} onClick={() => go(p.id)}
                      className={`group flex h-8 w-full items-center gap-2 rounded-md px-2 text-left text-[14px] transition-colors ${active ? 'bg-paper-white text-obsidian shadow-[0_0_0_1px_#ebebeb]' : 'text-charcoal hover:bg-paper-white hover:text-obsidian'}`}>
                      <span className="flex-1">{p.label}</span>
                      <span className={`font-mono text-[10.5px] ${active ? 'text-stone' : 'text-ash group-hover:text-smoke'}`}>alt {pages.indexOf(p) + 1}</span>
                    </button>
                  )
                })}
              </div>
            )
          })}
        </nav>
        <div className="space-y-1.5 border-t border-line px-4 py-3 font-mono text-[11px] text-stone">
          <div className="flex items-center gap-2"><Dot ok={backendOk} /><span className="flex-1">сервер</span><span>{backendOk == null ? '…' : backendOk ? 'online' : 'offline'}</span></div>
          <div className="flex items-center gap-2"><Dot ok={models ? llm.length > 0 : null} /><span className="flex-1">модель</span><span className="truncate">{models?.default?.split(':').slice(1).join(':') || (models ? '—' : '…')}</span></div>
          <div className="flex items-center gap-2"><Dot ok={backendOk ? connections.length > 0 : null} /><span className="flex-1">базы</span><span>{connections.length}</span></div>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-2 border-b border-line bg-bg/80 px-6 font-mono text-[12px] text-stone backdrop-blur-xl">
          <span>optimizer</span><span className="text-ash">/</span><span className="text-obsidian">{meta.label.toLowerCase()}</span>
          <span className="ml-auto hidden text-ash md:inline">{meta.group !== 'Главная' ? meta.group.toLowerCase() : 'рабочий стол'}</span>
        </header>
        <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto">
          <div className="px-6 pb-16 pt-6">
            {page !== 'setup' && (
              <div className="mb-6">
                <h1 className="text-[24px] font-[450] leading-[1.15] tracking-[-0.04em] text-obsidian">{meta.label}</h1>
                <p className="mt-1 text-[14px] text-charcoal">{meta.desc}</p>
              </div>
            )}
            {backendOk === false && page !== 'setup' && (
              <div className="card mb-6 flex flex-wrap items-center gap-4 px-4 py-3">
                <span className="font-mono text-[12px]">✕</span>
                <div className="min-w-0 flex-1 text-[14px]">
                  <div className="font-medium text-obsidian">Сервер программы не запущен</div>
                  <div className="text-charcoal">Запустите его (шаг 04 инструкции или scripts\start.ps1). Интерфейс оживёт сам, как только сервер ответит.</div>
                </div>
                <button className="h-8 rounded-md bg-obsidian px-3 text-[14px] text-white hover:bg-charcoal" onClick={() => go('setup')}>Инструкция</button>
              </div>
            )}
            <div hidden={page !== 'start'}><Start backendOk={backendOk} models={models} connections={connections} stats={stats} onNavigate={go} onConnectionsChange={loadConnections} /></div>
            <div hidden={page !== 'dashboard'}><Dashboard stats={stats} onNavigate={go} /></div>
            <div hidden={page !== 'console'}><Console connections={connections} models={models} onOptimize={sendToAnalyzer} onNavigate={go} /></div>
            <div hidden={page !== 'analyzer'}><Analyzer connections={connections} models={models} examples={examples} onRun={refresh} onSendToCompare={sendToCompare} onNavigate={go} draft={analyzerDraft} /></div>
            <div hidden={page !== 'compare'}><Compare connections={connections} onRun={refresh} draft={compareDraft} /></div>
            <div hidden={page !== 'experiments'}><Experiments connections={connections} models={models} onRun={refresh} /></div>
            <div hidden={page !== 'databases'}><Databases connections={connections} onChange={loadConnections} models={models} onOptimize={sendToAnalyzer} /></div>
            <div hidden={page !== 'history'}><History refreshKey={refreshKey} /></div>
            <div hidden={page !== 'setup'}><Setup /></div>
          </div>
        </div>
      </main>
    </div>
  )
}
