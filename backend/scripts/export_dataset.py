"""Выгрузка открытого датасета SQL Optimization Dataset из результатов экспериментов Research Mode.

    python scripts/export_dataset.py [--experiments 1,2,3,4,5,6] [--out ../dataset/sql-optimization-dataset-v1]

Одна запись = пара «запрос набора × участник» в одном эксперименте: исходный SQL, кандидат, план выполнения,
замеры, проверка эквивалентности, исход и (для языковой модели) ответ модели. Пароли и параметры подключения
в датасет не попадают.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import AIRecommendation, AnalysisRun, Experiment, ExperimentResult, SessionLocal  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
VERSION = "1.2.0"
NAME = "sql-optimization-dataset"


def iso(v):
    return v.isoformat(timespec="seconds") + "Z" if v else None


def participant(model: str) -> dict:
    """Модель и версия промпта из идентификатора участника (model@prompt)."""
    if model.startswith("baseline:"):
        return {"participant": model, "participant_type": "rule_based", "llm": None}
    name, _, prompt = model.partition("@")
    return {"participant": model, "participant_type": "llm", "llm": name, "prompt_override": prompt or None}


def plan_brief(plan: dict | None) -> dict | None:
    if not plan:
        return None
    return {"total_cost": plan.get("total_cost"), "analyzed": plan.get("analyzed"), "uses_filesort": plan.get("uses_filesort"),
            "uses_temporary": plan.get("uses_temporary"), "root": plan.get("root")}


def bench(b: dict | None) -> dict | None:
    if not b:
        return None
    return {k: b.get(k) for k in ("runs", "warmup", "times_ms", "median_ms", "mean_ms", "min_ms", "max_ms", "stdev_ms",
                                  "rows_returned", "rows_examined")}


def build(exp_ids: list[int], out: Path) -> None:
    keep = {"README.md", "LICENSE"}  # описание и лицензия пишутся вручную
    if out.exists():
        for p in out.iterdir():
            if p.name not in keep:
                shutil.rmtree(p) if p.is_dir() else p.unlink()
    (out / "schema").mkdir(parents=True)
    records, llm_io, experiments, queries = [], [], [], {}

    with SessionLocal() as s:
        for eid in exp_ids:
            e = s.get(Experiment, eid)
            if e is None or e.status != "done":
                raise SystemExit(f"Эксперимент {eid} не найден или не завершён")
            experiments.append({
                "experiment_id": e.id, "name": e.name, "dbms": e.dbms, "dbms_version": e.dbms_version,
                "query_set": e.dataset_version, "database_seed": e.database_seed, "participants": e.models,
                "prompt_version": e.prompt_version, "prompt_sha256": e.prompt_sha256, "model_parameters": e.model_parameters,
                "benchmark_runs": e.runs, "benchmark_warmup": e.warmup, "app_version": e.app_version,
                "started_at": iso(e.started_at), "finished_at": iso(e.finished_at),
            })
            rows = s.query(ExperimentResult).filter_by(experiment_id=eid).order_by(ExperimentResult.id).all()
            for r in rows:
                q = r.query
                queries.setdefault((e.dataset_version, e.dbms, q.key), {
                    "query_set": e.dataset_version, "dbms": e.dbms, "query_key": q.key, "category": q.category,
                    "title": q.title, "sql": q.sql_text})
                run = s.get(AnalysisRun, r.run_id) if r.run_id else None
                res = (run.result or {}) if run else {}
                cmp_ = res.get("comparison") or {}
                eq = cmp_.get("equivalence") or {}
                analysis = res.get("analysis") or {}
                ai = res.get("ai") or {}
                rec_id = f"e{eid}-{q.key}-{r.model}"
                rec = {
                    "record_id": rec_id, "experiment_id": eid, "dbms": e.dbms, "dbms_version": e.dbms_version,
                    "query_set": e.dataset_version, "database_seed": e.database_seed,
                    "query_key": q.key, "category": q.category, "title": q.title,
                    **participant(r.model),
                    "prompt_version": run.prompt_version if run else None,
                    "prompt_sha256": run.prompt_sha256 if run else None,
                    "original_sql": q.sql_text,
                    "candidate_sql": res.get("optimized_query"),
                    "proposed": r.proposed, "executed": r.executed,
                    "outcome": r.outcome, "verdict": r.verdict, "verdict_reason": run.verdict_reason if run else r.message,
                    "error_types": r.error_types or [],
                    "detected_issues": [i.get("code") for i in analysis.get("issues") or [] if i.get("code") != "RULE_ERROR"],
                    "equivalence": {k: eq.get(k) for k in ("status", "rows_original", "rows_optimized", "columns_match",
                                                           "order_checked", "checksum_original", "checksum_optimized")} if eq else None,
                    "speedup": r.speedup, "time_before_ms": r.time_before_ms, "time_after_ms": r.time_after_ms,
                    "benchmark_original": bench(cmp_.get("benchmark_original")),
                    "benchmark_candidate": bench(cmp_.get("benchmark_optimized")),
                    "plan_original": plan_brief(cmp_.get("plan_original") or analysis.get("plan")),
                    "plan_candidate": plan_brief(cmp_.get("plan_optimized")),
                    "plan_changes": cmp_.get("plan_changes") or [],
                    "optimization_score": r.optimization_score, "confidence": r.confidence,
                    "llm_summary": ai.get("summary"), "llm_explanation": ai.get("explanation"),
                    "llm_self_confidence": ai.get("confidence"),
                    "llm_recommended_indexes": ai.get("recommended_indexes"),
                    "latency_ms": r.latency_ms, "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
                    "app_version": run.app_version if run else e.app_version,
                    "created_at": iso(r.created_at),
                }
                records.append(rec)
                air = s.query(AIRecommendation).filter_by(run_id=r.run_id).first() if r.run_id else None
                if air is not None and air.provider != "baseline":
                    llm_io.append({"record_id": rec_id, "provider": air.provider, "model": air.model,
                                   "prompt_version": air.prompt_version, "system_prompt": air.system_prompt,
                                   "user_prompt": air.user_prompt, "raw_response": air.raw_response, "error": air.error})

    def jsonl(name, items):
        with open(out / name, "w", encoding="utf-8", newline="\n") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False, default=str) + "\n")

    jsonl("records.jsonl", records)
    jsonl("llm_io.jsonl", llm_io)
    (out / "experiments.json").write_text(json.dumps(experiments, ensure_ascii=False, indent=1), encoding="utf-8")

    flat_cols = ["record_id", "experiment_id", "dbms", "dbms_version", "query_set", "query_key", "category", "participant",
                 "participant_type", "prompt_version", "outcome", "verdict", "proposed", "executed", "error_types",
                 "detected_issues", "equivalence_status", "rows_original", "rows_candidate", "speedup", "time_before_ms",
                 "time_after_ms", "plan_cost_original", "plan_cost_candidate", "latency_ms", "prompt_tokens",
                 "completion_tokens", "original_sql", "candidate_sql"]
    with open(out / "records.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=flat_cols)
        w.writeheader()
        for r in records:
            eq, po, pc = r["equivalence"] or {}, r["plan_original"] or {}, r["plan_candidate"] or {}
            w.writerow({**{k: r.get(k) for k in flat_cols if k in r},
                        "error_types": ";".join(r["error_types"]), "detected_issues": ";".join(r["detected_issues"]),
                        "equivalence_status": eq.get("status"), "rows_original": eq.get("rows_original"),
                        "rows_candidate": eq.get("rows_optimized"), "plan_cost_original": po.get("total_cost"),
                        "plan_cost_candidate": pc.get("total_cost")})
    with open(out / "queries.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["query_set", "dbms", "query_key", "category", "title", "sql"])
        w.writeheader()
        w.writerows(sorted(queries.values(), key=lambda q: (q["query_set"], q["dbms"], q["query_key"])))

    for dbms in ("mysql", "postgres"):
        shutil.copy(ROOT / "docker" / dbms / "01_schema_and_seed.sql", out / "schema" / f"{dbms}_schema_and_seed.sql")
    prompts = out / "prompts"
    prompts.mkdir()
    for p in (ROOT / "backend/app/services/ai/prompts").glob("*.json"):
        shutil.copy(p, prompts / p.name)

    stats = {"version": VERSION, "records": len(records), "llm_records": len(llm_io), "experiments": len(experiments),
             "queries": len(queries), "outcomes": {}}
    for r in records:
        stats["outcomes"][r["outcome"]] = stats["outcomes"].get(r["outcome"], 0) + 1
    (out / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")

    sums = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out).as_posix()}"
            for p in sorted(out.rglob("*")) if p.is_file() and p.name != "SHA256SUMS"]
    (out / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiments", default="1,2,3,4,5,6,7,8,9,10,11")
    ap.add_argument("--out", default=str(ROOT / "dataset" / f"{NAME}-v1"))
    a = ap.parse_args()
    build([int(i) for i in a.experiments.split(",")], Path(a.out))
