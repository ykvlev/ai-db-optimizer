"""Агрегация результатов эксперимента (ТЗ, п. 20–21) и простая статистика для научного отчёта."""

from __future__ import annotations

import math
import random
import statistics
from collections import Counter, defaultdict

OUTCOMES = ("improved", "unchanged", "worse", "invalid", "error")
OUTCOME_NAMES = {"improved": "Улучшено", "unchanged": "Без изменений", "worse": "Ухудшено", "invalid": "Некорректно",
                 "error": "Сбой вызова"}
HALLUCINATIONS = {"WRONG_TABLE", "WRONG_COLUMN", "INDEX_HALLUCINATION", "SCHEMA_HALLUCINATION"}


def classify(verdict: str, error_types: list[str], ai_error: str | None, equivalent: bool | None) -> str:
    if verdict == "accepted":
        return "improved"
    if verdict == "no_change":
        return "unchanged"
    if verdict == "failed" and ai_error:
        return "error"  # сбой инфраструктуры (сеть, ключ, таймаут LLM), а не ошибка модели
    if verdict == "rejected" and equivalent and "PERFORMANCE_REGRESSION" in error_types:
        return "worse"
    return "invalid"


def geomean(xs: list[float]) -> float | None:
    xs = [x for x in xs if x and x > 0]
    return math.exp(statistics.fmean(math.log(x) for x in xs)) if xs else None


def bootstrap_ci(xs: list[float], stat=statistics.median, n: int = 2000, alpha: float = 0.05,
                 seed: int = 42) -> tuple[float, float] | None:
    """Перцентильный bootstrap-интервал (фиксированный seed — для воспроизводимости отчёта)."""
    if len(xs) < 3:
        return None
    rnd = random.Random(seed)
    vals = sorted(stat([rnd.choice(xs) for _ in xs]) for _ in range(n))
    return vals[int(n * alpha / 2)], vals[int(n * (1 - alpha / 2)) - 1]


def _r(x: float | None, nd: int = 3) -> float | None:
    return round(x, nd) if x is not None else None


def summarize(rows: list[dict]) -> dict:
    """rows: dict с ключами model, outcome, proposed, executed, equivalent, speedup, error_types, latency_ms,
    prompt_tokens, completion_tokens, category."""
    by_model: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_model[r["model"]].append(r)
    models = {}
    for model, rs in by_model.items():
        n = len(rs)
        cnt = Counter(r["outcome"] for r in rs)
        proposed = [r for r in rs if r["proposed"]]
        eq_speedups = [r["speedup"] for r in rs if r["equivalent"] and r["speedup"]]
        improved_speedups = [r["speedup"] for r in rs if r["outcome"] == "improved" and r["speedup"]]
        errors = Counter(e for r in rs for e in (r["error_types"] or []))
        lat = [r["latency_ms"] for r in rs if r["latency_ms"] is not None and r["outcome"] != "error"]
        ci = bootstrap_ci(eq_speedups)
        models[model] = {
            "n": n,
            "outcomes": {o: cnt.get(o, 0) for o in OUTCOMES},
            "outcomes_pct": {o: _r(100 * cnt.get(o, 0) / n, 1) for o in OUTCOMES},
            "proposed": len(proposed),
            "proposed_pct": _r(100 * len(proposed) / n, 1),
            # доли среди запросов, где модель предложила изменённый SQL
            "correct_sql_pct": _r(100 * sum(r["executed"] for r in proposed) / len(proposed), 1) if proposed else None,
            "equivalent_pct": _r(100 * sum(bool(r["equivalent"]) for r in proposed) / len(proposed), 1) if proposed else None,
            "faster_pct": _r(100 * sum(r["outcome"] == "improved" for r in proposed) / len(proposed), 1) if proposed else None,
            "median_speedup": _r(statistics.median(eq_speedups)) if eq_speedups else None,
            "median_speedup_ci95": [_r(ci[0]), _r(ci[1])] if ci else None,
            "mean_speedup": _r(statistics.fmean(eq_speedups)) if eq_speedups else None,
            "geomean_speedup": _r(geomean(eq_speedups)),
            "median_speedup_improved": _r(statistics.median(improved_speedups)) if improved_speedups else None,
            "max_speedup": _r(max(eq_speedups)) if eq_speedups else None,
            "regressions": cnt.get("worse", 0),
            "hallucinations": sum(v for k, v in errors.items() if k in HALLUCINATIONS),
            "error_types": dict(errors.most_common()),
            "avg_latency_ms": _r(statistics.fmean(lat), 1) if lat else None,
            "prompt_tokens": sum(r["prompt_tokens"] or 0 for r in rs),
            "completion_tokens": sum(r["completion_tokens"] or 0 for r in rs),
        }
    categories: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        c = categories[r["category"]].setdefault(r["model"], {"n": 0, "improved": 0, "invalid": 0, "worse": 0})
        c["n"] += 1
        if r["outcome"] in c:
            c[r["outcome"]] += 1
    return {"models": models, "categories": categories}
