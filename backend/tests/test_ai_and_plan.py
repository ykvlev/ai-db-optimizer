import json

import pytest

from app.models import AIResponse, EquivalenceResult
from app.services import explain, scoring
from app.services.ai import optimizer as ai
from app.services.ai.providers import LLMProvider, LLMResult, get_registry
from app.services.benchmark import canonical
from app.services.schema_ddl import parse_ddl
from tests.test_core import DDL

MYSQL_PLAN = {
    "query_block": {
        "select_id": 1, "cost_info": {"query_cost": "50321.10"},
        "ordering_operation": {
            "using_filesort": True,
            "nested_loop": [
                {"table": {"table_name": "o", "access_type": "ALL", "possible_keys": ["idx_orders_created"],
                           "rows_examined_per_scan": 498000, "rows_produced_per_join": 4980, "filtered": "1.00",
                           "cost_info": {"prefix_cost": "50000.1"}, "attached_condition": "(year(`o`.`created_at`) = 2026)"}},
                {"table": {"table_name": "u", "access_type": "eq_ref", "key": "PRIMARY", "rows_examined_per_scan": 1,
                           "rows_produced_per_join": 4980, "filtered": "100.00", "cost_info": {"prefix_cost": "50321.1"}}},
            ],
        },
    }
}

PG_PLAN = [{"Plan": {
    "Node Type": "Sort", "Total Cost": 9000.5, "Plan Rows": 100, "Actual Rows": 90, "Actual Loops": 1,
    "Actual Total Time": 120.0, "Sort Key": ["id"], "Sort Method": "quicksort", "Sort Space Type": "Memory",
    "Shared Hit Blocks": 10, "Shared Read Blocks": 500,
    "Plans": [{"Node Type": "Seq Scan", "Relation Name": "orders", "Alias": "orders", "Total Cost": 8900.0,
               "Plan Rows": 100, "Actual Rows": 90, "Actual Loops": 1, "Actual Total Time": 110.0,
               "Filter": "(date(created_at) = '2025-03-15'::date)", "Rows Removed by Filter": 499910}]}}]


def test_mysql_plan():
    s = explain.analyze("mysql", MYSQL_PLAN)
    assert s.total_cost == 50321.10
    assert s.full_scans == ["o"] and s.index_accesses == ["u"]
    assert s.uses_filesort
    codes = {i.code for i in s.issues}
    assert {"FULL_TABLE_SCAN", "INDEX_NOT_USED", "FILESORT"} <= codes
    assert s.estimated_rows_examined == 498000 + 4980


def test_pg_plan():
    s = explain.analyze("postgres", PG_PLAN)
    assert s.analyzed and s.full_scans == ["orders"]
    assert s.estimated_rows_examined == 90 + 499910
    assert explain.pg_buffers(PG_PLAN) == (500.0, 10.0)
    assert any(i.code == "FULL_TABLE_SCAN" for i in s.issues)


def test_compare_plans():
    after = json.loads(json.dumps(MYSQL_PLAN))
    t = after["query_block"]["ordering_operation"]["nested_loop"][0]["table"]
    t.update(access_type="range", key="idx_orders_created", rows_examined_per_scan=5000)
    after["query_block"]["cost_info"]["query_cost"] = "2500"
    changes = explain.compare_plans(explain.analyze("mysql", MYSQL_PLAN), explain.analyze("mysql", after))
    assert any("Full table scan → Index range scan" in c for c in changes)


def test_extract_json_variants():
    assert ai.extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert ai.extract_json('Вот ответ: {"a": {"b": 2}} Готово.') == {"a": {"b": 2}}
    with pytest.raises(ValueError):
        ai.extract_json("нет json")


def test_validate_ai_output_detects_hallucinations():
    schema, _ = parse_ddl(DDL, "mysql")
    resp = AIResponse(optimized_query="SELECT o.id, o.foo FROM orders o FORCE INDEX (idx_nope) JOIN ghosts g ON g.id = o.id",
                      recommended_indexes=[{"table": "orders", "columns": ["nonexistent"]}])
    errors, notes, verdict = ai.validate_ai_output(resp, "SELECT 1", "mysql", schema)
    assert {e.value for e in errors} >= {"WRONG_TABLE", "WRONG_COLUMN", "INDEX_HALLUCINATION", "SCHEMA_HALLUCINATION"}
    resp = AIResponse(optimized_query="DELETE FROM orders")
    errors, _, verdict = ai.validate_ai_output(resp, "SELECT 1", "mysql", schema)
    assert [e.value for e in errors] == ["DANGEROUS_QUERY"] and not verdict.allowed


def test_canonical_numbers():
    from decimal import Decimal
    assert canonical(5) == canonical(Decimal("5.00")) == canonical(5.0)
    assert canonical(None) != canonical("None")


def test_score_requires_measurements():
    assert scoring.optimization_score(None, None, None, None, None, None, None).score is None
    conf = scoring.ai_confidence(None, None, 1.0, None, None, None)
    assert conf.confidence is None  # без выполнения уверенность не выдумываем
    eq = EquivalenceResult(status="different")
    assert scoring.ai_confidence(eq, 3.0, 1.0, None, None, None).confidence == 0.0


class FakeProvider(LLMProvider):
    name = "fake"
    models = ["m1"]

    def __init__(self, answer: str):
        self.answer = answer

    def complete(self, model, system, user, temperature):
        assert "must_preserve_result" in user
        return LLMResult(text=self.answer, provider="fake", model=model, latency_ms=1.0)


def test_optimize_offline_pipeline(tmp_path, monkeypatch):
    from app.db import init_db
    from app.models import OptimizeRequest
    from app.services import pipeline
    init_db()
    answer = json.dumps({
        "summary": "Функция над колонкой", "issues": [{"type": "FUNCTION_ON_COLUMN", "severity": "high", "description": "x"}],
        "optimized_query": "SELECT id FROM orders WHERE created_at >= '2026-01-01' AND created_at < '2027-01-01';",
        "recommended_indexes": [], "explanation": ["диапазон вместо YEAR()"], "confidence": 0.9}, ensure_ascii=False)
    get_registry().register(FakeProvider(answer))
    resp = pipeline.optimize(OptimizeRequest(sql="SELECT id FROM orders WHERE YEAR(created_at) = 2026", dbms="mysql",
                                             ddl=DDL, model="fake:m1"))
    assert resp.verdict == "unverified"  # без БД — никаких метрик ускорения
    assert resp.comparison is None and resp.confidence.confidence is None
    assert resp.optimized_query.endswith("'2027-01-01'")
    assert resp.run_id

    get_registry().register(FakeProvider("я не умею в json"))
    resp = pipeline.optimize(OptimizeRequest(sql="SELECT id FROM orders", dbms="mysql", model="fake:m1"))
    assert resp.verdict == "rejected" and [e.value for e in resp.error_types] == ["INVALID_RESPONSE"]


class CapturingProvider(LLMProvider):
    name = "cap"
    models = ["m"]
    seen: list[str] = []

    def complete(self, model, system, user, temperature):
        CapturingProvider.seen.append(system + "\n" + user)
        return LLMResult(text='{"summary": "ok", "optimized_query": null}', provider="cap", model=model, latency_ms=1)


def test_noplan_prompt_hides_plan_and_plan_issues():
    from app.models import Issue
    ctx = {"dbms": "mysql", "version": "8", "query": "SELECT 1", "schema": {}, "constraints": {},
           "execution_plan": {"total_cost": 123456, "tree": {"type": "Full table scan"}},
           "detected_issues": [{"code": "FULL_TABLE_SCAN", "source": "plan"}, {"code": "SELECT_STAR", "source": "rule"}]}
    get_registry().register(CapturingProvider())
    CapturingProvider.seen.clear()
    ai.call_model(dict(ctx), "cap:m", "optimizer-v1", 0.1)
    ai.call_model(dict(ctx), "cap:m", "optimizer-v1-noplan", 0.1)
    with_plan, no_plan = CapturingProvider.seen
    assert "123456" in with_plan and "FULL_TABLE_SCAN" in with_plan
    assert "123456" not in no_plan and "execution_plan" not in no_plan and "FULL_TABLE_SCAN" not in no_plan
    assert "SELECT_STAR" in no_plan


def test_split_variant():
    from app.research.runner import split_variant
    assert split_variant("ollama:qwen:7b@optimizer-v1-noplan", "optimizer-v1") == ("ollama:qwen:7b", "optimizer-v1-noplan")
    assert split_variant("ollama:qwen:7b", "optimizer-v1") == ("ollama:qwen:7b", "optimizer-v1")
