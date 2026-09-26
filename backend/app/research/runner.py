"""Research Mode: фоновое выполнение экспериментов «датасет × модели» на реальной БД."""

from __future__ import annotations

import threading
import traceback

from app import __version__
from app.config import get_settings
from app.db import Dataset, Experiment, ExperimentResult, SessionLocal, utcnow
from app.models import OptimizeRequest
from app.research import stats
from app.services import pipeline
from app.services.ai import optimizer as ai
from app.services.connectors import DBError

_cancel: set[int] = set()
_threads: dict[int, threading.Thread] = {}


def create(name: str, dataset_id: int, connection_id: int, models: list[str], prompt_version: str | None,
           runs: int, warmup: int) -> Experiment:
    st = get_settings()
    prompt = ai.load_prompt(prompt_version or ai.DEFAULT_PROMPT)
    rec, _ = pipeline.connection_config(connection_id)
    with SessionLocal() as s:
        ds = s.get(Dataset, dataset_id)
        if ds is None:
            raise pipeline.PipelineError("Датасет не найден")
        if ds.dbms != rec.dbms:
            raise ValueError(f"Датасет рассчитан на {ds.dbms}, а подключение — {rec.dbms}")
        exp = Experiment(name=name, dataset_id=ds.id, connection_id=connection_id, models=models,
                         prompt_version=prompt.id, prompt_sha256=prompt.sha256, runs=runs, warmup=warmup,
                         model_parameters={"temperature": st.llm_temperature, "ollama_num_ctx": st.ollama_num_ctx},
                         progress_total=len(ds.queries) * len(models), app_version=__version__, dbms=ds.dbms,
                         dataset_version=ds.version, database_seed=ds.database_seed)
        s.add(exp)
        s.commit()
        return exp


def start(exp_id: int) -> None:
    t = threading.Thread(target=_run, args=(exp_id,), name=f"experiment-{exp_id}", daemon=True)
    _threads[exp_id] = t
    t.start()


def cancel(exp_id: int) -> None:
    _cancel.add(exp_id)


def is_alive(exp_id: int) -> bool:
    t = _threads.get(exp_id)
    return bool(t and t.is_alive())


def mark_interrupted() -> None:
    """При перезапуске сервера эксперименты, которые шли в памяти, помечаются прерванными."""
    with SessionLocal() as s:
        for e in s.query(Experiment).filter(Experiment.status.in_(["running", "pending"])):
            e.status = "interrupted"
        s.commit()


def _set(exp_id: int, **fields) -> None:
    with SessionLocal() as s:
        e = s.get(Experiment, exp_id)
        for k, v in fields.items():
            setattr(e, k, v)
        s.commit()


def _run(exp_id: int) -> None:
    st = get_settings()
    with SessionLocal() as s:
        exp = s.get(Experiment, exp_id)
        queries = [(q.id, q.key, q.sql_text) for q in exp.dataset.queries]
        models, connection_id, dbms = list(exp.models), exp.connection_id, exp.dbms
        prompt_version, runs, warmup = exp.prompt_version, exp.runs, exp.warmup
        done_pairs = {(r.dataset_query_id, r.model) for r in s.query(ExperimentResult).filter_by(experiment_id=exp_id)}
    _set(exp_id, status="running", started_at=utcnow(), error=None)
    conn = None
    try:
        _, conn = pipeline.open_connector(connection_id)
        conn.__enter__()
        _set(exp_id, dbms_version=conn.server_version())
        done = len(done_pairs)
        # модели во внутреннем цикле: кандидаты для одного запроса измеряются близко по времени
        for qid, key, sql in queries:
            for model in models:
                if exp_id in _cancel:
                    _set(exp_id, status="cancelled", finished_at=utcnow(), current_item=None)
                    return
                if (qid, model) in done_pairs:
                    continue
                _set(exp_id, current_item=f"{key} · {model}")
                req = OptimizeRequest(sql=sql, dbms=dbms, connection_id=connection_id, model=model,
                                      prompt_version=None if model == ai.BASELINE_MODEL else prompt_version,
                                      runs=runs, warmup=warmup)
                try:
                    resp = pipeline._optimize(req, conn, utcnow(), st)
                    _save_result(exp_id, qid, model, resp, sql, dbms)
                except DBError as e:
                    _save_error(exp_id, qid, model, f"СУБД: {e}")
                    try:  # соединение могло оборваться — переподключаемся
                        conn.__exit__(None, None, None)
                        conn.__enter__()
                    except Exception:
                        pass
                except Exception as e:  # noqa: BLE001 — один сбой не должен останавливать эксперимент
                    _save_error(exp_id, qid, model, f"{type(e).__name__}: {e}")
                done += 1
                _set(exp_id, progress_done=done)
        _set(exp_id, status="done", finished_at=utcnow(), current_item=None)
    except Exception as e:  # noqa: BLE001
        _set(exp_id, status="failed", finished_at=utcnow(), error=f"{e}\n{traceback.format_exc()[-2000:]}")
    finally:
        _cancel.discard(exp_id)
        if conn is not None:
            try:
                conn.__exit__(None, None, None)
            except Exception:
                pass


def _save_result(exp_id: int, qid: int, model: str, resp, original_sql: str, dbms: str) -> None:
    errors = [e.value if hasattr(e, "value") else e for e in resp.error_types]
    cmp = resp.comparison
    equivalent = None
    if cmp is not None and cmp.equivalence.status in ("equivalent", "different"):
        equivalent = cmp.equivalence.status == "equivalent"
    proposed = bool(resp.optimized_query) and not ai.same_query(original_sql, resp.optimized_query, dbms)
    executed = cmp is not None and cmp.equivalence.status in ("equivalent", "different")
    with SessionLocal() as s:
        s.add(ExperimentResult(
            experiment_id=exp_id, dataset_query_id=qid, model=model, run_id=resp.run_id,
            outcome=stats.classify(resp.verdict, errors, resp.ai_error, equivalent), verdict=resp.verdict,
            proposed=proposed, executed=executed, equivalent=equivalent,
            speedup=cmp.speedup if cmp else None,
            time_before_ms=cmp.benchmark_original.median_ms if cmp and cmp.benchmark_original else None,
            time_after_ms=cmp.benchmark_optimized.median_ms if cmp and cmp.benchmark_optimized else None,
            optimization_score=cmp.score.score if cmp and cmp.score else None,
            confidence=resp.confidence.confidence if resp.confidence else None, error_types=errors,
            latency_ms=resp.llm.latency_ms if resp.llm else None,
            prompt_tokens=resp.llm.prompt_tokens if resp.llm else None,
            completion_tokens=resp.llm.completion_tokens if resp.llm else None,
            message=resp.verdict_reason))
        s.commit()


def _save_error(exp_id: int, qid: int, model: str, message: str) -> None:
    with SessionLocal() as s:
        s.add(ExperimentResult(experiment_id=exp_id, dataset_query_id=qid, model=model, outcome="error",
                               verdict="failed", error_types=[], message=message))
        s.commit()


def result_rows(exp_id: int) -> list[dict]:
    with SessionLocal() as s:
        out = []
        for r in s.query(ExperimentResult).filter_by(experiment_id=exp_id).order_by(ExperimentResult.id):
            out.append({"id": r.id, "query_id": r.dataset_query_id, "key": r.query.key, "title": r.query.title,
                        "category": r.query.category, "model": r.model, "run_id": r.run_id, "outcome": r.outcome,
                        "verdict": r.verdict, "proposed": r.proposed, "executed": r.executed,
                        "equivalent": r.equivalent, "speedup": r.speedup, "time_before_ms": r.time_before_ms,
                        "time_after_ms": r.time_after_ms, "optimization_score": r.optimization_score,
                        "confidence": r.confidence, "error_types": r.error_types or [], "latency_ms": r.latency_ms,
                        "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
                        "message": r.message})
        return out
