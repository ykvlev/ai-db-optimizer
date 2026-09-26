"""AI-модуль: построение структурированного контекста, вызов LLM, разбор и валидация ответа."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache

from pydantic import ValidationError
from sqlglot import exp

from app.config import PROMPTS_DIR
from app.models import AIResponse, Dialect, ErrorType, Issue, PlanNode, PlanSummary, SchemaInfo
from app.services import safety
from app.services.ai.providers import LLMResult, get_registry
from app.services.sql_parser import SQLParseError, cte_names, parse, real_tables

DEFAULT_PROMPT = "optimizer-v1"


@dataclass
class PromptTemplate:
    id: str
    system: str
    user: str
    sha256: str


@lru_cache
def load_prompt(prompt_id: str = DEFAULT_PROMPT) -> PromptTemplate:
    if not re.fullmatch(r"[\w.-]+", prompt_id):
        raise ValueError("Недопустимый идентификатор промпта")
    raw = (PROMPTS_DIR / f"{prompt_id}.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    return PromptTemplate(id=data["id"], system=data["system"], user=data["user"],
                          sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest())


def list_prompts() -> list[str]:
    return sorted(p.stem for p in PROMPTS_DIR.glob("*.json"))


def _compact_plan(node: PlanNode | None, depth: int = 0) -> dict | None:
    if node is None or depth > 12:
        return None
    d = {k: v for k, v in {"type": node.type, "table": node.table, "index": node.index, "rows": node.rows,
                           "actual_rows": node.actual_rows, "cost": node.cost, "time_ms": node.time_ms,
                           "filter": node.filter, "extra": node.extra or None}.items() if v is not None}
    if node.children:
        d["children"] = [_compact_plan(c, depth + 1) for c in node.children]
    return d


def build_context(sql: str, dialect: Dialect, version: str | None, schema: SchemaInfo, plan: PlanSummary | None,
                  issues: list[Issue], tables_used: list[str]) -> dict:
    used = {t.lower() for t in tables_used}
    tables = [t for t in schema.tables if t.name.lower() in used] or schema.tables[:30]
    return {
        "dbms": dialect,
        "version": version or "unknown",
        "query": sql,
        "schema": {"source": schema.source, "tables": [
            {"name": t.name, "row_count": t.row_count,
             "columns": [{"name": c.name, "type": c.type, "nullable": c.nullable} for c in t.columns],
             "indexes": [{"name": i.name, "columns": i.columns, "unique": i.unique} for i in t.indexes],
             "foreign_keys": [{"columns": f.columns, "ref_table": f.ref_table, "ref_columns": f.ref_columns}
                              for f in t.foreign_keys]} for t in tables]},
        "execution_plan": {"total_cost": plan.total_cost, "tree": _compact_plan(plan.root),
                           "uses_filesort": plan.uses_filesort, "uses_temporary": plan.uses_temporary}
        if plan else None,
        "detected_issues": [{"code": i.code, "severity": i.severity, "title": i.title, "fragment": i.fragment}
                            for i in issues if i.code != "RULE_ERROR"],
        "constraints": {"must_preserve_result": True, "read_only": True, "single_statement": True},
    }


def extract_json(text: str) -> dict:
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
    if fence:
        t = fence.group(1).strip()
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("В ответе модели нет JSON-объекта")
    return json.loads(t[start:end + 1])


@dataclass
class AIRunResult:
    response: AIResponse | None
    llm: LLMResult | None
    prompt: PromptTemplate
    system_prompt: str
    user_prompt: str
    error: str | None = None
    error_types: list[ErrorType] | None = None


def call_model(context: dict, model_id: str | None, prompt_id: str | None, temperature: float) -> AIRunResult:
    prompt = load_prompt(prompt_id or DEFAULT_PROMPT)
    system = prompt.system.replace("{dbms}", context["dbms"]).replace("{version}", str(context["version"]))
    user = prompt.user.replace("{context_json}", json.dumps(context, ensure_ascii=False, separators=(",", ":"), default=str))
    provider, model = get_registry().resolve(model_id)
    llm = provider.complete(model, system, user, temperature)
    try:
        data = extract_json(llm.text)
        if isinstance(data.get("optimized_query"), str):
            data["optimized_query"] = data["optimized_query"].strip().rstrip(";").strip() or None
        resp = AIResponse.model_validate(data)
    except (ValueError, ValidationError) as e:
        return AIRunResult(None, llm, prompt, system, user, error=f"Ответ модели не соответствует формату: {e}",
                           error_types=[ErrorType.INVALID_RESPONSE])
    return AIRunResult(resp, llm, prompt, system, user, error_types=[])


BASELINE_MODEL = "baseline:rule-based"


def baseline_run(parsed) -> AIRunResult:
    """Детерминированная базовая линия: тот же конвейер проверки, но кандидат строит rule-based rewriter."""
    import time
    from app.services import rewriter
    t0 = time.perf_counter()
    sql, notes = rewriter.rewrite(parsed)
    resp = AIResponse(summary="Rule-based переписывание" if sql else "Правила переписывания не применимы",
                      optimized_query=sql, explanation=notes)
    llm = LLMResult(text=resp.model_dump_json(), provider="baseline", model="rule-based",
                    latency_ms=(time.perf_counter() - t0) * 1000)
    prompt = PromptTemplate(id="none", system="", user="", sha256="")
    return AIRunResult(resp, llm, prompt, "", "", error_types=[])


def validate_ai_output(resp: AIResponse, original_sql: str, dialect: Dialect, schema: SchemaInfo) \
        -> tuple[list[ErrorType], list[str], "safety.SafetyVerdict | None"]:
    """Статическая проверка ответа модели до выполнения. Возвращает (типы ошибок, пояснения, вердикт safety)."""
    errors: list[ErrorType] = []
    notes: list[str] = []
    verdict = None
    sql = resp.optimized_query
    if sql:
        verdict = safety.check(sql, dialect)
        if not verdict.allowed:
            try:
                parse(sql, dialect)
                errors.append(ErrorType.DANGEROUS_QUERY)
            except SQLParseError:
                errors.append(ErrorType.SYNTAX_ERROR)
            notes += verdict.reasons
        else:
            p = parse(sql, dialect)
            if schema.tables:
                ctes = cte_names(p.ast)
                for t in real_tables(p.ast):
                    if schema.table(t.name) is None and t.name.lower() not in ctes:
                        errors.append(ErrorType.WRONG_TABLE)
                        notes.append(f"Таблица {t.name} отсутствует в схеме")
                aliases = {a.lower(): r for a, r in p.info.table_aliases.items()}
                derived = {s.alias_or_name.lower() for s in p.ast.find_all(exp.Subquery) if s.alias_or_name}
                for c in p.ast.find_all(exp.Column):
                    if not c.table or c.table.lower() in derived or c.table.lower() in ctes:
                        continue
                    table = schema.table(aliases.get(c.table.lower(), c.table))
                    if table is not None and c.name and table.column(c.name) is None:
                        errors.append(ErrorType.WRONG_COLUMN)
                        notes.append(f"Колонка {c.table}.{c.name} отсутствует в таблице {table.name}")
                for t in real_tables(p.ast):
                    table = schema.table(t.name)
                    for hint in t.args.get("hints") or []:
                        if isinstance(hint, exp.IndexTableHint) and table is not None:
                            existing = {i.name.lower() for i in table.indexes}
                            for ident in hint.expressions:
                                if ident.name.lower() not in existing:
                                    errors.append(ErrorType.INDEX_HALLUCINATION)
                                    notes.append(f"Подсказка использует несуществующий индекс {ident.name}")
    if schema.tables:
        for rec in resp.recommended_indexes:
            table = schema.table(rec.table)
            if table is None:
                errors.append(ErrorType.SCHEMA_HALLUCINATION)
                notes.append(f"Индекс рекомендован для несуществующей таблицы {rec.table}")
                continue
            missing = [c for c in rec.columns if table.column(c) is None]
            if missing:
                errors.append(ErrorType.SCHEMA_HALLUCINATION)
                notes.append(f"Индекс по несуществующим колонкам {table.name}: {', '.join(missing)}")
            elif any([c.lower() for c in i.columns[: len(rec.columns)]] == [c.lower() for c in rec.columns]
                     for i in table.indexes):
                notes.append(f"Рекомендованный индекс {table.name}({', '.join(rec.columns)}) уже покрыт существующим")
    return list(dict.fromkeys(errors)), notes, verdict


def same_query(a: str, b: str, dialect: Dialect) -> bool:
    try:
        return parse(a, dialect).info.normalized_sql == parse(b, dialect).info.normalized_sql
    except SQLParseError:
        return False
