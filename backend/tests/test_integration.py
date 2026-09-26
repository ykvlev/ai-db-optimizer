"""Интеграционные тесты полного цикла на тестовых БД из docker/ (пропускаются, если БД недоступны).

LLM заменена фиктивным провайдером: проверяется не качество модели, а то, что система
принимает корректную оптимизацию и отклоняет ошибочную по реальным измерениям.
"""

import json

import pytest

from app.db import DatabaseConnection, SessionLocal, encrypt, init_db
from app.models import OptimizeRequest
from app.services import pipeline
from app.services.ai.providers import LLMProvider, LLMResult, get_registry
from app.services.connectors import ConnectionConfig, make_connector

TARGETS = {
    "mysql": ConnectionConfig("mysql", "127.0.0.1", 3307, "shop", "optimizer_ro", "optimizer_ro"),
    "postgres": ConnectionConfig("postgres", "127.0.0.1", 5434, "shop", "optimizer_ro", "optimizer_ro"),
}


def _available(cfg) -> bool:
    try:
        with make_connector(cfg, 5000) as c:
            c.ping()
        return True
    except Exception:
        return False


class ScriptedProvider(LLMProvider):
    name = "scripted"
    models = ["m"]
    answer: dict = {}

    def complete(self, model, system, user, temperature):
        return LLMResult(text=json.dumps(self.answer, ensure_ascii=False), provider=self.name, model=model, latency_ms=1)


@pytest.fixture(params=list(TARGETS))
def conn_id(request):
    cfg = TARGETS[request.param]
    if not _available(cfg):
        pytest.skip(f"{request.param} недоступна (docker compose up)")
    init_db()
    with SessionLocal() as s:
        rec = DatabaseConnection(name=f"test-{cfg.dbms}", dbms=cfg.dbms, host=cfg.host, port=cfg.port,
                                 database=cfg.database, username=cfg.username, password_enc=encrypt(cfg.password))
        s.add(rec)
        s.commit()
        return rec.id


def _optimize(conn_id, sql, answer):
    ScriptedProvider.answer = answer
    get_registry().register(ScriptedProvider())
    return pipeline.optimize(OptimizeRequest(sql=sql, dbms="mysql", connection_id=conn_id, model="scripted:m",
                                             runs=3, warmup=1))


ORIGINAL = "SELECT id, user_id, total FROM orders WHERE DATE(created_at) = '2025-03-15' ORDER BY id"


def test_correct_optimization_is_accepted(conn_id):
    r = _optimize(conn_id, ORIGINAL, {
        "summary": "DATE() над колонкой", "issues": [{"type": "FUNCTION_ON_COLUMN", "severity": "high", "description": "-"}],
        "optimized_query": "SELECT id, user_id, total FROM orders WHERE created_at >= '2025-03-15' "
                           "AND created_at < '2025-03-16' ORDER BY id", "explanation": ["диапазон"]})
    assert r.comparison.equivalence.status == "equivalent"
    assert r.comparison.speedup > 1.5
    assert r.verdict == "accepted", r.verdict_reason
    assert r.confidence.confidence > 0.7


def test_changed_result_is_rejected(conn_id):
    r = _optimize(conn_id, ORIGINAL, {
        "summary": "x", "optimized_query": "SELECT id, user_id, total FROM orders WHERE created_at >= '2025-03-15' "
                                           "AND created_at < '2025-03-17' ORDER BY id"})
    assert r.comparison.equivalence.status == "different"
    assert r.verdict == "rejected"
    assert "RESULT_CHANGED" in [e.value for e in r.error_types]
    assert r.confidence.confidence == 0.0


def test_hallucinated_column_is_rejected_before_execution(conn_id):
    r = _optimize(conn_id, ORIGINAL, {"summary": "x", "optimized_query": "SELECT o.id FROM orders o WHERE o.order_date = '2025-03-15'"})
    assert r.verdict == "rejected" and r.comparison is None
    assert [e.value for e in r.error_types] == ["WRONG_COLUMN"]
