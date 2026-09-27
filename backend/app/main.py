"""HTTP API (FastAPI)."""

from __future__ import annotations

import csv
import io
import json

from fastapi import FastAPI, HTTPException, Query as Q, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from app import __version__
from app.config import get_settings
from app.db import AnalysisRun, DatabaseConnection, Query, SessionLocal, encrypt, init_db
from app.examples import EXAMPLES
from app.research.api import router as research_router, seed_builtin_datasets
from app.research.runner import mark_interrupted
from app.models import (AnalyzeRequest, AnalyzeResponse, BenchmarkRequest, BenchmarkStats, CompareRequest, Comparison,
                        ConnectionCreate, ConnectionOut, ExplainRequest, OptimizeRequest, OptimizeResponse, PlanSummary, ScriptAnalyzeResponse,
                        SchemaInfo)
from app.services import benchmark as bench
from app.services import explain, pipeline, safety
from app.services.ai.optimizer import BASELINE_MODEL, list_prompts
from app.services.ai.providers import get_registry
from app.services.connectors import DEFAULT_PORTS, ConnectionConfig, DBError, make_connector

app = FastAPI(title="AI Database Optimizer", version=__version__,
              description="Интеллектуальная система анализа и оптимизации SQL-запросов")
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins.split(","), allow_methods=["*"],
                   allow_headers=["*"])


@app.on_event("startup")
def _startup():
    init_db()
    seed_builtin_datasets()
    mark_interrupted()


app.include_router(research_router)


@app.exception_handler(DBError)
def _db_error(_: Request, e: DBError):
    return JSONResponse(status_code=400, content={"detail": str(e), "code": e.code})


@app.exception_handler(pipeline.PipelineError)
def _pipeline_error(_: Request, e: pipeline.PipelineError):
    return JSONResponse(status_code=404, content={"detail": str(e)})


# ---------------------------------------------------------------- служебное
@app.get("/api/health")
def health():
    return {"status": "ok", "version": __version__}


@app.get("/api/models")
def models():
    reg = get_registry()
    return {"models": reg.model_ids() + [BASELINE_MODEL], "default": reg.default_model() or BASELINE_MODEL,
            "prompts": list_prompts(), "providers": list(reg.providers), "baseline": BASELINE_MODEL}


@app.get("/api/examples")
def examples():
    return EXAMPLES


# ---------------------------------------------------------------- запросы
@app.post("/api/query/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest):
    return pipeline.analyze(req)


@app.post("/api/query/analyze-script", response_model=ScriptAnalyzeResponse)
def analyze_script(req: AnalyzeRequest):
    """Скрипт из нескольких SQL-операторов: разбивка по «;» и анализ каждого оператора отдельно."""
    return pipeline.analyze_script(req)


@app.post("/api/query/optimize", response_model=OptimizeResponse)
def optimize(req: OptimizeRequest):
    return pipeline.optimize(req)


@app.post("/api/query/compare", response_model=Comparison)
def compare(req: CompareRequest):
    return pipeline.compare(req.original_sql, req.optimized_sql, req.connection_id, req.runs, req.warmup)


@app.post("/api/explain", response_model=PlanSummary)
def explain_query(req: ExplainRequest):
    rec, conn = pipeline.open_connector(req.connection_id)
    v = safety.check(req.sql, rec.dbms)
    if not v.allowed:
        raise HTTPException(400, "; ".join(v.reasons))
    with conn:
        return explain.analyze(rec.dbms, conn.explain(req.sql, analyze=req.analyze))


@app.post("/api/benchmark", response_model=BenchmarkStats)
def benchmark(req: BenchmarkRequest):
    st = get_settings()
    rec, conn = pipeline.open_connector(req.connection_id)
    v = safety.check(req.sql, rec.dbms)
    if not v.allowed:
        raise HTTPException(400, "; ".join(v.reasons))
    with conn:
        return bench.benchmark(conn, req.sql, min(req.runs or st.benchmark_runs, 50),
                               req.warmup if req.warmup is not None else st.benchmark_warmup)


# ---------------------------------------------------------------- подключения
def _conn_out(c: DatabaseConnection, warnings: list[str] | None = None) -> ConnectionOut:
    return ConnectionOut(id=c.id, name=c.name, dbms=c.dbms, host=c.host, port=c.port, database=c.database,
                         username=c.username, ssl=c.ssl, server_version=c.server_version,
                         read_only_user=c.read_only_user, warnings=warnings or [])


@app.post("/api/database/connect", response_model=ConnectionOut)
def connect(req: ConnectionCreate):
    port = req.port or DEFAULT_PORTS[req.dbms]
    cfg = ConnectionConfig(dbms=req.dbms, host=req.host, port=port, database=req.database, username=req.username,
                           password=req.password, ssl=req.ssl)
    with make_connector(cfg, 10000) as conn:
        version = conn.server_version()
        ro, warnings = conn.privilege_report()
    with SessionLocal() as s:
        rec = DatabaseConnection(name=req.name or f"{req.dbms}://{req.username}@{req.host}:{port}/{req.database}",
                                 dbms=req.dbms, host=req.host, port=port, database=req.database, username=req.username,
                                 password_enc=encrypt(req.password), ssl=req.ssl, server_version=version,
                                 read_only_user=ro)
        s.add(rec)
        s.commit()
        return _conn_out(rec, warnings)


@app.get("/api/database/connections", response_model=list[ConnectionOut])
def connections():
    with SessionLocal() as s:
        return [_conn_out(c) for c in s.scalars(select(DatabaseConnection).order_by(DatabaseConnection.id))]


@app.delete("/api/database/connections/{connection_id}")
def delete_connection(connection_id: int):
    with SessionLocal() as s:
        c = s.get(DatabaseConnection, connection_id)
        if c is None:
            raise HTTPException(404, "Подключение не найдено")
        for run in s.scalars(select(AnalysisRun).where(AnalysisRun.connection_id == connection_id)):
            run.connection_id = None
        s.delete(c)
        s.commit()
    pipeline.invalidate_schema(connection_id)
    return {"deleted": connection_id}


@app.get("/api/database/{connection_id}/schema", response_model=SchemaInfo)
def schema(connection_id: int, refresh: bool = False):
    _, conn = pipeline.open_connector(connection_id)
    with conn:
        return pipeline.live_schema(conn, connection_id, refresh=refresh)[0]


# ---------------------------------------------------------------- история, статистика, экспорт
@app.get("/api/runs")
def runs(limit: int = Q(50, le=500), kind: str | None = None):
    with SessionLocal() as s:
        stmt = select(AnalysisRun, Query).join(Query).order_by(AnalysisRun.id.desc()).limit(limit)
        if kind:
            stmt = stmt.where(AnalysisRun.kind == kind)
        return [{"id": r.id, "kind": r.kind, "started_at": r.started_at.isoformat() + "Z", "dbms": q.dbms,
                 "sql": q.sql_text[:300], "model": r.model_name, "verdict": r.verdict, "speedup": r.speedup,
                 "score": r.optimization_score, "equivalent": r.result_equivalent, "error_types": r.error_types,
                 "issues": len(r.issue_codes or [])} for r, q in s.execute(stmt)]


@app.get("/api/runs/{run_id}")
def run(run_id: int):
    with SessionLocal() as s:
        r = s.get(AnalysisRun, run_id)
        if r is None:
            raise HTTPException(404, "Запуск не найден")
        return {"id": r.id, "kind": r.kind, "sql": r.query.sql_text, "dbms": r.query.dbms,
                "started_at": r.started_at.isoformat() + "Z", "model": r.model_name, "prompt_version": r.prompt_version,
                "app_version": r.app_version, "dbms_version": r.dbms_version, "result": r.result}


@app.get("/api/stats")
def stats():
    with SessionLocal() as s:
        def count(*where):
            return s.scalar(select(func.count(AnalysisRun.id)).where(*where)) or 0
        speedups = [x for x in s.scalars(select(AnalysisRun.speedup).where(
            AnalysisRun.kind == "optimize", AnalysisRun.verdict == "accepted", AnalysisRun.speedup.is_not(None)))]
        speedups.sort()
        median = speedups[len(speedups) // 2] if speedups and len(speedups) % 2 else (
            (speedups[len(speedups) // 2 - 1] + speedups[len(speedups) // 2]) / 2 if speedups else None)
        verdicts = dict(s.execute(select(AnalysisRun.verdict, func.count()).where(AnalysisRun.kind == "optimize")
                                  .group_by(AnalysisRun.verdict)).all())
        models_used = s.scalar(select(func.count(func.distinct(AnalysisRun.model_name)))
                               .where(AnalysisRun.model_name.is_not(None), AnalysisRun.model_name != BASELINE_MODEL)) or 0
        errors: dict[str, int] = {}
        for et in s.scalars(select(AnalysisRun.error_types).where(AnalysisRun.kind == "optimize")):
            for e in et or []:
                errors[e] = errors.get(e, 0) + 1
        return {
            "queries_analyzed": s.scalar(select(func.count(Query.id))) or 0,
            "runs_total": count(),
            "optimize_runs": count(AnalysisRun.kind == "optimize"),
            "verified_runs": count(AnalysisRun.result_equivalent.is_not(None)),
            "successful_optimizations": verdicts.get("accepted", 0),
            "verdicts": {k or "none": v for k, v in verdicts.items()},
            "median_speedup": median,
            "mean_speedup": sum(speedups) / len(speedups) if speedups else None,
            "databases": s.scalar(select(func.count(DatabaseConnection.id))) or 0,
            "ai_models_used": models_used,
            "ai_models_configured": len(get_registry().model_ids()),
            "error_types": errors,
        }


_EXPORT_FIELDS = ["run_id", "query_id", "dbms", "dbms_version", "original_sql", "optimized_sql", "ai_model",
                  "prompt_version", "verdict", "equivalent", "time_before_ms", "time_after_ms", "speedup",
                  "optimization_score", "confidence", "error_types", "issue_codes", "app_version", "started_at"]


def _dataset_records(kind: str | None) -> list[dict]:
    with SessionLocal() as s:
        stmt = select(AnalysisRun).order_by(AnalysisRun.id)
        stmt = stmt.where(AnalysisRun.kind == kind) if kind else stmt.where(AnalysisRun.kind.in_(["optimize", "compare"]))
        out = []
        for r in s.scalars(stmt):
            opt = next((v.sql_text for v in r.versions if v.source != "original"), None)
            out.append({"run_id": r.id, "query_id": r.query_id, "dbms": r.query.dbms, "dbms_version": r.dbms_version,
                        "original_sql": r.query.sql_text, "optimized_sql": opt, "ai_model": r.model_name,
                        "prompt_version": r.prompt_version, "verdict": r.verdict, "equivalent": r.result_equivalent,
                        "time_before_ms": r.original_time_ms, "time_after_ms": r.optimized_time_ms,
                        "speedup": r.speedup, "optimization_score": r.optimization_score, "confidence": r.confidence,
                        "error_types": r.error_types, "issue_codes": r.issue_codes, "app_version": r.app_version,
                        "started_at": r.started_at.isoformat() + "Z",
                        "execution_plan_before": next((p.raw for p in r.plans if p.label == "original"), None),
                        "execution_plan_after": next((p.raw for p in r.plans if p.label == "optimized"), None)})
        return out


@app.get("/api/export/runs")
def export_runs(format: str = Q("json", pattern="^(json|csv|xlsx)$"), kind: str | None = None):
    records = _dataset_records(kind)
    if format == "json":
        return Response(json.dumps(records, ensure_ascii=False, indent=1, default=str), media_type="application/json",
                        headers={"Content-Disposition": "attachment; filename=ai_db_optimizer_runs.json"})
    rows = [[json.dumps(r[f], ensure_ascii=False) if isinstance(r[f], (list, dict)) else r[f] for f in _EXPORT_FIELDS]
            for r in records]
    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(_EXPORT_FIELDS)
        w.writerows(rows)
        return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=ai_db_optimizer_runs.csv"})
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "runs"
    ws.append(_EXPORT_FIELDS)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=ai_db_optimizer_runs.xlsx"})


# Интерфейс раздаётся самим сервером, если задан FRONTEND_DIR (запуск в Docker). Монтируется последним,
# чтобы не перекрывать маршруты /api.
if get_settings().frontend_dir:
    app.mount("/", StaticFiles(directory=get_settings().frontend_dir, html=True), name="frontend")
