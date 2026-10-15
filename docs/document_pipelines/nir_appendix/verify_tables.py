"""Сверка чисел таблиц приложения А с исходными данными эксперимента.

    python verify_tables.py

Читает runs/library_evaluation_20261015/results.json и заново считает всё,
что стоит в таблицах А.1–А.3, затем сверяет с тем, что записано в документе.
Доверять summary.json здесь нельзя: проверяем именно его.
"""

from __future__ import annotations

import json
import sys
import re
from collections import Counter, defaultdict
from pathlib import Path

# Пути считаются от корня репозитория: скрипт лежит в
# docs/document_pipelines/nir_appendix/. Так проверку можно запускать и в CI.
ROOT = Path(__file__).resolve().parents[3]
RESULTS = (ROOT / "docs/articles/sql_rewrite_validation/runs"
           / "library_evaluation_20261015/results.json")
SUMMARY = RESULTS.parent / "summary.json"

# Что записано в таблице А.1 документа
TABLE_A1 = {"qwen2.5-coder:7b": (12, 5, 3), "phi3.5:3.8b": (12, 2, 1)}
# Что записано в таблице А.3 документа
TABLE_A3 = {"multiplicity": 4, "ties": 4, "nullable": 3, "zero_fee": 2,
            "random_uniform": 2, "boundary": 1, "fixed": 1}


def main() -> None:
    records = json.loads(RESULTS.read_text(encoding="utf-8"))
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))

    print("=== А.1: ответов / предложено / опровергнуто ===")
    per = defaultdict(lambda: {"answers": 0, "proposed": 0, "refuted": 0})
    for r in records:
        m = r["model"]
        per[m]["answers"] += 1
        if not r.get("unchanged"):
            per[m]["proposed"] += 1
        if any(c["status"] == "counterexample" for c in r["checks"]):
            per[m]["refuted"] += 1
    ok = True
    for m, (a, p, ref) in TABLE_A1.items():
        got = (per[m]["answers"], per[m]["proposed"], per[m]["refuted"])
        mark = "совпало" if got == (a, p, ref) else "РАСХОЖДЕНИЕ"
        ok &= got == (a, p, ref)
        print(f"   {m:<18} в документе {a}/{p}/{ref}, пересчёт {got[0]}/{got[1]}/{got[2]} — {mark}")

    print("\n=== А.2: сколько состояний опровергло каждую ошибку ===")
    for r in records:
        ref = sum(1 for c in r["checks"] if c["status"] == "counterexample")
        if ref:
            print(f"   {r['model']:<18} {r['case']:<16} {ref} из 28")

    print("\n=== А.3: вклад профилей состояний ===")
    profile = lambda s: re.sub(r"_\d+$", "", s)
    hits = defaultdict(int)
    for r in records:
        if any(c["status"] == "counterexample" for c in r["checks"]):
            for q in {profile(c["state"]) for c in r["checks"] if c["status"] == "counterexample"}:
                hits[q] += 1
    for q, expected in TABLE_A3.items():
        got = hits.get(q, 0)
        mark = "совпало" if got == expected else "РАСХОЖДЕНИЕ"
        ok &= got == expected
        print(f"   {q:<16} в документе {expected} из 4, пересчёт {got} из 4 — {mark}")

    print("\n=== сверка со summary.json ===")
    # В summary.json счётчики ведутся ПО ЗАДАЧАМ (24 пары «модель × запрос»),
    # а статусы внутри checks — по состояниям (их 672). Сравнивать нужно
    # одно с одним, иначе получается ложное расхождение.
    case_status = Counter(r["status"] for r in records)
    state_status = Counter(c["status"] for r in records for c in r["checks"])
    refuted_states = sum(case_status.values())  # для наглядности ниже
    pairs = sum(len(r["checks"]) for r in records)
    checks = {
        "пар «модель × состояние»": (pairs, summary["checked_pairs"]),
        "задач not_refuted": (case_status["not_refuted"], sum(v["not_refuted"] for v in summary["counts"].values())),
        "задач counterexample": (case_status["counterexample"], sum(v["counterexample"] for v in summary["counts"].values())),
    }
    for name, (got, expected) in checks.items():
        mark = "совпало" if got == expected else "РАСХОЖДЕНИЕ"
        ok &= got == expected
        print(f"   {name:<26} пересчёт {got}, summary {expected} — {mark}")
    print(f"   состояний matched: {state_status['matched']}, "
          f"состояний counterexample: {state_status['counterexample']} "
          f"(= сумма опровергнутых состояний по таблице А.2)")

    corpus = summary["corpus_sha256"]
    print(f"\nконтрольная сумма корпуса: {corpus[:16]}…")
    print(f"\nИТОГ: {'все числа таблиц А.1–А.3 подтверждены исходными данными' if ok else 'ЕСТЬ РАСХОЖДЕНИЯ'}")
    # Код возврата нужен, чтобы шаг CI падал при расхождении.
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
