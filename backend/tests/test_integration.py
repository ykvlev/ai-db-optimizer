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

    def complete(self, model, system, user, temperature, json_mode=True):
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


def test_postgres_non_default_schema():
    """Таблицы из пользовательской схемы (study.books) видны в интроспекции и используются правилами."""
    import psycopg
    from app.services import rules
    from app.services.sql_parser import parse
    cfg = TARGETS["postgres"]
    if not _available(cfg):
        pytest.skip("postgres недоступна")
    admin = psycopg.connect(host=cfg.host, port=cfg.port, dbname=cfg.database, user="postgres", password="rootpass",
                            autocommit=True)
    try:
        admin.execute("DROP SCHEMA IF EXISTS study CASCADE")
        admin.execute("CREATE SCHEMA study")
        admin.execute("CREATE TABLE study.books (bshifr int PRIMARY KEY, title text, price numeric(8,2))")
        admin.execute("CREATE TABLE study.tickets (id int PRIMARY KEY, bshifr int REFERENCES study.books, data_vydachi date)")
        admin.execute("GRANT USAGE ON SCHEMA study TO optimizer_ro")
        admin.execute("GRANT SELECT ON ALL TABLES IN SCHEMA study TO optimizer_ro")
        with make_connector(cfg, 10000) as c:
            schema = c.introspect()
            books = schema.table("study.books")
            assert books is not None and [col.name for col in books.columns] == ["bshifr", "title", "price"]
            assert schema.table("study.tickets").foreign_keys[0].ref_table == "study.books"
            assert schema.table("orders") is not None  # таблицы схемы по умолчанию — без префикса
            sql = "SELECT t.id, b.title FROM study.books b JOIN study.tickets t ON t.bshifr = b.bshifr WHERE EXTRACT(YEAR FROM t.data_vydachi) = 2024"
            codes = {i.code for i in rules.run_rules(parse(sql, "postgres"), schema, "postgres")}
            assert "FUNCTION_ON_COLUMN" in codes and "MISSING_INDEX" in codes  # tickets.bshifr без индекса
            c.explain(sql)
    finally:
        admin.execute("DROP SCHEMA IF EXISTS study CASCADE")
        admin.close()
