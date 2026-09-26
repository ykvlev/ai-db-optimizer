"""Доменные модели (Pydantic): то, чем обмениваются модули и что отдаёт API."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

Dialect = Literal["mysql", "postgres"]
Severity = Literal["info", "low", "medium", "high", "critical"]


# ---------------------------------------------------------------- SQL Parser
class JoinInfo(BaseModel):
    kind: str  # INNER / LEFT / RIGHT / FULL / CROSS
    table: str
    alias: str | None = None
    condition: str | None = None


class ParsedQuery(BaseModel):
    query_type: str
    tables: list[str] = []
    table_aliases: dict[str, str] = {}  # alias -> table
    columns: list[str] = []
    select_star: bool = False
    joins: list[JoinInfo] = []
    where_conditions: list[str] = []
    group_by: list[str] = []
    order_by: list[str] = []
    having: str | None = None
    subqueries: int = 0
    correlated_subqueries: int = 0
    cte: list[str] = []
    aggregations: list[str] = []
    functions: list[str] = []
    limit: str | None = None
    offset: str | None = None
    distinct: bool = False
    union: bool = False
    node_count: int = 0
    normalized_sql: str = ""


# ---------------------------------------------------------------- Schema
class ColumnInfo(BaseModel):
    name: str
    type: str
    nullable: bool = True


class IndexInfo(BaseModel):
    name: str
    columns: list[str]
    unique: bool = False
    primary: bool = False


class ForeignKeyInfo(BaseModel):
    name: str | None = None
    columns: list[str]
    ref_table: str
    ref_columns: list[str]


class TableInfo(BaseModel):
    name: str
    row_count: int | None = None
    size_bytes: int | None = None
    columns: list[ColumnInfo] = []
    indexes: list[IndexInfo] = []
    foreign_keys: list[ForeignKeyInfo] = []

    def column(self, name: str) -> ColumnInfo | None:
        name = name.lower()
        return next((c for c in self.columns if c.name.lower() == name), None)


class SchemaInfo(BaseModel):
    tables: list[TableInfo] = []
    source: Literal["ddl", "live", "none"] = "none"

    def table(self, name: str) -> TableInfo | None:
        """Поиск по полному имени (schema.table), затем по короткому, если оно однозначно."""
        full = name.lower()
        exact = next((t for t in self.tables if t.name.lower() == full), None)
        if exact is not None:
            return exact
        short = full.split(".")[-1]
        matches = [t for t in self.tables if t.name.lower().split(".")[-1] == short]
        if len(matches) == 1:
            return matches[0]
        # при неоднозначности без схемы — таблица схемы по умолчанию (имя без префикса)
        return next((t for t in matches if "." not in t.name), None) if "." not in full else None


# ---------------------------------------------------------------- Issues
class Issue(BaseModel):
    code: str
    severity: Severity
    title: str
    description: str
    source: Literal["rule", "plan", "ai"] = "rule"
    fragment: str | None = None
    suggestion: str | None = None
    table: str | None = None


# ---------------------------------------------------------------- Safety
class SafetyVerdict(BaseModel):
    allowed: bool
    statement_type: str | None = None
    reasons: list[str] = []
    warnings: list[str] = []


# ---------------------------------------------------------------- Execution plan
class PlanNode(BaseModel):
    type: str
    table: str | None = None
    index: str | None = None
    access: str | None = None
    rows: float | None = None
    actual_rows: float | None = None
    cost: float | None = None
    time_ms: float | None = None
    filter: str | None = None
    extra: list[str] = []
    children: list["PlanNode"] = []


class PlanSummary(BaseModel):
    dbms: Dialect
    total_cost: float | None = None
    root: PlanNode | None = None
    full_scans: list[str] = []
    index_accesses: list[str] = []
    uses_filesort: bool = False
    uses_temporary: bool = False
    estimated_rows_examined: float | None = None
    issues: list[Issue] = []
    raw: Any = None
    analyzed: bool = False  # True, если план получен с фактическим выполнением (ANALYZE)


# ---------------------------------------------------------------- AI
class AIIssue(BaseModel):
    type: str
    severity: str = "medium"
    description: str


class AIIndexRecommendation(BaseModel):
    table: str
    columns: list[str]
    sql: str | None = None
    reason: str | None = None


class AIResponse(BaseModel):
    summary: str = ""
    issues: list[AIIssue] = []
    optimized_query: str | None = None
    recommended_indexes: list[AIIndexRecommendation] = []
    explanation: list[str] = []
    plain_explanation: str | None = None
    confidence: float | None = None


class ErrorType(str, Enum):
    SYNTAX_ERROR = "SYNTAX_ERROR"
    SEMANTIC_ERROR = "SEMANTIC_ERROR"
    WRONG_COLUMN = "WRONG_COLUMN"
    WRONG_TABLE = "WRONG_TABLE"
    RESULT_CHANGED = "RESULT_CHANGED"
    PERFORMANCE_REGRESSION = "PERFORMANCE_REGRESSION"
    UNSUPPORTED_SYNTAX = "UNSUPPORTED_SYNTAX"
    DANGEROUS_QUERY = "DANGEROUS_QUERY"
    INDEX_HALLUCINATION = "INDEX_HALLUCINATION"
    SCHEMA_HALLUCINATION = "SCHEMA_HALLUCINATION"
    INVALID_RESPONSE = "INVALID_RESPONSE"


class LLMCallInfo(BaseModel):
    provider: str
    model: str
    prompt_version: str
    latency_ms: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


# ---------------------------------------------------------------- Benchmark / equivalence
class BenchmarkStats(BaseModel):
    runs: int
    warmup: int
    times_ms: list[float]
    mean_ms: float
    median_ms: float
    min_ms: float
    max_ms: float
    stdev_ms: float
    rows_returned: int
    rows_examined: float | None = None  # MySQL: Handler_read_*; PG: из EXPLAIN ANALYZE
    disk_reads: float | None = None
    buffer_hits: float | None = None


class EquivalenceResult(BaseModel):
    status: Literal["equivalent", "different", "error", "skipped"]
    rows_original: int | None = None
    rows_optimized: int | None = None
    columns_match: bool | None = None
    checksum_original: str | None = None
    checksum_optimized: str | None = None
    order_sensitive: bool = False
    order_match: bool | None = None
    details: list[str] = []
    sample_only_in_original: list[list[Any]] = []
    sample_only_in_optimized: list[list[Any]] = []


class ScoreComponent(BaseModel):
    name: str
    value: float  # 0..100
    weight: float
    detail: str


class ScoreResult(BaseModel):
    score: float | None
    components: list[ScoreComponent] = []
    note: str | None = None


class ConfidenceFactor(BaseModel):
    name: str
    value: float  # 0..1
    weight: float
    detail: str


class ConfidenceResult(BaseModel):
    confidence: float | None
    factors: list[ConfidenceFactor] = []


class Comparison(BaseModel):
    original_sql: str
    optimized_sql: str
    equivalence: EquivalenceResult
    benchmark_original: BenchmarkStats | None = None
    benchmark_optimized: BenchmarkStats | None = None
    plan_original: PlanSummary | None = None
    plan_optimized: PlanSummary | None = None
    speedup: float | None = None
    improvement_pct: float | None = None
    plan_changes: list[str] = []
    score: ScoreResult | None = None
    errors: list[str] = []


# ---------------------------------------------------------------- API payloads
class AnalyzeRequest(BaseModel):
    sql: str
    dbms: Dialect = "mysql"
    ddl: str | None = None
    connection_id: int | None = None
    with_plan: bool = True


class AnalyzeResponse(BaseModel):
    run_id: int | None = None
    parsed: ParsedQuery | None = None
    safety: SafetyVerdict
    schema_info: SchemaInfo = Field(default_factory=SchemaInfo)
    issues: list[Issue] = []
    rule_rewrite: str | None = None
    rule_rewrite_notes: list[str] = []
    plan: PlanSummary | None = None
    parse_error: str | None = None


class OptimizeRequest(AnalyzeRequest):
    model: str | None = None
    prompt_version: str | None = None
    verify: bool = True  # проверка эквивалентности + бенчмарк (нужно подключение)
    runs: int | None = None
    warmup: int | None = None


class OptimizeResponse(BaseModel):
    run_id: int | None = None
    analysis: AnalyzeResponse
    ai: AIResponse | None = None
    ai_error: str | None = None
    llm: LLMCallInfo | None = None
    optimized_query: str | None = None
    optimized_safety: SafetyVerdict | None = None
    error_types: list[ErrorType] = []
    comparison: Comparison | None = None
    confidence: ConfidenceResult | None = None
    verdict: Literal["accepted", "rejected", "unverified", "no_change", "failed"]
    verdict_reason: str


class CompareRequest(BaseModel):
    original_sql: str
    optimized_sql: str
    connection_id: int
    runs: int | None = None
    warmup: int | None = None


class ConnectionCreate(BaseModel):
    name: str | None = None
    dbms: Dialect
    host: str = "127.0.0.1"
    port: int | None = None
    database: str
    username: str
    password: str = ""
    ssl: bool = False


class ConnectionOut(BaseModel):
    id: int
    name: str
    dbms: Dialect
    host: str
    port: int
    database: str
    username: str
    ssl: bool
    server_version: str | None = None
    read_only_user: bool | None = None
    warnings: list[str] = []


class ExplainRequest(BaseModel):
    sql: str
    connection_id: int
    analyze: bool = False


class BenchmarkRequest(BaseModel):
    sql: str
    connection_id: int
    runs: int | None = None
    warmup: int | None = None


class ScriptStatement(BaseModel):
    index: int
    title: str | None = None
    start_line: int
    sql: str
    analysis: AnalyzeResponse


class ScriptAnalyzeResponse(BaseModel):
    dbms: Dialect
    statements: list[ScriptStatement]
