import { forwardRef, useEffect, useMemo, useRef, useState } from 'react'
import type { SchemaInfo, TableInfo } from '../api'

// ER-диаграмма в нотации IDEF1X (чёрно-белая, как принято в документации и отчётах по ГОСТ 2.105):
// имя сущности над блоком; над чертой — первичный ключ, под чертой — остальные атрибуты; внешние ключи — «(FK)»;
// зависимая сущность (первичный ключ включает внешний) — со скруглёнными углами. Связь: сплошная линия —
// идентифицирующая, пунктир — неидентифицирующая; точка у дочерней сущности — «много»,
// ромб у родительской — связь необязательна (внешний ключ допускает NULL).
const BOX_W = 250, NAME_H = 20, ROW = 18, PAD = 6, MAX_ROWS = 16, GAP_X = 90, GAP_Y = 46
const FONT = 'Times New Roman, Times, serif'

type Pos = Record<string, { x: number; y: number }>

const pkCols = (t: TableInfo) => t.indexes.find(i => i.primary)?.columns ?? []
const fkCols = (t: TableInfo) => new Set(t.foreign_keys.flatMap(f => f.columns))

function ordered(t: TableInfo) {
  const pk = pkCols(t)
  const keys = pk.map(n => t.columns.find(c => c.name === n)).filter(Boolean) as TableInfo['columns']
  const rest = t.columns.filter(c => !pk.includes(c.name))
  return { keys, rest: rest.slice(0, Math.max(0, MAX_ROWS - keys.length)), hidden: Math.max(0, rest.length - (MAX_ROWS - keys.length)) }
}

function boxHeight(t: TableInfo) {
  const { keys, rest, hidden } = ordered(t)
  return PAD + Math.max(keys.length, 1) * ROW + PAD + (rest.length + (hidden ? 1 : 0)) * ROW + PAD
}

function initialLayout(tables: TableInfo[]): Pos {
  const degree = new Map(tables.map(t => [t.name, 0]))
  for (const t of tables) for (const f of t.foreign_keys) {
    degree.set(t.name, (degree.get(t.name) ?? 0) + 1)
    degree.set(f.ref_table, (degree.get(f.ref_table) ?? 0) + 1)
  }
  const sorted = [...tables].sort((a, b) => (degree.get(b.name) ?? 0) - (degree.get(a.name) ?? 0) || a.name.localeCompare(b.name))
  const cols = Math.max(1, Math.min(4, Math.ceil(Math.sqrt(tables.length * 1.2))))
  const colY = Array(cols).fill(10)
  const pos: Pos = {}
  sorted.forEach(t => {
    const c = colY.indexOf(Math.min(...colY))
    pos[t.name] = { x: 20 + c * (BOX_W + GAP_X), y: colY[c] }
    colY[c] += NAME_H + boxHeight(t) + GAP_Y
  })
  return pos
}

export const ErDiagram = forwardRef<SVGSVGElement, { schema: SchemaInfo }>(function ErDiagram({ schema }, ref) {
  const tables = schema.tables
  const key = tables.map(t => t.name).join(',')
  const [pos, setPos] = useState<Pos>(() => initialLayout(tables))
  useEffect(() => setPos(initialLayout(tables)), [key])  // eslint-disable-line react-hooks/exhaustive-deps
  const drag = useRef<{ name: string; dx: number; dy: number } | null>(null)
  const byName = useMemo(() => new Map(tables.map(t => [t.name, t])), [tables])
  const find = (n: string) => byName.get(n) ?? tables.find(x => x.name.split('.').pop() === n.split('.').pop())

  const W = Math.max(600, ...tables.map(t => (pos[t.name]?.x ?? 0) + BOX_W + 30))
  const H = Math.max(300, ...tables.map(t => (pos[t.name]?.y ?? 0) + NAME_H + boxHeight(t) + 20))

  // y строки атрибута внутри блока (ключи сверху, остальные под чертой)
  const rowY = (t: TableInfo, col: string) => {
    const { keys, rest } = ordered(t)
    const top = (pos[t.name]?.y ?? 0) + NAME_H
    const ki = keys.findIndex(c => c.name === col)
    if (ki >= 0) return top + PAD + ki * ROW + ROW / 2
    const ri = rest.findIndex(c => c.name === col)
    return top + PAD + Math.max(keys.length, 1) * ROW + PAD + (ri >= 0 ? ri : rest.length) * ROW + ROW / 2
  }

  const links = tables.flatMap(t => t.foreign_keys.map((f, k) => {
    const parent = find(f.ref_table)
    if (!parent || !pos[t.name] || !pos[parent.name]) return null
    const identifying = f.columns.every(c => pkCols(t).includes(c))
    const optional = f.columns.some(c => t.columns.find(x => x.name === c)?.nullable)
    const a = pos[t.name], b = pos[parent.name]
    const y1 = rowY(t, f.columns[0]), y2 = rowY(parent, f.ref_columns[0] ?? pkCols(parent)[0])
    let x1: number, x2: number, c1: number, c2: number
    if (parent === t) { x1 = a.x + BOX_W; x2 = a.x + BOX_W; c1 = x1 + 40; c2 = x2 + 40 }
    else if (b.x > a.x + BOX_W / 2) { x1 = a.x + BOX_W; x2 = b.x; c1 = x1 + 40; c2 = x2 - 40 }
    else if (b.x + BOX_W / 2 < a.x) { x1 = a.x; x2 = b.x + BOX_W; c1 = x1 - 40; c2 = x2 + 40 }
    else { x1 = a.x + BOX_W; x2 = b.x + BOX_W; c1 = x1 + 50; c2 = x2 + 50 }
    const dir = Math.sign(c2 - x2) || 1
    return <g key={`${t.name}-${k}`}>
      <path d={`M${x1},${y1} C${c1},${y1} ${c2},${y2} ${x2},${y2}`} fill="none" stroke="#000" strokeWidth="1.1" strokeDasharray={identifying ? undefined : '6 4'} />
      <circle cx={x1} cy={y1} r="3.6" fill="#000" />
      {optional && <path d={`M${x2},${y2} l${6 * dir},-5 l${6 * dir},5 l${-6 * dir},5 z`} fill="#fff" stroke="#000" strokeWidth="1" />}
    </g>
  }))

  const toSvg = (e: React.PointerEvent) => {
    const svg = ((e.currentTarget as SVGElement).ownerSVGElement ?? e.currentTarget) as SVGSVGElement
    const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY
    return pt.matrixTransform(svg.getScreenCTM()!.inverse())
  }
  const onDown = (e: React.PointerEvent, name: string) => {
    const p = toSvg(e)
    drag.current = { name, dx: p.x - pos[name].x, dy: p.y - pos[name].y }
    ;(e.currentTarget as Element).setPointerCapture(e.pointerId)
  }
  const onMove = (e: React.PointerEvent) => {
    if (!drag.current) return
    const p = toSvg(e), d = drag.current
    setPos(prev => ({ ...prev, [d.name]: { x: Math.max(0, p.x - d.dx), y: Math.max(0, p.y - d.dy) } }))
  }

  const attr = (t: TableInfo, c: TableInfo['columns'][number], y: number) => {
    const fk = fkCols(t).has(c.name)
    const label = `${c.name}${fk ? ' (FK)' : ''}`
    return (
      <g key={c.name}>
        <text x="8" y={y + 13} fontSize="12.5" fill="#000" fontFamily={FONT}>{label.length > 24 ? label.slice(0, 23) + '…' : label}</text>
        <text x={BOX_W - 8} y={y + 13} fontSize="11.5" textAnchor="end" fill="#000" fontFamily={FONT}>{c.type.toLowerCase().replace('character varying', 'varchar').replace(' without time zone', '').slice(0, 16)}</text>
      </g>
    )
  }

  return (
    <svg ref={ref} xmlns="http://www.w3.org/2000/svg" width={W} height={H} viewBox={`0 0 ${W} ${H}`}
      style={{ background: '#ffffff', fontFamily: FONT }} onPointerMove={onMove} onPointerUp={() => { drag.current = null }}>
      <rect width={W} height={H} fill="#ffffff" />
      {links}
      {tables.map(t => {
        const p = pos[t.name]
        if (!p) return null
        const { keys, rest, hidden } = ordered(t)
        const h = boxHeight(t)
        const dependent = t.foreign_keys.some(f => f.columns.every(c => pkCols(t).includes(c)))
        const divider = PAD + Math.max(keys.length, 1) * ROW + PAD / 2
        return (
          <g key={t.name} transform={`translate(${p.x},${p.y})`} style={{ cursor: 'move' }} onPointerDown={e => onDown(e, t.name)}>
            <text x="2" y="14" fontSize="13.5" fontWeight="bold" fill="#000" fontFamily={FONT}>{t.name.split('.').pop()}</text>
            <g transform={`translate(0,${NAME_H})`}>
              <rect width={BOX_W} height={h} rx={dependent ? 10 : 0} fill="#ffffff" stroke="#000" strokeWidth="1.2" />
              <line x1="0" x2={BOX_W} y1={divider} y2={divider} stroke="#000" strokeWidth="1" />
              {keys.map((c, i) => attr(t, c, PAD + i * ROW))}
              {!keys.length && <text x="8" y={PAD + 13} fontSize="11.5" fontStyle="italic" fill="#000" fontFamily={FONT}>нет первичного ключа</text>}
              {rest.map((c, i) => attr(t, c, divider + PAD / 2 + i * ROW))}
              {hidden > 0 && <text x="8" y={divider + PAD / 2 + rest.length * ROW + 13} fontSize="11.5" fontStyle="italic" fill="#000" fontFamily={FONT}>… ещё {hidden}</text>}
            </g>
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
