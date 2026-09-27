import type { Stats } from '../api'
import { Card, Empty, Stat, Tag } from '../components/ui'

const verdictNames: Record<string, string> = {
  accepted: 'Принято', rejected: 'Отклонено', unverified: 'Не проверено', no_change: 'Без изменений', failed: 'Ошибка',
}

export function Dashboard({ stats, onNavigate }: { stats: Stats | null; onNavigate: (p: string) => void }) {
  if (!stats) return <Empty>Загрузка…</Empty>
  const total = Object.values(stats.verdicts).reduce((a, b) => a + b, 0)
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 2xl:grid-cols-6">
        <Stat label="Проанализировано запросов" value={stats.queries_analyzed} hint={`${stats.runs_total} запусков`} />
        <Stat label="Успешных оптимизаций" value={stats.successful_optimizations} hint="эквивалентны и быстрее ≥ 5%" />
        <Stat label="Медианное ускорение" value={stats.median_speedup != null ? `${stats.median_speedup.toFixed(2)}x` : '—'}
          hint={stats.median_speedup != null ? `среднее ${stats.mean_speedup!.toFixed(2)}x` : 'только измеренные на БД'} />
        <Stat label="Проверено на БД" value={stats.verified_runs} hint="с проверкой эквивалентности" />
        <Stat label="Базы данных" value={stats.databases} />
        <Stat label="AI-модели" value={stats.ai_models_configured} hint={`использовано: ${stats.ai_models_used}`} />
      </div>

      {stats.runs_total === 0 && (
        <Empty>
          Пока нет ни одного запуска. Откройте <button className="text-obsidian" onClick={() => onNavigate('analyzer')}>SQL Analyzer</button>, вставьте запрос и нажмите «Анализировать».
          Все показатели на этой странице рассчитываются только по фактически выполненным запускам.
        </Empty>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Результаты AI-оптимизации">
          {total === 0 ? <Empty>Нет запусков AI-оптимизации</Empty> : (
            <div className="space-y-2">
              {Object.entries(stats.verdicts).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                <div key={k}>
                  <div className="flex justify-between text-[13px]"><span>{verdictNames[k] ?? k}</span><span className="tabular-nums">{v} · {Math.round((v / total) * 100)}%</span></div>
                  <div className="mt-0.5 h-1.5 rounded bg-line"><div className={`h-1.5 rounded ${k === 'accepted' ? 'bg-good' : k === 'rejected' || k === 'failed' ? 'bg-bad' : 'bg-muted'}`} style={{ width: `${(v / total) * 100}%` }} /></div>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card title="Классификация ошибок модели">
          {Object.keys(stats.error_types).length === 0 ? <Empty>Ошибок не зафиксировано</Empty> : (
            <div className="flex flex-wrap gap-2">
              {Object.entries(stats.error_types).sort((a, b) => b[1] - a[1]).map(([k, v]) => <Tag key={k} tone="bad">{k}: {v}</Tag>)}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
