"""Оценка ответов участников эксперимента «ИИ против человека» тем же способом, что и ответов моделей.

    python docs/human_study/evaluate_humans.py answers.csv [--connection 2] [--experiment 7]

answers.csv (UTF-8): participant,experience,task,sql
  participant — анонимный код (например, P01); experience — опыт работы с SQL в годах;
  task — ключ запроса (например, not_in-1); sql — переписанный запрос или пусто, если участник оставил запрос без изменений.

Для каждого ответа выполняется сравнение с исходным запросом на той же базе (POST /api/query/compare): проверка
совпадения результата и бенчмарк. Исходы определяются по тем же порогам, что и для моделей (улучшено ≥ 1,05,
ухудшено < 0,95). Результаты сопоставляются с ответами моделей из эксперимента (по умолчанию 7, MySQL).
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
TASKS = json.loads((HERE / "tasks.json").read_text(encoding="utf-8"))


def outcome(cmp_: dict) -> str:
    eq = (cmp_.get("equivalence") or {}).get("status")
    if eq != "equivalent":
        return "invalid"
    sp = cmp_.get("speedup") or 1.0
    return "improved" if sp >= 1.05 else ("worse" if sp < 0.95 else "unchanged")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("answers")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--connection", type=int, default=2)
    ap.add_argument("--experiment", type=int, default=7)
    a = ap.parse_args()
    c = httpx.Client(base_url=a.api, timeout=600)
    original = {t["key"]: t["sql"] for t in TASKS}
    rows = []
    with open(a.answers, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            key, sql = r["task"].strip(), (r.get("sql") or "").strip().rstrip(";")
            rec = {"participant": r["participant"], "experience": r.get("experience", ""), "task": key, "proposed": bool(sql)}
            if not sql:
                rec.update(outcome="unchanged", speedup=None, note="без изменений")
            else:
                resp = c.post("/api/query/compare", json={"original_sql": original[key], "optimized_sql": sql, "connection_id": a.connection})
                if resp.status_code != 200:
                    rec.update(outcome="invalid", speedup=None, note=resp.json().get("detail", resp.text)[:200])
                else:
                    cmp_ = resp.json()
                    rec.update(outcome=outcome(cmp_), speedup=cmp_.get("speedup"),
                               note=f"строк {cmp_['equivalence'].get('rows_original')}/{cmp_['equivalence'].get('rows_optimized')}")
            rows.append(rec)
            print(rec["participant"], key, rec["outcome"], rec["speedup"], rec["note"], flush=True)

    out = HERE / "results_humans.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # сводка: люди и модели на тех же задачах
    keys = [t["key"] for t in TASKS]
    models = defaultdict(dict)
    for r in c.get(f"/api/experiments/{a.experiment}").json()["results"]:
        if r["key"] in keys:
            models[r["model"]][r["key"]] = r["outcome"]
    summary = {}
    by_p = defaultdict(list)
    for r in rows:
        by_p[r["participant"]].append(r["outcome"])
    for p_, outs in by_p.items():
        summary[p_] = {o: outs.count(o) for o in ("improved", "unchanged", "worse", "invalid")}
    for m, d in models.items():
        outs = list(d.values())
        summary[m] = {o: outs.count(o) for o in ("improved", "unchanged", "worse", "invalid")}
    (HERE / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nрезультаты: {out}\nсводка:")
    for k, v in summary.items():
        print(f"  {k:32} {v}")


if __name__ == "__main__":
    main()
