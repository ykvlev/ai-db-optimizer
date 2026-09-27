import { forwardRef, useEffect, useMemo, useRef, useState } from 'react'
import type { SchemaInfo, TableInfo } from '../api'

// ER-диаграмма по структуре подключённой базы: блоки таблиц (можно перетаскивать) и связи по внешним ключам.
const BOX_W = 230, HEAD = 28, ROW = 19, MAX_ROWS = 14, GAP_X = 90, GAP_Y = 50
const FONT = 'Geist Mono Variable, Consolas, monospace'

type Pos = Record<string, { x: number; y: number }>

function boxHeight(t: TableInfo) {
  return HEAD + Math.min(t.columns.length, MAX_ROWS) * ROW + (t.columns.length > MAX_ROWS ? ROW : 0) + 6
}

// начальная раскладка: самые связанные таблицы — в центре первых рядов, дальше сеткой по столбцам
function initialLayout(tables: TableInfo[]): Pos {
  const degree = new Map(tables.map(t => [t.name, 0]))
  for (const t of tables) for (const f of t.foreign_keys) {
    degree.set(t.name, (degree.get(t.name) ?? 0) + 1)
    degree.set(f.ref_table, (degree.get(f.ref_table) ?? 0) + 1)
  }
  const sorted = [...tables].sort((a, b) => (degree.get(b.name) ?? 0) - (degree.get(a.name) ?? 0) || a.name.localeCompare(b.name))
  const cols = Math.max(1, Math.ceil(Math.sqrt(tables.length * 1.3)))
  const colY = Array(cols).fill(20)
  const pos: Pos = {}
  sorted.forEach(t => {
    const c = colY.indexOf(Math.min(...colY))  // в самый короткий столбец
    pos[t.name] = { x: 20 + c * (BOX_W + GAP_X), y: colY[c] }
    colY[c] += boxHeight(t) + GAP_Y
  })
  return pos
}

function isKey(t: TableInfo, col: string) {
  if (t.indexes.some(i => i.primary && i.columns.includes(col))) return 'PK'
  if (t.foreign_keys.some(f => f.columns.includes(col))) return 'FK'
  return ''
}

export const ErDiagram = forwardRef<SVGSVGElement, { schema: SchemaInfo }>(function ErDiagram({ schema }, ref) {
  const tables = schema.tables
  const key = tables.map(t => t.name).join(',')
  const [pos, setPos] = useState<Pos>(() => initialLayout(tables))
  useEffect(() => setPos(initialLayout(tables)), [key])  // eslint-disable-line react-hooks/exhaustive-deps
  const drag = useRef<{ name: string; dx: number; dy: number } | null>(null)
  const byName = useMemo(() => new Map(tables.map(t => [t.name, t])), [tables])

  const W = Math.max(600, ...tables.map(t => (pos[t.name]?.x ?? 0) + BOX_W + 20))
  const H = Math.max(300, ...tables.map(t => (pos[t.name]?.y ?? 0) + boxHeight(t) + 20))

  const rowY = (t: TableInfo, col: string) => {
    const i = t.columns.findIndex(c => c.name === col)
    return (pos[t.name]?.y ?? 0) + HEAD + (i >= 0 && i < MAX_ROWS ? i : Math.min(t.columns.length, MAX_ROWS)) * ROW + ROW / 2 + 3
  }

  const links = tables.flatMap(t => t.foreign_keys.map((f, k) => {
    const ref = byName.get(f.ref_table) ?? tables.find(x => x.name.split('.').pop() === f.ref_table)
    if (!ref || !pos[t.name] || !pos[ref.name]) return null
    const a = pos[t.name], b = pos[ref.name]
    const y1 = rowY(t, f.columns[0]), y2 = rowY(ref, f.ref_columns[0])
    let x1: number, x2: number, c1: number, c2: number
    if (ref === t) { x1 = a.x + BOX_W; x2 = a.x + BOX_W; c1 = x1 + 40; c2 = x2 + 40 }
    else if (b.x > a.x + BOX_W / 2) { x1 = a.x + BOX_W; x2 = b.x; c1 = x1 + 40; c2 = x2 - 40 }
    else if (b.x + BOX_W / 2 < a.x) { x1 = a.x; x2 = b.x + BOX_W; c1 = x1 - 40; c2 = x2 + 40 }
    else { x1 = a.x + BOX_W; x2 = b.x + BOX_W; c1 = x1 + 50; c2 = x2 + 50 }
    return <g key={`${t.name}-${k}`}>
      <path d={`M${x1},${y1} C${c1},${y1} ${c2},${y2} ${x2},${y2}`} fill="none" stroke="#8f8f8f" strokeWidth="1.2" />
      <circle cx={x2} cy={y2} r="3" fill="#171717" />
    </g>
  }))

  const onDown = (e: React.PointerEvent, name: string) => {
    const svg = (e.currentTarget as SVGElement).ownerSVGElement!
    const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY
    const p = pt.matrixTransform(svg.getScreenCTM()!.inverse())
    drag.current = { name, dx: p.x - pos[name].x, dy: p.y - pos[name].y }
    ;(e.currentTarget as Element).setPointerCapture(e.pointerId)
  }
  const onMove = (e: React.PointerEvent) => {
    if (!drag.current) return
    const svg = (e.currentTarget as SVGElement).ownerSVGElement ?? (e.currentTarget as SVGSVGElement)
    const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY
    const p = pt.matrixTransform(svg.getScreenCTM()!.inverse())
    const d = drag.current
    setPos(prev => ({ ...prev, [d.name]: { x: Math.max(0, p.x - d.dx), y: Math.max(0, p.y - d.dy) } }))
  }

  return (
    <svg ref={ref} xmlns="http://www.w3.org/2000/svg" width={W} height={H} viewBox={`0 0 ${W} ${H}`}
      style={{ background: '#ffffff', fontFamily: FONT }} onPointerMove={onMove} onPointerUp={() => { drag.current = null }}>
      <rect width={W} height={H} fill="#ffffff" />
      {links}
      {tables.map(t => {
        const p = pos[t.name]
        if (!p) return null
        const h = boxHeight(t)
        return (
          <g key={t.name} transform={`translate(${p.x},${p.y})`} style={{ cursor: 'move' }} onPointerDown={e => onDown(e, t.name)}>
            <rect width={BOX_W} height={h} rx="6" fill="#ffffff" stroke="#d6d6d6" />
            <rect width={BOX_W} height={HEAD} rx="6" fill="#171717" />
            <rect y={HEAD - 6} width={BOX_W} height="6" fill="#171717" />
            <text x="10" y="18" fontSize="12.5" fontWeight="600" fill="#ffffff" fontFamily={FONT}>{(n => n.length > 26 ? n.slice(0, 25) + '…' : n)(t.name.split('.').pop()!)}</text>
            {t.row_count != null && <text x={BOX_W - 10} y="18" fontSize="10" textAnchor="end" fill="#a8a8a8" fontFamily={FONT}>{t.row_count.toLocaleString('ru-RU')}</text>}
            {t.columns.slice(0, MAX_ROWS).map((c, i) => {
              const k = isKey(t, c.name)
              return (
                <g key={c.name} transform={`translate(0,${HEAD + i * ROW + 3})`}>
                  <text x="10" y="13" fontSize="10" fontWeight="600" fill={k === 'PK' ? '#171717' : '#297a3a'} fontFamily={FONT}>{k}</text>
                  <text x="32" y="13" fontSize="11.5" fill="#171717" fontFamily={FONT}>{c.name.length > 17 ? c.name.slice(0, 16) + '…' : c.name}</text>
                  <text x={BOX_W - 10} y="13" fontSize="10" textAnchor="end" fill="#8f8f8f" fontFamily={FONT}>{c.type.toLowerCase().replace('character varying', 'varchar').slice(0, 14)}</text>
                </g>
              )
            })}
            {t.columns.length > MAX_ROWS && <text x="32" y={HEAD + MAX_ROWS * ROW + 16} fontSize="10.5" fill="#8f8f8f" fontFamily={FONT}>ещё {t.columns.length - MAX_ROWS} столбцов</text>}
          </g>
        )
      })}
    </svg>
  )
})

// SVG → PNG (data URL) для скачивания и вставки в документ Word
export async function svgToPng(svg: SVGSVGElement, scale = 2): Promise<string> {
  const xml = new XMLSerializer().serializeToString(svg)
  const img = new Image()
  img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(xml)
  await img.decode()
  const canvas = document.createElement('canvas')
  canvas.width = svg.width.baseVal.value * scale
  canvas.height = svg.height.baseVal.value * scale
  const ctx = canvas.getContext('2d')!
  ctx.scale(scale, scale)
  ctx.drawImage(img, 0, 0)
  return canvas.toDataURL('image/png')
}
