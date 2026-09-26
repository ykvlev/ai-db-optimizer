"""HTTP API Research Mode: датасеты, эксперименты, отчёты."""

from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, HTTPException, Query as Q
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from app.db import Dataset, DatasetQuery, Experiment, ExperimentResult, SessionLocal
from app.research import datasets as builtin, report, runner, stats
from app.services import safety
from app.services.ai.optimizer import BASELINE_MODEL, list_prompts
from app.services.ai.providers import get_registry

router = APIRouter(prefix="/api")


def seed_builtin_datasets() -> None:
    with SessionLocal() as s:
        for name, version, build, description in builtin.BUILTIN:
            for dbms in ("mysql", "postgres"):
                if s.query(Dataset).filter_by(version=version, dbms=dbms, builtin=True).first():
                    continue
                ds = Dataset(name=name, version=version, dbms=dbms, description=description,
                             database_seed=builtin.DATABASE_SEED, builtin=True)
                ds.queries = [DatasetQuery(position=i, key=q["key"], title=q["title"], category=q["category"],
                                           sql_text=q["sql"]) for i, q in enumerate(build(dbms))]
                s.add(ds)
        s.commit()


# ---------------------------------------------------------------- датасеты
class DatasetQueryIn(BaseModel):
    title: str | None = None
    category: str = "custom"
    sql: str


class DatasetIn(BaseModel):
    name: str
    version: str
    dbms: str = Field(pattern="^(mysql|postgres)$")
    description: str | None = None
    database_seed: str | None = None
    queries: list[DatasetQueryIn] = Field(min_length=1, max_length=5000)


def _ds_out(d: Dataset, with_queries: bool = False) -> dict:
    out = {"id": d.id, "name": d.name, "version": d.version, "dbms": d.dbms, "description": d.description,
           "database_seed": d.database_seed, "builtin": d.builtin, "size": len(d.queries),
           "categories": sorted({q.category for q in d.queries})}
    if with_queries:
        out["queries"] = [{"id": q.id, "key": q.key, "title": q.title, "category": q.category, "sql": q.sql_text}
                          for q in d.queries]
    return out


@router.get("/datasets")
def list_datasets():
    with SessionLocal() as s:
        return [_ds_out(d) for d in s.query(Dataset).order_by(Dataset.id)]


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: int):
    with SessionLocal() as s:
        d = s.get(Dataset, dataset_id)
        if d is None:
            raise HTTPException(404, "Датасет не найден")
        return _ds_out(d, with_queries=True)


@router.post("/datasets")
def create_dataset(body: DatasetIn):
    problems = []
    for i, q in enumerate(body.queries, 1):
        v = safety.check(q.sql, body.dbms)
        if not v.allowed:
            problems.append(f"Запрос {i}: {'; '.join(v.reasons)}")
    if problems:
        raise HTTPException(400, "Датасет содержит недопустимые запросы: " + " | ".join(problems[:10]))
    with SessionLocal() as s:
        d = Dataset(name=body.name, version=body.version, dbms=body.dbms, description=body.description,
                    database_seed=body.database_seed)
        d.queries = [DatasetQuery(position=i, key=f"q{i + 1}", title=q.title or f"Запрос {i + 1}",
                                  category=q.category or "custom", sql_text=q.sql.strip().rstrip(";"))
                     for i, q in enumerate(body.queries)]
        s.add(d)
        s.commit()
        return _ds_out(d)


@router.delete("/datasets/{dataset_id}")
def delete_dataset(dataset_id: int):
    with SessionLocal() as s:
        d = s.get(Dataset, dataset_id)
        if d is None:
            raise HTTPException(404, "Датасет не найден")
        if d.builtin:
            raise HTTPException(400, "Встроенный датасет удалить нельзя")
        if s.query(Experiment).filter_by(dataset_id=dataset_id).first():
            raise HTTPException(400, "По датасету есть эксперименты")
        s.delete(d)
        s.commit()
    return {"deleted": dataset_id}


# ---------------------------------------------------------------- эксперименты
class ExperimentIn(BaseModel):
    name: str
    dataset_id: int
    connection_id: int
    models: list[str] = Field(min_length=1, max_length=10)
    prompt_version: str | None = None
    runs: int = Field(5, ge=1, le=50)
    warmup: int = Field(2, ge=0, le=10)


def _meta(e: Experiment) -> dict:
    return {"id": e.id, "name": e.name, "dataset_id": e.dataset_id, "dataset_name": e.dataset.name,
            "dataset_version": e.dataset_version, "n_queries": len(e.dataset.queries), "connection_id": e.connection_id,
            "models": e.models, "prompt_version": e.prompt_version, "prompt_sha256": e.prompt_sha256, "runs": e.runs,
            "warmup": e.warmup, "model_parameters": e.model_parameters, "status": e.status,
            "running": runner.is_alive(e.id), "progress_done": e.progress_done, "progress_total": e.progress_total,
            "current_item": e.current_item, "app_version": e.app_version, "dbms": e.dbms,
            "dbms_version": e.dbms_version, "database_seed": e.database_seed, "error": e.error,
            "created_at": e.created_at.isoformat() + "Z",
            "started_at": e.started_at.isoformat() + "Z" if e.started_at else None,
            "finished_at": e.finished_at.isoformat() + "Z" if e.finished_at else None}


def _load(exp_id: int) -> tuple[dict, list[dict], dict]:
    with SessionLocal() as s:
        e = s.get(Experiment, exp_id)
        if e is None:
            raise HTTPException(404, "Эксперимент не найден")
        meta = _meta(e)
    rows = runner.result_rows(exp_id)
    return meta, rows, stats.summarize(rows)


@router.get("/experiments")
def list_experiments():
    with SessionLocal() as s:
        return [_meta(e) for e in s.query(Experiment).order_by(Experiment.id.desc())]


@router.post("/experiments")
def create_experiment(body: ExperimentIn):
    available = set(get_registry().model_ids()) | {BASELINE_MODEL}
    unknown = [m for m in body.models if m.partition("@")[0] not in available]
    prompts = set(list_prompts())
    bad_prompts = [m for m in body.models if m.partition("@")[2] and m.partition("@")[2] not in prompts]
    if bad_prompts:
        raise HTTPException(400, f"Неизвестные версии промпта: {', '.join(bad_prompts)}")
    if unknown:
        raise HTTPException(400, f"Модели не настроены: {', '.join(unknown)}")
    try:
        e = runner.create(body.name, body.dataset_id, body.connection_id, list(dict.fromkeys(body.models)),
                          body.prompt_version, body.runs, body.warmup)
    except (ValueError, FileNotFoundError) as err:
        raise HTTPException(400, str(err))
    runner.start(e.id)
    return {"id": e.id}


@router.get("/experiments/{exp_id}")
def get_experiment(exp_id: int):
    meta, rows, summary = _load(exp_id)
    return {"meta": meta, "summary": summary, "results": rows, "conclusions": report.conclusions(meta, summary)}


@router.post("/experiments/{exp_id}/cancel")
def cancel_experiment(exp_id: int):
    runner.cancel(exp_id)
    return {"cancelling": exp_id}


@router.post("/experiments/{exp_id}/resume")
def resume_experiment(exp_id: int):
    """Продолжает прерванный/отменённый эксперимент: уже выполненные пары «запрос × модель» пропускаются."""
    if runner.is_alive(exp_id):
        raise HTTPException(400, "Эксперимент уже выполняется")
    with SessionLocal() as s:
        e = s.get(Experiment, exp_id)
        if e is None:
            raise HTTPException(404, "Эксперимент не найден")
        if e.status == "done":
            raise HTTPException(400, "Эксперимент уже завершён")
    runner.start(exp_id)
    return {"resumed": exp_id}


@router.delete("/experiments/{exp_id}")
def delete_experiment(exp_id: int):
    if runner.is_alive(exp_id):
        raise HTTPException(400, "Сначала остановите эксперимент")
    with SessionLocal() as s:
        e = s.get(Experiment, exp_id)
        if e is None:
            raise HTTPException(404, "Эксперимент не найден")
        s.query(ExperimentResult).filter_by(experiment_id=exp_id).delete()
        s.delete(e)
        s.commit()
    return {"deleted": exp_id}


@router.get("/experiments/{exp_id}/report", response_class=HTMLResponse)
def experiment_report_html(exp_id: int):
    meta, rows, summary = _load(exp_id)
    return HTMLResponse(report.html_report(meta, summary, rows))


@router.get("/experiments/{exp_id}/report.md", response_class=PlainTextResponse)
def experiment_report_md(exp_id: int):
    meta, rows, summary = _load(exp_id)
    return PlainTextResponse(report.markdown(meta, summary, rows), media_type="text/markdown; charset=utf-8",
                             headers={"Content-Disposition": f"attachment; filename=experiment_{exp_id}.md"})


_FIELDS = ["experiment_id", "dataset_version", "key", "category", "title", "model", "outcome", "verdict", "proposed",
           "executed", "equivalent", "speedup", "time_before_ms", "time_after_ms", "optimization_score", "confidence",
           "error_types", "latency_ms", "prompt_tokens", "completion_tokens", "run_id", "message"]


@router.get("/experiments/{exp_id}/export")
def export_experiment(exp_id: int, format: str = Q("csv", pattern="^(csv|json|xlsx)$")):
    meta, rows, summary = _load(exp_id)
    fname = f"experiment_{exp_id}_{meta['dataset_version']}"
    if format == "json":
        body = json.dumps({"meta": meta, "summary": summary, "results": rows}, ensure_ascii=False, indent=1, default=str)
        return Response(body, media_type="application/json",
                        headers={"Content-Disposition": f"attachment; filename={fname}.json"})
    table = [[meta["id"], meta["dataset_version"]] + [
        json.dumps(r[f], ensure_ascii=False) if isinstance(r[f], (list, dict)) else r[f] for f in _FIELDS[2:]] for r in rows]
    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(_FIELDS)
        w.writerows(table)
        return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f"attachment; filename={fname}.csv"})
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "results"
    ws.append(_FIELDS)
    for row in table:
        ws.append(row)
    ws2 = wb.create_sheet("summary")
    ws2.append(["model", "n", *stats.OUTCOMES, "proposed", "correct_sql_pct", "equivalent_pct", "faster_pct",
                "median_speedup", "ci95_low", "ci95_high", "geomean_speedup", "mean_speedup", "regressions",
                "hallucinations", "avg_latency_ms", "prompt_tokens", "completion_tokens"])
    for m, s in summary["models"].items():
        ci = s["median_speedup_ci95"] or [None, None]
        ws2.append([m, s["n"], *[s["outcomes"][o] for o in stats.OUTCOMES], s["proposed"], s["correct_sql_pct"],
                    s["equivalent_pct"], s["faster_pct"], s["median_speedup"], ci[0], ci[1], s["geomean_speedup"],
                    s["mean_speedup"], s["regressions"], s["hallucinations"], s["avg_latency_ms"], s["prompt_tokens"],
                    s["completion_tokens"]])
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename={fname}.xlsx"})
