import { useEffect, useRef, useState } from 'react'
import type { Connection, Dialect, ModelsInfo, SchemaInfo } from '../api'
import { api } from '../api'
import { AuditView, DocsView, TopQueriesView } from '../components/DbTools'
import { schemaOf } from '../components/DbIntro'
import { ErDiagram, svgToPng } from '../components/ErDiagram'
import { Button, Card, Empty, ErrorBox, Spinner, Tabs, Tag } from '../components/ui'
import { SchemaView } from './Analyzer'

type Tool = 'schema' | 'audit' | 'slow' | 'er' | 'docs'
const TOOL_TABS: { id: Tool; label: string }[] = [
  { id: 'schema', label: 'Структура' }, { id: 'audit', label: 'Аудит' }, { id: 'slow', label: 'Медленные запросы' },
  { id: 'er', label: 'ER-диаграмма' }, { id: 'docs', label: 'Описание (.docx)' },
]

const presets: Record<string, Record<string, unknown>> = {
  'Демо MySQL (docker)': { dbms: 'mysql', host: '127.0.0.1', port: 3307, database: 'shop', username: 'optimizer_ro', password: 'optimizer_ro' },
  'Демо PostgreSQL (docker)': { dbms: 'postgres', host: '127.0.0.1', port: 5434, database: 'shop', username: 'optimizer_ro', password: 'optimizer_ro' },
}

export function Databases({ connections, onChange, models, onOptimize }: {
  connections: Connection[]; onChange: () => void; models: ModelsInfo | null
  onOptimize: (sql: string, connectionId: number | null) => void
}) {
  const [tool, setTool] = useState<Tool>('schema')
  const erRef = useRef<SVGSVGElement>(null)
  const [form, setForm] = useState<Record<string, unknown>>({ dbms: 'mysql', host: '127.0.0.1', port: 3306, database: '', username: '', password: '', ssl: false, name: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [schema, setSchema] = useState<SchemaInfo | null>(null)
  const [schemaBusy, setSchemaBusy] = useState(false)

  const set = (k: string, v: unknown) => setForm(f => ({ ...f, [k]: v }))

  const submit = async () => {
    setBusy(true); setError(null); setWarnings([])
    try {
      const c = await api.connect({ ...form, name: form.name || undefined })
      setWarnings(c.warnings)
      onChange()
      setSelected(c.id)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  const loadSchema = async (id: number, refresh = false) => {
    setSchemaBusy(true); setError(null)
    try { setSchema(await api.schema(id, refresh)) } catch (e) { setError((e as Error).message); setSchema(null) } finally { setSchemaBusy(false) }
  }

  useEffect(() => { if (selected != null) loadSchema(selected) }, [selected])
  useEffect(() => { if (selected == null && connections.length) setSelected(connections[0].id) }, [connections, selected])

  // переход из консоли: #/databases/er/<id> — сразу ER-диаграмма нужной базы
  useEffect(() => {
    const onHash = () => {
      const [, page, t, id] = window.location.hash.replace('#', '').split('/')
      if (page !== 'databases' || !t) return
      if (TOOL_TABS.some(x => x.id === t)) setTool(t as Tool)
      if (id && !Number.isNaN(Number(id))) setSelected(Number(id))
    }
    onHash()
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  // ER-диаграмма — по одной схеме: у базы с несколькими схемами общая картинка нечитаема
  const [defSchema, setDefSchema] = useState('public')
  const [erSchema, setErSchema] = useState<string | null>(null)
  useEffect(() => {
    if (selected == null) return
    setErSchema(null)
    api.consoleOverview(selected).then(o => { setDefSchema(o.default); setErSchema(o.selected ?? o.schemas[0]?.name ?? null) }).catch(() => {})
  }, [selected])
  const erSchemas = schema ? [...new Set(schema.tables.map(t => schemaOf(t.name, defSchema)))] : []
  const erView: SchemaInfo | null = schema && (erSchemas.length > 1 && erSchema
    ? { ...schema, tables: schema.tables.filter(t => schemaOf(t.name, defSchema) === erSchema) } : schema)

  const remove = async (id: number) => {
    await api.deleteConnection(id)
    if (selected === id) { setSelected(null); setSchema(null) }
    onChange()
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[380px_1fr]">
      <div className="space-y-4">
        <Card title="Новое подключение">
          <div className="mb-3 flex flex-wrap gap-2">
            {Object.entries(presets).map(([name, p]) => <Button key={name} onClick={() => setForm(f => ({ ...f, ...p, name }))}>{name}</Button>)}
          </div>
          <div className="grid grid-cols-[90px_1fr] items-center gap-2 text-[13px]">
            <label className="text-stone">СУБД</label>
            <select value={form.dbms as string} onChange={e => { const d = e.target.value as Dialect; set('dbms', d); set('port', d === 'mysql' ? 3306 : 5432) }}>
              <option value="mysql">MySQL 8+</option><option value="postgres">PostgreSQL 14+</option>
            </select>
            <label className="text-stone">Название</label><input value={form.name as string} onChange={e => set('name', e.target.value)} placeholder="необязательно" />
            <label className="text-stone">Host</label><input value={form.host as string} onChange={e => set('host', e.target.value)} />
            <label className="text-stone">Port</label><input type="number" value={form.port as number} onChange={e => set('port', Number(e.target.value))} />
            <label className="text-stone">Database</label><input value={form.database as string} onChange={e => set('database', e.target.value)} />
            <label className="text-stone">User</label><input value={form.username as string} onChange={e => set('username', e.target.value)} />
            <label className="text-stone">Password</label><input type="password" value={form.password as string} onChange={e => set('password', e.target.value)} />
            <label className="text-stone">SSL</label><input type="checkbox" className="h-4 w-4 justify-self-start" checked={form.ssl as boolean} onChange={e => set('ssl', e.target.checked)} />
          </div>
          <div className="mt-4"><Button variant="primary" onClick={submit} disabled={busy}>{busy && <Spinner />} Проверить и сохранить</Button></div>
          <p className="mt-3 text-[12px] text-stone">
            Все запросы выполняются в READ ONLY транзакции с таймаутом. Рекомендуется пользователь только с правом SELECT. Пароль хранится зашифрованным.
          </p>
          {warnings.map((w, i) => <p key={i} className="mt-2 text-[12px] text-warn">⚠ {w}</p>)}
          {error && <div className="mt-3"><ErrorBox>{error}</ErrorBox></div>}
        </Card>

        <Card title="Подключения">
          {!connections.length ? <Empty>Подключений пока нет. Нажмите «Демо MySQL (docker)» или «Демо PostgreSQL (docker)» над формой — поля заполнятся сами, останется нажать «Проверить и сохранить». Для своей базы введите её адрес и пользователя с правом только на чтение.</Empty> : (
            <ul className="space-y-2">{connections.map(c => (
              <li key={c.id} onClick={() => setSelected(c.id)}
                className={`cursor-pointer rounded-md border p-2.5 text-[13px] ${selected === c.id ? 'border-text bg-panel-2' : 'border-line bg-panel-2 hover:border-muted'}`}>
                <div className="flex items-center gap-2"><span className="font-medium">{c.name}</span><span className="ml-auto" /><Button variant="danger" onClick={() => remove(c.id)}>Удалить</Button></div>
                <div className="mono mt-1 text-[11.5px] text-stone">{c.dbms} {c.server_version} · {c.username}@{c.host}:{c.port}/{c.database}</div>
                <div className="mt-1">{c.read_only_user ? <Tag tone="good">только чтение</Tag> : c.read_only_user === false ? <Tag tone="warn">есть права на запись</Tag> : null}</div>
              </li>
            ))}</ul>
          )}
        </Card>
      </div>

      <div className="min-w-0 space-y-3">
        {selected != null && <Tabs tabs={TOOL_TABS} active={tool} onChange={setTool} />}
        <div hidden={tool !== 'schema'}>
          <Card title="Структура базы" actions={selected != null && <Button variant="ghost" onClick={() => loadSchema(selected, true)}>{schemaBusy && <Spinner />} Обновить</Button>}>
            {schema ? <SchemaView schema={schema} /> : <Empty>{schemaBusy ? 'Загрузка схемы…' : 'Выберите подключение слева — здесь появятся его структура, аудит, медленные запросы, ER-диаграмма и описание базы'}</Empty>}
          </Card>
        </div>
        {selected != null && <>
          <div hidden={tool !== 'audit'}><Card title="Аудит базы"><AuditView key={selected} connectionId={selected} /></Card></div>
          <div hidden={tool !== 'slow'}><Card title="Медленные запросы"><TopQueriesView key={selected} connectionId={selected} onOptimize={sql => onOptimize(sql, selected)} /></Card></div>
          <div hidden={tool !== 'er'}>
            <Card title="Схема связей" actions={schema && <Button variant="ghost" onClick={async () => { if (erRef.current) { const png = await svgToPng(erRef.current); const a = document.createElement('a'); a.href = png; a.download = 'er_diagram.png'; a.click() } }}>PNG</Button>}>
              {erView?.tables.length ? <>
                {erSchemas.length > 1 && (
                  <div className="mb-3 flex flex-wrap items-center gap-1.5">
                    <span className="kicker mr-1 text-stone">схема</span>
                    {erSchemas.map(s => (
                      <button key={s} onClick={() => setErSchema(s)} className={`rounded-md px-2.5 py-1 font-mono text-[12px] ${erSchema === s ? 'bg-obsidian text-white' : 'shadow-[0_0_0_1px_#ebebeb] hover:shadow-[0_0_0_1px_#a8a8a8]'}`}>{s}</button>
                    ))}
                  </div>
                )}
                <p className="mb-3 text-[12.5px] text-stone">Таблицы можно перетаскивать мышью. PK — первичный ключ, FK — внешний; линии идут от внешнего ключа к таблице, на которую он ссылается.</p>
                <div className="max-h-[720px] overflow-auto rounded-md shadow-[0_0_0_1px_#ebebeb]"><ErDiagram ref={erRef} schema={erView} /></div>
              </> : <Empty>{schemaBusy ? 'Загрузка схемы…' : 'В базе нет таблиц'}</Empty>}
            </Card>
          </div>
          <div hidden={tool !== 'docs'}><Card title="Описание базы"><DocsView connectionId={selected} models={models} getErPng={async () => erRef.current && schema?.tables.length ? svgToPng(erRef.current) : null} /></Card></div>
        </>}
      </div>
    </div>
  )
}
