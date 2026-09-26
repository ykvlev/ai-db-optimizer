export type Dialect = 'mysql' | 'postgres'
export type Severity = 'info' | 'low' | 'medium' | 'high' | 'critical'

export interface Issue {
  code: string
  severity: Severity
  title: string
  description: string
  source: 'rule' | 'plan' | 'ai'
  fragment?: string | null
  suggestion?: string | null
  table?: string | null
}

export interface JoinInfo { kind: string; table: string; alias?: string | null; condition?: string | null }

export interface ParsedQuery {
  query_type: string
  tables: string[]
  columns: string[]
  select_star: boolean
  joins: JoinInfo[]
  where_conditions: string[]
  group_by: string[]
  order_by: string[]
  having?: string | null
  subqueries: number
  correlated_subqueries: number
  cte: string[]
  aggregations: string[]
  functions: string[]
  limit?: string | null
  offset?: string | null
  distinct: boolean
  union: boolean
  node_count: number
  normalized_sql: string
}

export interface ColumnInfo { name: string; type: string; nullable: boolean }
export interface IndexInfo { name: string; columns: string[]; unique: boolean; primary: boolean }
export interface ForeignKeyInfo { name?: string | null; columns: string[]; ref_table: string; ref_columns: string[] }
export interface TableInfo {
  name: string
  row_count?: number | null
  size_bytes?: number | null
  columns: ColumnInfo[]
  indexes: IndexInfo[]
  foreign_keys: ForeignKeyInfo[]
}
export interface SchemaInfo { tables: TableInfo[]; source: 'ddl' | 'live' | 'none' }

export interface SafetyVerdict { allowed: boolean; statement_type?: string | null; reasons: string[]; warnings: string[] }

export interface PlanNode {
  type: string
  table?: string | null
  index?: string | null
  access?: string | null
  rows?: number | null
  actual_rows?: number | null
  cost?: number | null
  time_ms?: number | null
  filter?: string | null
  extra: string[]
  children: PlanNode[]
}

export interface PlanSummary {
  dbms: Dialect
  total_cost?: number | null
  root?: PlanNode | null
  full_scans: string[]
  index_accesses: string[]
  uses_filesort: boolean
  uses_temporary: boolean
  estimated_rows_examined?: number | null
  issues: Issue[]
  raw: unknown
  analyzed: boolean
}

export interface AnalyzeResponse {
  run_id?: number | null
  parsed?: ParsedQuery | null
  safety: SafetyVerdict
  schema_info: SchemaInfo
  issues: Issue[]
  rule_rewrite?: string | null
  rule_rewrite_notes: string[]
  plan?: PlanSummary | null
  parse_error?: string | null
}

// передача пары запросов из анализатора на страницу сравнения
export interface CompareDraft { original: string; optimized: string; connectionId: number | null; source: string; nonce: number }

export interface ScriptStatement {
  index: number
  title?: string | null
  start_line: number
  sql: string
  analysis: AnalyzeResponse
}

export interface ScriptAnalyzeResponse { dbms: Dialect; statements: ScriptStatement[] }

export interface AIResponse {
  summary: string
  issues: { type: string; severity: string; description: string }[]
  optimized_query?: string | null
  recommended_indexes: { table: string; columns: string[]; sql?: string | null; reason?: string | null }[]
  explanation: string[]
  plain_explanation?: string | null
  confidence?: number | null
}

export interface BenchmarkStats {
  runs: number
  warmup: number
  times_ms: number[]
  mean_ms: number
  median_ms: number
  min_ms: number
  max_ms: number
  stdev_ms: number
  rows_returned: number
  rows_examined?: number | null
  disk_reads?: number | null
  buffer_hits?: number | null
}

export interface EquivalenceResult {
  status: 'equivalent' | 'different' | 'error' | 'skipped'
  rows_original?: number | null
  rows_optimized?: number | null
  columns_match?: boolean | null
  checksum_original?: string | null
  checksum_optimized?: string | null
  order_sensitive: boolean
  order_match?: boolean | null
  details: string[]
  sample_only_in_original: unknown[][]
  sample_only_in_optimized: unknown[][]
}

export interface ScoreResult {
  score: number | null
  components: { name: string; value: number; weight: number; detail: string }[]
  note?: string | null
}

export interface Comparison {
  original_sql: string
  optimized_sql: string
  equivalence: EquivalenceResult
  benchmark_original?: BenchmarkStats | null
  benchmark_optimized?: BenchmarkStats | null
  plan_original?: PlanSummary | null
  plan_optimized?: PlanSummary | null
  speedup?: number | null
  improvement_pct?: number | null
  plan_changes: string[]
  score?: ScoreResult | null
  errors: string[]
}

export interface ConfidenceResult {
  confidence: number | null
  factors: { name: string; value: number; weight: number; detail: string }[]
}

export interface OptimizeResponse {
  run_id?: number | null
  analysis: AnalyzeResponse
  ai?: AIResponse | null
  ai_error?: string | null
  llm?: { provider: string; model: string; prompt_version: string; latency_ms: number; prompt_tokens?: number | null; completion_tokens?: number | null } | null
  optimized_query?: string | null
  optimized_safety?: SafetyVerdict | null
  error_types: string[]
  comparison?: Comparison | null
  confidence?: ConfidenceResult | null
  verdict: 'accepted' | 'rejected' | 'unverified' | 'no_change' | 'failed'
  verdict_reason: string
}

export interface Connection {
  id: number
  name: string
  dbms: Dialect
  host: string
  port: number
  database: string
  username: string
  ssl: boolean
  server_version?: string | null
  read_only_user?: boolean | null
  warnings: string[]
}

export interface ModelsInfo { models: string[]; default: string | null; prompts: string[]; providers: string[]; baseline: string }

export interface Examples {
  ddl: Record<Dialect, string>
  queries: { id: string; title: string; mysql: string; postgres: string }[]
}

export interface RunRow {
  id: number
  kind: string
  started_at: string
  dbms: Dialect
  sql: string
  model?: string | null
  verdict?: string | null
  speedup?: number | null
  score?: number | null
  equivalent?: boolean | null
  error_types?: string[] | null
  issues: number
}

export interface Stats {
  queries_analyzed: number
  runs_total: number
  optimize_runs: number
  verified_runs: number
  successful_optimizations: number
  verdicts: Record<string, number>
  median_speedup: number | null
  mean_speedup: number | null
  databases: number
  ai_models_used: number
  ai_models_configured: number
  error_types: Record<string, number>
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`
    try {
      const data = await res.json()
      msg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch { /* ответ не JSON */ }
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

export const api = {
  models: () => request<ModelsInfo>('GET', '/api/models'),
  examples: () => request<Examples>('GET', '/api/examples'),
  stats: () => request<Stats>('GET', '/api/stats'),
  analyzeScript: (b: { sql: string; dbms: Dialect; ddl?: string; connection_id?: number | null }) =>
    request<ScriptAnalyzeResponse>('POST', '/api/query/analyze-script', b),
  analyze: (b: { sql: string; dbms: Dialect; ddl?: string; connection_id?: number | null }) =>
    request<AnalyzeResponse>('POST', '/api/query/analyze', b),
  optimize: (b: { sql: string; dbms: Dialect; ddl?: string; connection_id?: number | null; model?: string | null; prompt_version?: string | null; runs?: number }) =>
    request<OptimizeResponse>('POST', '/api/query/optimize', b),
  compare: (b: { original_sql: string; optimized_sql: string; connection_id: number; runs?: number; warmup?: number }) =>
    request<Comparison>('POST', '/api/query/compare', b),
  connections: () => request<Connection[]>('GET', '/api/database/connections'),
  connect: (b: Record<string, unknown>) => request<Connection>('POST', '/api/database/connect', b),
  deleteConnection: (id: number) => request<unknown>('DELETE', `/api/database/connections/${id}`),
  schema: (id: number, refresh = false) => request<SchemaInfo>('GET', `/api/database/${id}/schema?refresh=${refresh}`),
  runs: (limit = 100) => request<RunRow[]>('GET', `/api/runs?limit=${limit}`),
  run: (id: number) => request<{ id: number; kind: string; sql: string; dbms: Dialect; started_at: string; model?: string; prompt_version?: string; app_version: string; dbms_version?: string; result: unknown }>('GET', `/api/runs/${id}`),
}

// ---------------------------------------------------------------- Research Mode
export interface DatasetInfo {
  id: number
  name: string
  version: string
  dbms: Dialect
  description?: string | null
  database_seed?: string | null
  builtin: boolean
  size: number
  categories: string[]
  queries?: { id: number; key: string; title: string; category: string; sql: string }[]
}

export type Outcome = 'improved' | 'unchanged' | 'worse' | 'invalid' | 'error'

export interface ExperimentMeta {
  id: number
  name: string
  dataset_id: number
  dataset_name: string
  dataset_version: string
  n_queries: number
  connection_id: number | null
  models: string[]
  prompt_version: string
  prompt_sha256?: string | null
  runs: number
  warmup: number
  model_parameters?: Record<string, unknown> | null
  status: 'pending' | 'running' | 'done' | 'cancelled' | 'failed' | 'interrupted'
  running: boolean
  progress_done: number
  progress_total: number
  current_item?: string | null
  app_version: string
  dbms?: Dialect | null
  dbms_version?: string | null
  database_seed?: string | null
  error?: string | null
  created_at: string
  started_at?: string | null
  finished_at?: string | null
}

export interface ModelSummary {
  n: number
  outcomes: Record<Outcome, number>
  outcomes_pct: Record<Outcome, number>
  proposed: number
  proposed_pct: number
  correct_sql_pct: number | null
  equivalent_pct: number | null
  faster_pct: number | null
  median_speedup: number | null
  median_speedup_ci95: [number, number] | null
  mean_speedup: number | null
  geomean_speedup: number | null
  median_speedup_improved: number | null
  max_speedup: number | null
  regressions: number
  hallucinations: number
  error_types: Record<string, number>
  avg_latency_ms: number | null
  prompt_tokens: number
  completion_tokens: number
}

export interface ExperimentResultRow {
  id: number
  key: string
  title: string
  category: string
  model: string
  run_id?: number | null
  outcome: Outcome
  verdict?: string | null
  proposed: boolean
  executed: boolean
  equivalent?: boolean | null
  speedup?: number | null
  time_before_ms?: number | null
  time_after_ms?: number | null
  optimization_score?: number | null
  confidence?: number | null
  error_types: string[]
  latency_ms?: number | null
  message?: string | null
}

export interface ExperimentDetail {
  meta: ExperimentMeta
  summary: { models: Record<string, ModelSummary>; categories: Record<string, Record<string, { n: number; improved: number; invalid: number; worse: number }>> }
  results: ExperimentResultRow[]
  conclusions: string[]
}

export const research = {
  datasets: () => request<DatasetInfo[]>('GET', '/api/datasets'),
  dataset: (id: number) => request<DatasetInfo>('GET', `/api/datasets/${id}`),
  createDataset: (b: { name: string; version: string; dbms: Dialect; description?: string; queries: { sql: string; title?: string; category?: string }[] }) =>
    request<DatasetInfo>('POST', '/api/datasets', b),
  experiments: () => request<ExperimentMeta[]>('GET', '/api/experiments'),
  experiment: (id: number) => request<ExperimentDetail>('GET', `/api/experiments/${id}`),
  create: (b: { name: string; dataset_id: number; connection_id: number; models: string[]; prompt_version?: string | null; runs: number; warmup: number }) =>
    request<{ id: number }>('POST', '/api/experiments', b),
  cancel: (id: number) => request<unknown>('POST', `/api/experiments/${id}/cancel`),
  resume: (id: number) => request<unknown>('POST', `/api/experiments/${id}/resume`),
  remove: (id: number) => request<unknown>('DELETE', `/api/experiments/${id}`),
}
