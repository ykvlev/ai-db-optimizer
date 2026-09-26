"""Главный алгоритм (ТЗ, п. 39):

SQL → Parse → Schema → Execution Plan → Rule-based Analysis → AI Context → LLM → Safety → Syntax/Schema
validation → Result Equivalence → Benchmark → Compare Plans → Score → Save.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from app import __version__
from app.config import get_settings
from app.db import (AIRecommendation, AnalysisRun, Benchmark, DatabaseConnection, ExecutionPlan, IndexRecommendation,
                    Query, QueryVersion, SessionLocal, decrypt, utcnow)
from app.models import (AnalyzeRequest, AnalyzeResponse, ScriptAnalyzeResponse, ScriptStatement, Comparison, Dialect, EquivalenceResult, ErrorType,
                        LLMCallInfo, OptimizeRequest, OptimizeResponse, PlanSummary, SchemaInfo)
from app.services import benchmark as bench
from app.services import explain, rewriter, rules, safety, scoring
from app.services.ai import optimizer as ai
from app.services.ai.providers import LLMError
from app.services.connectors import ConnectionConfig, Connector, DBError, make_connector
from app.services.schema_ddl import parse_ddl
from app.services.sql_parser import SQLParseError, parse, split_script

SCHEMA_CACHE_TTL_S = 300
_schema_cache: dict[int, tuple[float, SchemaInfo, str]] = {}


class PipelineError(Exception):
    pass


# ---------------------------------------------------------------- подключения
def connection_config(connection_id: int) -> tuple[DatabaseConnection, ConnectionConfig]:
    with SessionLocal() as s:
        c = s.get(DatabaseConnection, connection_id)
        if c is None:
            raise PipelineError(f"Подключение {connection_id} не найдено")
        return c, ConnectionConfig(dbms=c.dbms, host=c.host, port=c.port, database=c.database, username=c.username,
                                   password=decrypt(c.password_enc), ssl=c.ssl)


def open_connector(connection_id: int) -> tuple[DatabaseConnection, Connector]:
    rec, cfg = connection_config(connection_id)
    return rec, make_connector(cfg, get_settings().query_timeout_ms)


def live_schema(conn: Connector, connection_id: int, refresh: bool = False) -> tuple[SchemaInfo, str]:
    cached = _schema_cache.get(connection_id)
    if cached and not refresh and time.time() - cached[0] < SCHEMA_CACHE_TTL_S:
        return cached[1], cached[2]
    schema, version = conn.introspect(), conn.server_version()
    _schema_cache[connection_id] = (time.time(), schema, version)
    return schema, version


def invalidate_schema(connection_id: int) -> None:
    _schema_cache.pop(connection_id, None)


# ---------------------------------------------------------------- классификация ошибок СУБД
_DB_ERRORS = {
    "1064": ErrorType.SYNTAX_ERROR, "1146": ErrorType.WRONG_TABLE, "1054": ErrorType.WRONG_COLUMN,
    "1235": ErrorType.UNSUPPORTED_SYNTAX, "1176": ErrorType.INDEX_HALLUCINATION,
    "3024": ErrorType.PERFORMANCE_REGRESSION,
    "42601": ErrorType.SYNTAX_ERROR, "42P01": ErrorType.WRONG_TABLE, "42703": ErrorType.WRONG_COLUMN,
    "0A000": ErrorType.UNSUPPORTED_SYNTAX, "57014": ErrorType.PERFORMANCE_REGRESSION,
}


def classify_db_error(e: DBError) -> ErrorType:
    return _DB_ERRORS.get(str(e.code), ErrorType.SEMANTIC_ERROR)


# ---------------------------------------------------------------- анализ
@dataclass
class _AnalysisState:
    response: AnalyzeResponse
    parsed: object | None
    version: str | None


def _analyze(req: AnalyzeRequest, conn: Connector | None, connection_id: int | None) -> _AnalysisState:
    verdict = safety.check(req.sql, req.dbms)
    resp = AnalyzeResponse(safety=verdict)
    parsed = None
    try:
        parsed = parse(req.sql, req.dbms)
        resp.parsed = parsed.info
    except SQLParseError as e:
        resp.parse_error = str(e)

    version = None
    if conn is not None and connection_id is not None:
        resp.schema_info, version = live_schema(conn, connection_id)
    elif req.ddl and req.ddl.strip():
        resp.schema_info, warnings = parse_ddl(req.ddl, req.dbms)
        resp.safety.warnings += warnings

    if parsed is not None:
        resp.issues = rules.run_rules(parsed, resp.schema_info, req.dbms)
        resp.rule_rewrite, resp.rule_rewrite_notes = rewriter.rewrite(parsed)

    if conn is not None and verdict.allowed and req.with_plan:
        try:
            resp.plan = explain.analyze(req.dbms, conn.explain(req.sql, analyze=False))
            resp.issues += resp.plan.issues
        except DBError as e:
            resp.safety.warnings.append(f"Не удалось получить план выполнения: {e}")
    return _AnalysisState(resp, parsed, version)


def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    started = utcnow()
    if req.connection_id:
        rec, conn = open_connector(req.connection_id)
        req.dbms = rec.dbms
        with conn:
            state = _analyze(req, conn, req.connection_id)
    else:
        state = _analyze(req, None, None)
    resp = state.response
    resp.run_id = _save_run("analyze", req.sql, req.dbms, req.connection_id, state.version, started, resp,
                            issue_codes=[i.code for i in resp.issues], plans={"original": resp.plan})
    return resp


MAX_SCRIPT_STATEMENTS = 100


def analyze_script(req: AnalyzeRequest) -> ScriptAnalyzeResponse:
    """Скрипт из нескольких операторов: каждый анализируется отдельно (одно подключение на весь скрипт)."""
    conn = None
    if req.connection_id:
        rec, conn = open_connector(req.connection_id)
        req.dbms = rec.dbms
    parts = split_script(req.sql, req.dbms)[:MAX_SCRIPT_STATEMENTS]
    out: list[ScriptStatement] = []
    try:
        if conn is not None:
            conn.__enter__()
        for part in parts:
            started = utcnow()
            sub = req.model_copy(update={"sql": part.sql})
            state = _analyze(sub, conn, req.connection_id)
            resp = state.response
            resp.run_id = _save_run("analyze", part.sql, req.dbms, req.connection_id, state.version, started, resp,
                                    issue_codes=[i.code for i in resp.issues], plans={"original": resp.plan})
            out.append(ScriptStatement(index=part.index, title=part.title, start_line=part.start_line, sql=part.sql,
                                       analysis=resp))
    finally:
        if conn is not None:
            conn.__exit__(None, None, None)
    return ScriptAnalyzeResponse(dbms=req.dbms, statements=out)


# ---------------------------------------------------------------- сравнение
def _compare(conn: Connector, original: str, optimized: str, dialect: Dialect, runs: int, warmup: int) -> tuple[Comparison, list[ErrorType]]:
    cmp = Comparison(original_sql=original, optimized_sql=optimized, equivalence=EquivalenceResult(status="skipped"))
    errors: list[ErrorType] = []
    for label, sql in (("исходный", original), ("оптимизированный", optimized)):
        v = safety.check(sql, dialect)
        if not v.allowed:
            cmp.errors.append(f"{label} запрос отклонён safety: {'; '.join(v.reasons)}")
            cmp.equivalence.status = "error"
            if label == "оптимизированный":
                errors.append(ErrorType.DANGEROUS_QUERY)
            return cmp, errors

    analyze_plan = dialect == "postgres"  # в PG EXPLAIN ANALYZE даёт реальные строки и буферы
    try:
        cmp.plan_original = explain.analyze(dialect, conn.explain(original, analyze=analyze_plan))
    except DBError as e:
        cmp.errors.append(f"Исходный запрос: {e}")
        cmp.equivalence.status = "error"
        return cmp, errors
    try:
        cmp.plan_optimized = explain.analyze(dialect, conn.explain(optimized, analyze=analyze_plan))
    except DBError as e:
        cmp.errors.append(f"Оптимизированный запрос: {e}")
        cmp.equivalence.status = "error"
        errors.append(classify_db_error(e))
        return cmp, errors

    order_sensitive = False
    try:
        order_sensitive = bool(parse(original, dialect).info.order_by)
    except SQLParseError:
        pass
    try:
        cmp.equivalence = bench.check_equivalence(conn, original, optimized, order_sensitive)
    except DBError as e:
        cmp.errors.append(str(e))
        cmp.equivalence.status = "error"
        errors.append(classify_db_error(e))
        return cmp, errors
    if cmp.equivalence.status == "different":
        errors.append(ErrorType.RESULT_CHANGED)

    try:
        cmp.benchmark_original, cmp.benchmark_optimized = bench.benchmark_pair(conn, original, optimized, runs, warmup)
    except DBError as e:
        cmp.errors.append(f"Бенчмарк: {e}")
        errors.append(classify_db_error(e))
        return cmp, errors

    if dialect == "postgres":
        for b, p in ((cmp.benchmark_original, cmp.plan_original), (cmp.benchmark_optimized, cmp.plan_optimized)):
            b.rows_examined = p.estimated_rows_examined
            b.disk_reads, b.buffer_hits = explain.pg_buffers(p.raw)

    b0, b1 = cmp.benchmark_original, cmp.benchmark_optimized
    if b1.median_ms > 0:
        cmp.speedup = round(b0.median_ms / b1.median_ms, 3)
        cmp.improvement_pct = round((1 - b1.median_ms / b0.median_ms) * 100, 1) if b0.median_ms > 0 else None
    if cmp.speedup is not None and cmp.speedup < 0.95 and cmp.equivalence.status == "equivalent":
        errors.append(ErrorType.PERFORMANCE_REGRESSION)
    cmp.plan_changes = explain.compare_plans(cmp.plan_original, cmp.plan_optimized)

    try:
        n0, n1 = parse(original, dialect).info.node_count, parse(optimized, dialect).info.node_count
    except SQLParseError:
        n0 = n1 = None
    cmp.score = scoring.optimization_score(cmp.equivalence, b0, b1, cmp.plan_original, cmp.plan_optimized, n0, n1)
    return cmp, errors


def compare(original: str, optimized: str, connection_id: int, runs: int | None, warmup: int | None) -> Comparison:
    st = get_settings()
    started = utcnow()
    rec, conn = open_connector(connection_id)
    with conn:
        cmp, errors = _compare(conn, original, optimized, rec.dbms, runs or st.benchmark_runs,
                               warmup if warmup is not None else st.benchmark_warmup)
        version = conn.server_version()
    _save_run("compare", original, rec.dbms, connection_id, version, started, cmp, comparison=cmp,
              optimized_sql=optimized, optimized_source="manual", error_types=errors)
    return cmp


# ---------------------------------------------------------------- AI-оптимизация
def optimize(req: OptimizeRequest) -> OptimizeResponse:
    st = get_settings()
    started = utcnow()
    conn = None
    if req.connection_id:
        rec, conn = open_connector(req.connection_id)
        req.dbms = rec.dbms
    try:
        if conn is not None:
            conn.__enter__()
        return _optimize(req, conn, started, st)
    finally:
        if conn is not None:
            conn.__exit__(None, None, None)


def _optimize(req: OptimizeRequest, conn: Connector | None, started, st) -> OptimizeResponse:
    state = _analyze(req, conn, req.connection_id)
    analysis = state.response
    resp = OptimizeResponse(analysis=analysis, verdict="failed", verdict_reason="")
    ai_run = None

    def finish() -> OptimizeResponse:
        resp.run_id = _save_run("optimize", req.sql, req.dbms, req.connection_id, state.version, started, resp,
                                issue_codes=[i.code for i in analysis.issues], plans={"original": analysis.plan},
                                comparison=resp.comparison, optimized_sql=resp.optimized_query, optimized_source="ai",
                                ai_run=ai_run, error_types=resp.error_types, verdict=resp.verdict,
                                verdict_reason=resp.verdict_reason,
                                confidence=resp.confidence.confidence if resp.confidence else None,
                                model_parameters={"temperature": st.llm_temperature})
        return resp

    if not analysis.safety.allowed:
        resp.verdict_reason = "Исходный запрос не прошёл проверку безопасности: " + "; ".join(analysis.safety.reasons)
        return finish()
    if state.parsed is None:
        resp.verdict_reason = f"Исходный запрос не разобран: {analysis.parse_error}"
        return finish()

    context = ai.build_context(req.sql, req.dbms, state.version, analysis.schema_info, analysis.plan,
                               analysis.issues, analysis.parsed.tables if analysis.parsed else [])
    try:
        if req.model == ai.BASELINE_MODEL:
            ai_run = ai.baseline_run(state.parsed)
        else:
            ai_run = ai.call_model(context, req.model, req.prompt_version, st.llm_temperature)
    except (LLMError, FileNotFoundError, ValueError) as e:
        resp.ai_error = str(e)
        resp.verdict_reason = f"Ошибка вызова модели: {e}"
        return finish()

    resp.llm = LLMCallInfo(provider=ai_run.llm.provider, model=ai_run.llm.model, prompt_version=ai_run.prompt.id,
                           latency_ms=round(ai_run.llm.latency_ms, 1), prompt_tokens=ai_run.llm.prompt_tokens,
                           completion_tokens=ai_run.llm.completion_tokens)
    if ai_run.response is None:
        resp.ai_error = ai_run.error
        resp.error_types = ai_run.error_types or []
        resp.verdict = "rejected"
        resp.verdict_reason = ai_run.error or "Некорректный ответ модели"
        return finish()

    resp.ai = ai_run.response
    errors, notes, verdict = ai.validate_ai_output(resp.ai, req.sql, req.dbms, analysis.schema_info)
    resp.error_types = errors
    resp.optimized_safety = verdict
    resp.optimized_query = resp.ai.optimized_query
    agreement = None if req.model == ai.BASELINE_MODEL else scoring.rule_ai_agreement(analysis.issues, resp.ai)

    if not resp.optimized_query:
        resp.verdict = "no_change"
        resp.verdict_reason = "Модель не предложила переписанный запрос" + \
                              (" (рекомендованы только индексы)" if resp.ai.recommended_indexes else "")
        resp.confidence = scoring.ai_confidence(None, None, agreement, None, None, None)
        return finish()
    if ai.same_query(req.sql, resp.optimized_query, req.dbms):
        resp.verdict = "no_change"
        resp.verdict_reason = "Предложенный запрос совпадает с исходным"
        return finish()
    blocking = [e for e in errors if e != ErrorType.SCHEMA_HALLUCINATION]  # ошибка в рекомендации индекса не ломает SQL
    if blocking:
        resp.verdict = "rejected"
        resp.verdict_reason = "Статическая проверка не пройдена: " + "; ".join(notes)
        return finish()

    if conn is None or not req.verify:
        resp.verdict = "unverified"
        resp.verdict_reason = ("Запрос прошёл статические проверки, но не выполнялся: подключите БД, чтобы проверить "
                               "эквивалентность результата и измерить реальное ускорение.")
        resp.confidence = scoring.ai_confidence(None, None, agreement, None, None, None)
        return finish()

    cmp, run_errors = _compare(conn, req.sql, resp.optimized_query, req.dbms, req.runs or st.benchmark_runs,
                               req.warmup if req.warmup is not None else st.benchmark_warmup)
    resp.comparison = cmp
    resp.error_types = list(dict.fromkeys(errors + run_errors))
    resp.confidence = scoring.ai_confidence(cmp.equivalence, cmp.speedup, agreement, cmp.plan_original,
                                            cmp.plan_optimized, cmp.benchmark_optimized)
    eq = cmp.equivalence.status
    if eq == "error":
        resp.verdict = "rejected"
        resp.verdict_reason = "Ошибка выполнения: " + "; ".join(cmp.errors)
    elif eq == "different":
        resp.verdict = "rejected"
        resp.verdict_reason = "REJECT OPTIMIZATION: результат оптимизированного запроса отличается от исходного"
    elif cmp.speedup is None:
        resp.verdict = "unverified"
        resp.verdict_reason = "Результат совпал, но бенчмарк не выполнен: " + "; ".join(cmp.errors)
    elif cmp.speedup < 0.95:
        resp.verdict = "rejected"
        resp.verdict_reason = f"Результат совпал, но запрос стал медленнее ({cmp.speedup:.2f}x)"
    elif cmp.speedup < 1.05:
        resp.verdict = "no_change"
        resp.verdict_reason = f"Результат совпал, значимого ускорения нет ({cmp.speedup:.2f}x)"
    else:
        resp.verdict = "accepted"
        resp.verdict_reason = f"Результат совпал, ускорение {cmp.speedup:.2f}x"
    return finish()


# ---------------------------------------------------------------- сохранение
def _save_run(kind: str, sql: str, dbms: str, connection_id: int | None, version: str | None, started,
              payload, *, issue_codes: list[str] | None = None, plans: dict[str, PlanSummary | None] | None = None,
              comparison: Comparison | None = None, optimized_sql: str | None = None, optimized_source: str = "ai",
              ai_run=None, error_types: list | None = None, verdict: str | None = None,
              verdict_reason: str | None = None, confidence: float | None = None,
              model_parameters: dict | None = None) -> int:
    sql_hash = hashlib.sha256(sql.strip().encode("utf-8")).hexdigest()
    with SessionLocal() as s:
        q = s.query(Query).filter_by(sql_hash=sql_hash, dbms=dbms).first()
        if q is None:
            try:
                qtype = parse(sql, dbms).info.query_type
            except SQLParseError:
                qtype = None
            q = Query(sql_text=sql, sql_hash=sql_hash, dbms=dbms, query_type=qtype)
            s.add(q)
            s.flush()
        run = AnalysisRun(query_id=q.id, kind=kind, connection_id=connection_id, dbms_version=version,
                          app_version=__version__, started_at=started, finished_at=utcnow(), verdict=verdict,
                          verdict_reason=verdict_reason, confidence=confidence,
                          error_types=[e.value if hasattr(e, "value") else e for e in (error_types or [])],
                          issue_codes=issue_codes, model_parameters=model_parameters,
                          result=payload.model_dump(mode="json"))
        run.versions.append(QueryVersion(source="original", sql_text=sql))
        if optimized_sql:
            run.versions.append(QueryVersion(source=optimized_source, sql_text=optimized_sql))
        for label, p in (plans or {}).items():
            if p is not None:
                run.plans.append(ExecutionPlan(label=label, total_cost=p.total_cost, analyzed=p.analyzed, raw=p.raw))
        if comparison is not None:
            for label, p in (("original", comparison.plan_original), ("optimized", comparison.plan_optimized)):
                if p is not None and not (label == "original" and plans and plans.get("original")):
                    run.plans.append(ExecutionPlan(label=label, total_cost=p.total_cost, analyzed=p.analyzed, raw=p.raw))
            for label, b in (("original", comparison.benchmark_original), ("optimized", comparison.benchmark_optimized)):
                if b is not None:
                    run.benchmarks.append(Benchmark(label=label, runs=b.runs, warmup=b.warmup, mean_ms=b.mean_ms,
                                                    median_ms=b.median_ms, min_ms=b.min_ms, max_ms=b.max_ms,
                                                    stdev_ms=b.stdev_ms, rows_returned=b.rows_returned,
                                                    rows_examined=b.rows_examined, times_ms=b.times_ms))
            if comparison.benchmark_original and comparison.benchmark_optimized:
                run.original_time_ms = comparison.benchmark_original.median_ms
                run.optimized_time_ms = comparison.benchmark_optimized.median_ms
            run.speedup = comparison.speedup
            if comparison.equivalence.status in ("equivalent", "different"):
                run.result_equivalent = comparison.equivalence.status == "equivalent"
            run.optimization_score = comparison.score.score if comparison.score else None
        if ai_run is not None:
            run.model_name = f"{ai_run.llm.provider}:{ai_run.llm.model}" if ai_run.llm else None
            run.prompt_version, run.prompt_sha256 = ai_run.prompt.id, ai_run.prompt.sha256
            run.ai_recommendations.append(AIRecommendation(
                provider=ai_run.llm.provider if ai_run.llm else None, model=ai_run.llm.model if ai_run.llm else None,
                prompt_version=ai_run.prompt.id, system_prompt=ai_run.system_prompt, user_prompt=ai_run.user_prompt,
                raw_response=ai_run.llm.text if ai_run.llm else None,
                parsed=ai_run.response.model_dump(mode="json") if ai_run.response else None, error=ai_run.error,
                latency_ms=ai_run.llm.latency_ms if ai_run.llm else None,
                prompt_tokens=ai_run.llm.prompt_tokens if ai_run.llm else None,
                completion_tokens=ai_run.llm.completion_tokens if ai_run.llm else None))
            for r in (ai_run.response.recommended_indexes if ai_run.response else []):
                run.index_recommendations.append(IndexRecommendation(source="ai", table_name=r.table, columns=r.columns,
                                                                     sql=r.sql, reason=r.reason))
        s.add(run)
        s.commit()
        return run.id
