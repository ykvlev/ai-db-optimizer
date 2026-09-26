import { useCallback, useEffect, useState } from 'react'
import type { CompareDraft, Connection, Examples, ModelsInfo, Stats } from './api'
import { api } from './api'
import { Analyzer } from './pages/Analyzer'
import { Compare } from './pages/Compare'
import { Dashboard } from './pages/Dashboard'
import { Databases } from './pages/Databases'
import { Experiments } from './pages/Experiments'
import { History } from './pages/History'

const pages = [
  { id: 'dashboard', label: 'Dashboard', icon: '◧' },
  { id: 'analyzer', label: 'SQL Analyzer', icon: '⌘' },
  { id: 'compare', label: 'Сравнение', icon: '⇄' },
  { id: 'experiments', label: 'Эксперименты', icon: '⚗' },
  { id: 'databases', label: 'Базы данных', icon: '⛁' },
  { id: 'history', label: 'История и датасет', icon: '☰' },
] as const
type PageId = typeof pages[number]['id']

function currentPage(): PageId {
  const h = window.location.hash.replace('#/', '').split('/')[0] as PageId
  return pages.some(p => p.id === h) ? h : 'analyzer'
}

export default function App() {
  const [page, setPage] = useState<PageId>(currentPage)
  const [connections, setConnections] = useState<Connection[]>([])
  const [models, setModels] = useState<ModelsInfo | null>(null)
  const [examples, setExamples] = useState<Examples | null>(null)
  const [stats, setStats] = useState<Stats | null>(null)
  const [backendError, setBackendError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  const loadConnections = useCallback(() => api.connections().then(setConnections).catch(() => {}), [])
  const refresh = useCallback(() => {
    setRefreshKey(k => k + 1)
    api.stats().then(setStats).catch(() => {})
  }, [])

  useEffect(() => {
    api.models().then(setModels).then(() => setBackendError(null))
      .catch(e => setBackendError(`Backend недоступен: ${(e as Error).message}. Запустите: uvicorn app.main:app --port 8000`))
    api.examples().then(setExamples).catch(() => {})
    loadConnections()
    refresh()
    const onHash = () => setPage(currentPage())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [loadConnections, refresh])

  const go = (p: string) => { window.location.hash = `#/${p}` }
  const [compareDraft, setCompareDraft] = useState<CompareDraft | null>(null)
  const sendToCompare = (d: Omit<CompareDraft, 'nonce'>) => { setCompareDraft({ ...d, nonce: Date.now() }); go('compare') }

  return (
    <div className="flex h-full">
      <aside className="flex w-56 shrink-0 flex-col border-r border-line bg-panel">
        <div className="px-4 py-4">
          <div className="text-[15px] font-bold tracking-tight">AI Database Optimizer</div>
          <div className="text-[11px] text-muted">анализ и оптимизация SQL</div>
        </div>
        <nav className="flex flex-col gap-0.5 px-2">
          {pages.map(p => (
            <button key={p.id} onClick={() => go(p.id)}
              className={`flex items-center gap-2.5 rounded-md px-3 py-2 text-left text-[13px] transition ${page === p.id ? 'bg-accent/15 text-text' : 'text-muted hover:bg-panel-2 hover:text-text'}`}>
              <span className="w-4 text-center">{p.icon}</span>{p.label}
            </button>
          ))}
        </nav>
        <div className="mt-auto space-y-1 border-t border-line px-4 py-3 text-[11.5px] text-muted">
          <div>LLM: {models ? (models.providers.length ? models.providers.join(', ') : 'не настроен') : '…'}</div>
          <div>Подключений: {connections.length}</div>
        </div>
      </aside>

      <main className="min-w-0 flex-1 overflow-auto">
        <header className="sticky top-0 z-10 border-b border-line bg-bg/90 px-6 py-3 backdrop-blur">
          <h1 className="text-[16px] font-semibold">{pages.find(p => p.id === page)?.label}</h1>
        </header>
        <div className="p-6">
          {backendError && <div className="mb-4 rounded-md border border-bad/40 bg-bad/10 px-3 py-2 text-[13px] text-bad">{backendError}</div>}
          <div hidden={page !== 'dashboard'}><Dashboard stats={stats} onNavigate={go} /></div>
          <div hidden={page !== 'analyzer'}><Analyzer connections={connections} models={models} examples={examples} onRun={refresh} onSendToCompare={sendToCompare} /></div>
          <div hidden={page !== 'compare'}><Compare connections={connections} onRun={refresh} draft={compareDraft} /></div>
          <div hidden={page !== 'experiments'}><Experiments connections={connections} models={models} onRun={refresh} /></div>
          <div hidden={page !== 'databases'}><Databases connections={connections} onChange={loadConnections} /></div>
          <div hidden={page !== 'history'}><History refreshKey={refreshKey} /></div>
        </div>
      </main>
    </div>
  )
}
