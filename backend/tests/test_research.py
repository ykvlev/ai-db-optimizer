import json
import time

import pytest

from app.db import DatabaseConnection, SessionLocal, encrypt, init_db
from app.research import datasets, report, runner, stats
from app.research.api import seed_builtin_datasets
from app.services import safety
from app.services.ai.providers import LLMProvider, LLMResult, get_registry
from tests.test_integration import TARGETS, _available


def test_builtin_dataset_shape():
    for dbms in ("mysql", "postgres"):
        full = datasets.build_shop_bench(dbms)
        assert len(full) == 40
        assert {q["category"] for q in full} == set(datasets.CATEGORIES)
        assert len({q["key"] for q in full}) == 40
        assert all(safety.check(q["sql"], dbms).allowed for q in full)
        assert len(datasets.build_shop_bench_mini(dbms)) == len(datasets.CATEGORIES)


def test_classify():
    assert stats.classify("accepted", [], None, True) == "improved"
    assert stats.classify("no_change", [], None, True) == "unchanged"
    assert stats.classify("rejected", ["PERFORMANCE_REGRESSION"], None, True) == "worse"
    assert stats.classify("rejected", ["RESULT_CHANGED"], None, False) == "invalid"
    assert stats.classify("failed", [], "timeout", None) == "error"


def test_summarize_and_bootstrap():
    rows = [{"model": "m", "category": "c", "outcome": o, "proposed": o != "unchanged", "executed": o in ("improved", "worse"),
             "equivalent": o in ("improved", "worse"), "speedup": sp, "error_types": et, "latency_ms": 100,
             "prompt_tokens": 10, "completion_tokens": 5}
            for o, sp, et in [("improved", 4.0, []), ("improved", 2.0, []), ("worse", 0.5, ["PERFORMANCE_REGRESSION"]),
                              ("invalid", None, ["WRONG_COLUMN"]), ("unchanged", None, [])]]
    s = stats.summarize(rows)["models"]["m"]
    assert s["outcomes"] == {"improved": 2, "unchanged": 1, "worse": 1, "invalid": 1, "error": 0}
    assert s["median_speedup"] == 2.0 and s["geomean_speedup"] == 1.587
    assert s["correct_sql_pct"] == 75.0 and s["hallucinations"] == 1
    assert stats.bootstrap_ci([1, 2, 3, 4, 5]) is not None and stats.bootstrap_ci([1]) is None


class GoodDateModel(LLMProvider):
    """Переписывает DATE(col) = 'd' правильно, всё остальное оставляет как есть."""
    name = "fake"
    models = ["good"]

    def complete(self, model, system, user, temperature):
        ctx = json.loads(user.split("\n", 1)[1])
        q = ctx["query"]
        import re
        m = re.search(r"DATE\(created_at\) = '(\d{4}-\d\d-\d\d)'", q)
        out = None
        if m:
            import datetime as dt
            d = dt.date.fromisoformat(m.group(1))
            out = q.replace(m.group(0), f"created_at >= '{d}' AND created_at < '{d + dt.timedelta(days=1)}'")
        return LLMResult(text=json.dumps({"summary": "ok", "optimized_query": out}), provider="fake", model=model,
                         latency_ms=5, prompt_tokens=100, completion_tokens=20)


@pytest.mark.parametrize("dbms", list(TARGETS))
def test_experiment_end_to_end(dbms):
    cfg = TARGETS[dbms]
    if not _available(cfg):
        pytest.skip(f"{dbms} недоступна")
    init_db()
    seed_builtin_datasets()
    get_registry().register(GoodDateModel())
    from app.db import Dataset
    with SessionLocal() as s:
        conn = DatabaseConnection(name="t", dbms=dbms, host=cfg.host, port=cfg.port, database=cfg.database,
                                  username=cfg.username, password_enc=encrypt(cfg.password))
        s.add(conn)
        # маленький датасет: первые 3 запроса мини-набора (date, year, year_aggregate) + контроль
        mini = s.query(Dataset).filter_by(version="shop-bench-mini-v1", dbms=dbms).one()
        from app.db import DatasetQuery
        ds = Dataset(name="t", version="t-v1", dbms=dbms, database_seed="shop-seed-v1")
        picked = [q for q in mini.queries if q.category in ("date_function", "year_function", "control")]
        ds.queries = [DatasetQuery(position=i, key=q.key, title=q.title, category=q.category, sql_text=q.sql_text)
                      for i, q in enumerate(picked)]
        s.add(ds)
        s.commit()
        conn_id, ds_id = conn.id, ds.id

    exp = runner.create("t", ds_id, conn_id, ["baseline:rule-based", "fake:good"], None, runs=2, warmup=1)
    runner.start(exp.id)
    for _ in range(300):
        if not runner.is_alive(exp.id):
            break
        time.sleep(0.2)
    rows = runner.result_rows(exp.id)
    assert len(rows) == 6
    by = {(r["key"], r["model"]): r for r in rows}
    assert by[("date_function-1", "fake:good")]["outcome"] == "improved"
    assert by[("date_function-1", "baseline:rule-based")]["outcome"] == "improved"
    assert by[("year_function-1", "fake:good")]["outcome"] == "unchanged"
    assert by[("control-1", "baseline:rule-based")]["outcome"] == "unchanged"
    summary = stats.summarize(rows)
    from app.research.api import _load
    meta, _, _ = _load(exp.id)
    assert meta["status"] == "done" and meta["progress_done"] == 6
    html = report.html_report(meta, summary, rows)
    assert "<svg" in html and "shop-seed-v1" in html
    assert "| fake:good |" in report.markdown(meta, summary, rows)
