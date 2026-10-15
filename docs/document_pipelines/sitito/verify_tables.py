"""Сверка таблиц 1–5 рукописи МГУ с исходными данными experiments.

    python verify_tables.py

Данные: ai-db-optimizer/docs/nir/data.json (опыты 7–11) и
runs/library_evaluation_20261015/results.json (замороженный корпус).

Ключевая деталь: один и тот же запрос проходит и на MySQL (опыт 7), и на
PostgreSQL (опыт 8), поэтому задачи считаются парами «запрос × СУБД», а не
уникальными запросами. Если считать по ключу запроса, числа занижаются.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Пути считаются от корня репозитория: скрипт лежит в docs/document_pipelines/sitito/.
# Так проверку можно запускать и в CI, где рабочих путей нет. Раньше здесь были
# абсолютные пути, и скрипт работал только на машине автора.
ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "docs/nir/data.json"
LIB = (ROOT / "docs/articles/sql_rewrite_validation/runs"
       / "library_evaluation_20261015/results.json")

NAME = {"gigachat:GigaChat-2": "GigaChat-2", "gigachat:GigaChat-2-Pro": "GigaChat-2-Pro",
        "gigachat:GigaChat-2-Max": "GigaChat-2-Max",
        "ollama:qwen2.5-coder:7b": "Qwen2.5-Coder 7B", "baseline:rule-based": "Правила"}

T2 = {"GigaChat-2": (23, 11, 21, 21, 4), "GigaChat-2-Pro": (29, 18, 17, 16, 0),
      "GigaChat-2-Max": (14, 53, 11, 2, 0), "Qwen2.5-Coder 7B": (16, 58, 4, 2, 0),
      "Правила": (17, 59, 4, 0, 0)}
T3 = {"GigaChat-2": (9, 8, 14, 13), "GigaChat-2-Pro": (13, 11, 16, 5),
      "GigaChat-2-Max": (5, 2, 9, 0), "Qwen2.5-Coder 7B": (10, 1, 6, 1),
      "Правила": (8, 0, 9, 0)}
T4 = {"GigaChat-2": (13, 10, 4, 27), "GigaChat-2-Pro": (15, 14, 2, 31),
      "GigaChat-2-Max": (11, 3, 6, 20), "Qwen2.5-Coder 7B": (12, 4, 5, 21)}
T5 = {"gigachat:GigaChat-2-Pro": (32, 12, 16), "gigachat:GigaChat-2-Max": (34, 4, 8)}
T6 = {"qwen2.5-coder:7b": (12, 5, 3, 9, 336), "phi3.5:3.8b": (12, 2, 1, 11, 336)}


def report(title: str, ok: bool) -> None:
    print(f"   -> {title}: {'совпало' if ok else 'ЕСТЬ РАСХОЖДЕНИЯ'}\n")


def main() -> None:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    everything = True

    print("=== ТАБЛИЦА 1: исходы на 80 задачах ===")
    per = defaultdict(Counter)
    for ek in ("7", "8"):
        for r in data["exp"][ek]["results"]:
            per[r["model"]][r["outcome"]] += 1
    ok = True
    for raw, name in NAME.items():
        c = per[raw]
        got = (c["improved"], c["unchanged"], c["worse"], c["invalid"], c["error"])
        ok &= got == T2[name]
        print(f"   {name:<20} {got}  в документе {T2[name]}")
    everything &= ok
    report("таблица 1", ok)

    print("=== ТАБЛИЦА 2: по СУБД (ускорение и некорректные исходы) ===")
    ok = True
    for raw, name in NAME.items():
        vals = []
        for ek in ("7", "8"):
            c = Counter(r["outcome"] for r in data["exp"][ek]["results"] if r["model"] == raw)
            vals += [c["improved"], c["invalid"]]
        ok &= tuple(vals) == T3[name]
        print(f"   {name:<20} {tuple(vals)}  в документе {T3[name]}")
    everything &= ok
    report("таблица 2", ok)

    def improved(ek: str, model: str) -> set:
        return {(ek, r["key"]) for r in data["exp"][ek]["results"]
                if r["model"] == model and r["outcome"] == "improved"}

    print("=== ТАБЛИЦА 3: пересечение с правилами ===")
    rules = improved("7", "baseline:rule-based") | improved("8", "baseline:rule-based")
    ok = True
    for raw, name in NAME.items():
        if raw == "baseline:rule-based":
            continue
        m = improved("7", raw) | improved("8", raw)
        got = (len(m & rules), len(m - rules), len(rules - m), len(m | rules))
        ok &= got == T4[name]
        print(f"   {name:<20} {got}  в документе {T4[name]}")
    everything &= ok
    report("таблица 3", ok)

    print("=== ТАБЛИЦА 4: устойчивость трёх прогонов ===")
    ok = True
    for raw, expected in T5.items():
        runs = [{r["key"]: r["outcome"] for r in data["exp"][ek]["results"] if r["model"] == raw}
                for ek in ("7", "9", "10")]
        keys = set(runs[0]) & set(runs[1]) & set(runs[2])
        got = (sum(1 for k in keys if runs[0][k] == runs[1][k] == runs[2][k]),
               sum(1 for k in keys if all(x[k] == "improved" for x in runs)),
               sum(1 for k in keys if any(x[k] == "improved" for x in runs)))
        ok &= got == expected
        print(f"   {raw.split(':')[-1]:<20} {got}  в документе {expected}")
    everything &= ok
    report("таблица 4", ok)

    print("=== ТАБЛИЦА 5: замороженный корпус ===")
    records = json.loads(LIB.read_text(encoding="utf-8"))
    ok = True
    for model, (answers, proposed, refuted, clean, checks) in T6.items():
        rows = [r for r in records if r["model"] == model]
        got = (len(rows),
               sum(1 for r in rows if not r.get("unchanged")),
               sum(1 for r in rows if any(c["status"] == "counterexample" for c in r["checks"])),
               sum(1 for r in rows if r["status"] == "not_refuted"),
               sum(len(r["checks"]) for r in rows))
        ok &= got == (answers, proposed, refuted, clean, checks)
        print(f"   {model:<20} {got}  в документе {(answers, proposed, refuted, clean, checks)}")
    everything &= ok
    report("таблица 5", ok)

    print("ИТОГ:", "все пять таблиц подтверждены исходными данными"
          if everything else "ЕСТЬ РАСХОЖДЕНИЯ")
    # Код возврата нужен, чтобы шаг CI падал при расхождении, а не просто печатал текст.
    return 0 if everything else 1


if __name__ == "__main__":
    raise SystemExit(main())
