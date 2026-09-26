"""Optimization Score (0–100) и AI Confidence, рассчитываемые только из измеренных данных.

Если данных для компонента нет — компонент исключается, а веса оставшихся нормируются.
Если нет ни эквивалентности, ни бенчмарка — score не рассчитывается вовсе (никаких «фейковых» метрик).
"""

from __future__ import annotations

import math
import re

from app.config import load_scoring_config
from app.models import (AIResponse, BenchmarkStats, ConfidenceFactor, ConfidenceResult, EquivalenceResult, Issue,
                        PlanSummary, ScoreComponent, ScoreResult)
from app.services.explain import index_usage_ratio


def _ratio_score(before: float | None, after: float | None) -> float | None:
    """1x → 50, 10x лучше → 100, 10x хуже → 0 (логарифмическая шкала)."""
    if before is None or after is None or before <= 0:
        return None
    ratio = before / max(after, 1e-9)
    return max(0.0, min(100.0, 50 + 50 * math.log10(ratio)))


def optimization_score(eq: EquivalenceResult | None, b0: BenchmarkStats | None, b1: BenchmarkStats | None,
                       p0: PlanSummary | None, p1: PlanSummary | None,
                       nodes_before: int | None, nodes_after: int | None) -> ScoreResult:
    if eq is None or b0 is None or b1 is None:
        return ScoreResult(score=None, note="Score рассчитывается только после выполнения запросов на реальной БД")
    if eq.status != "equivalent":
        return ScoreResult(score=0.0, note="Результат запроса изменился — оптимизация отклонена")
    weights = load_scoring_config()["weights"]
    comps: list[ScoreComponent] = []

    def add(name: str, value: float | None, detail: str):
        if value is not None and name in weights:
            comps.append(ScoreComponent(name=name, value=round(value, 1), weight=weights[name], detail=detail))

    add("speed", _ratio_score(b0.median_ms, b1.median_ms), f"медиана {b0.median_ms:.2f} → {b1.median_ms:.2f} мс")
    if p0 and p1:
        add("query_cost", _ratio_score(p0.total_cost, p1.total_cost), f"cost {p0.total_cost} → {p1.total_cost}")
        r0, r1 = index_usage_ratio(p0), index_usage_ratio(p1)
        if r0 is not None and r1 is not None:
            add("index_usage", 50 + 50 * (r1 - r0), f"доля индексных доступов {r0:.0%} → {r1:.0%}")
    e0 = b0.rows_examined if b0.rows_examined is not None else (p0.estimated_rows_examined if p0 else None)
    e1 = b1.rows_examined if b1.rows_examined is not None else (p1.estimated_rows_examined if p1 else None)
    if e0 is not None and e1 is not None:
        add("rows_examined", _ratio_score(max(e0, 1), max(e1, 1)), f"{e0:,.0f} → {e1:,.0f}".replace(",", " "))
    if b1.mean_ms > 0:
        cv = b1.stdev_ms / b1.mean_ms
        add("stability", 100 * (1 - min(cv, 1.0)), f"коэф. вариации {cv:.1%}")
    if nodes_before and nodes_after:
        add("complexity", max(0.0, min(100.0, 50 + 50 * (nodes_before - nodes_after) / nodes_before)),
            f"узлов AST {nodes_before} → {nodes_after}")

    total_w = sum(c.weight for c in comps)
    if not total_w:
        return ScoreResult(score=None, components=comps, note="Недостаточно данных")
    score = sum(c.value * c.weight for c in comps) / total_w
    return ScoreResult(score=round(score, 1), components=comps)


def _norm(s: str) -> set[str]:
    return set(re.findall(r"[a-z]+", s.lower().replace("_", " ")))


def rule_ai_agreement(detected: list[Issue], ai: AIResponse | None) -> float | None:
    important = {i.code for i in detected if i.severity in ("critical", "high", "medium")}
    if not important or ai is None:
        return None
    ai_types = [i.type for i in ai.issues]
    hit = 0
    for code in important:
        cw = _norm(code)
        if any(t.upper() == code or len(cw & _norm(t)) >= max(1, len(cw) - 1) for t in ai_types):
            hit += 1
    return hit / len(important)


def ai_confidence(eq: EquivalenceResult | None, speedup: float | None, agreement: float | None,
                  p0: PlanSummary | None, p1: PlanSummary | None, b1: BenchmarkStats | None) -> ConfidenceResult:
    w = load_scoring_config()["confidence_weights"]
    f: list[ConfidenceFactor] = []
    if eq is not None and eq.status in ("equivalent", "different"):
        v = 0.0 if eq.status == "different" else (0.5 if eq.order_match is False else 1.0)
        f.append(ConfidenceFactor(name="equivalence", value=v, weight=w["equivalence"],
                                  detail={1.0: "результат совпал", 0.5: "совпал набор строк, порядок отличается",
                                          0.0: "результат изменился"}[v]))
    if speedup is not None:
        v = 1.0 if speedup >= 1.1 else (0.5 if speedup >= 0.95 else 0.0)
        f.append(ConfidenceFactor(name="real_speedup", value=v, weight=w["real_speedup"], detail=f"ускорение {speedup:.2f}x"))
    if agreement is not None:
        f.append(ConfidenceFactor(name="rule_ai_agreement", value=agreement, weight=w["rule_ai_agreement"],
                                  detail=f"ИИ подтвердил {agreement:.0%} проблем, найденных правилами и планом"))
    if p0 and p1 and p0.total_cost and p1.total_cost:
        fewer_scans = len(p1.full_scans) < len(p0.full_scans)
        v = 1.0 if (p1.total_cost < p0.total_cost * 0.95 or fewer_scans) else (0.5 if p1.total_cost <= p0.total_cost * 1.05 else 0.0)
        f.append(ConfidenceFactor(name="plan_confirmed", value=v, weight=w["plan_confirmed"],
                                  detail=f"cost плана {p0.total_cost:g} → {p1.total_cost:g}, полных сканирований "
                                         f"{len(p0.full_scans)} → {len(p1.full_scans)}"))
    if b1 is not None and b1.mean_ms > 0:
        cv = b1.stdev_ms / b1.mean_ms
        f.append(ConfidenceFactor(name="benchmark_stability", value=max(0.0, 1 - min(cv, 1.0)),
                                  weight=w["benchmark_stability"], detail=f"коэф. вариации {cv:.1%}"))
    total = sum(x.weight for x in f)
    if not total or eq is None or eq.status not in ("equivalent", "different"):
        # без фактической проверки результата уверенность не рассчитываем
        return ConfidenceResult(confidence=None, factors=f)
    if eq is not None and eq.status == "different":
        return ConfidenceResult(confidence=0.0, factors=f)
    return ConfidenceResult(confidence=round(sum(x.value * x.weight for x in f) / total, 3), factors=f)
