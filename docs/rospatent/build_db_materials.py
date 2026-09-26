"""Формирует материалы, идентифицирующие базу данных, для регистрации в Роспатенте.

    python docs/rospatent/build_db_materials.py

Результат (docs/rospatent/out/):
  db_full.html / .pdf     — описание структуры и полное содержание БД (для архива автора)
  db_deposit.html / .pdf  — первые 25 и последние 25 листов (депонируемые материалы)

Содержание берётся из выгруженного датасета dataset/sql-optimization-dataset-v1 (backend/scripts/export_dataset.py).
"""

from __future__ import annotations

import importlib.util
import json
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DS = ROOT / "dataset" / "sql-optimization-dataset-v1"

spec = importlib.util.spec_from_file_location("listing", HERE / "build_listing.py")
lst = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lst)
lst.TITLE = "SQL Optimization Dataset"
lst.SUBTITLE = "База данных результатов интеллектуальной оптимизации SQL-запросов"
W = lst.WIDTH

FIELDS = [
    ("record_id", "идентификатор записи: e<эксперимент>-<запрос>-<участник>"),
    ("experiment_id", "номер эксперимента (связь с файлом experiments.json)"),
    ("dbms, dbms_version", "СУБД и её версия"),
    ("query_set, database_seed", "версия набора запросов и испытательных данных"),
    ("query_key, category, title", "идентификатор, категория и название запроса (связь с queries.csv)"),
    ("participant, participant_type", "участник: языковая модель (llm) или правила (rule_based)"),
    ("prompt_version, prompt_sha256", "версия промпта и контрольная сумма его файла"),
    ("original_sql", "исходный SQL-запрос"),
    ("candidate_sql", "предложенный вариант запроса или null"),
    ("proposed, executed", "кандидат отличается от исходного; кандидат выполнен без ошибок"),
    ("outcome", "исход: improved, unchanged, worse, invalid, error"),
    ("verdict, verdict_reason", "решение системы проверки и его причина"),
    ("error_types", "типы ошибок кандидата (RESULT_CHANGED, PERFORMANCE_REGRESSION и др.)"),
    ("detected_issues", "коды проблем, найденных детерминированным анализатором"),
    ("equivalence", "статус проверки, число строк и контрольные суммы результатов"),
    ("speedup, time_before_ms, time_after_ms", "ускорение и медианы времени выполнения"),
    ("benchmark_original, benchmark_candidate", "все замеры времени, прогрев, статистика, прочитанные строки"),
    ("plan_original, plan_candidate, plan_changes", "планы выполнения до и после, перечень изменений"),
    ("llm_summary, llm_explanation", "пояснение языковой модели"),
    ("llm_self_confidence, llm_recommended_indexes", "самооценка модели и рекомендованные индексы"),
    ("latency_ms, prompt_tokens, completion_tokens", "время ответа модели и объём в токенах"),
]


def wrap(text: str, indent: str = "") -> list[str]:
    out = []
    for line in str(text).split("\n"):
        out += textwrap.wrap(line, W, initial_indent=indent, subsequent_indent=indent + "  ",
                             drop_whitespace=False, replace_whitespace=False) or [indent]
    return out


def structure() -> list[str]:
    stats = json.loads((DS / "stats.json").read_text(encoding="utf-8"))
    exps = json.loads((DS / "experiments.json").read_text(encoding="utf-8"))
    L = ["РАЗДЕЛ 1. СТРУКТУРА БАЗЫ ДАННЫХ", ""]
    L += wrap(f"База данных содержит {stats['records']} записей о результатах оптимизации SQL-запросов, полученных в "
              f"{stats['experiments']} экспериментах, {stats['queries']} уникальных запросов и сведения об экспериментах. "
              "Одна запись соответствует паре «SQL-запрос × участник» в одном эксперименте. Данные хранятся в текстовых "
              "файлах в кодировке UTF-8 и связаны идентификаторами.")
    L += ["", "Состав файлов:",
          "  records.jsonl     основная таблица: записи о результатах (одна JSON-строка на запись)",
          "  records.csv       основная таблица в плоском виде",
          "  llm_io.jsonl      промпты и ответы языковой модели (связь по record_id)",
          "  queries.csv       справочник запросов (связь по query_set, dbms, query_key)",
          "  experiments.json  справочник экспериментов (связь по experiment_id)",
          "  schema/, prompts/ схема испытательной БД и версии промптов",
          "", "Поля основной таблицы records:"]
    for k, v in FIELDS:
        L += wrap(f"  {k:<45} {v}")
    L += ["", "Эксперименты:"]
    for e in exps:
        L += wrap(f"  {e['experiment_id']}. {e['name']} | {e['dbms']} {e['dbms_version']} | набор {e['query_set']} | "
                  f"участники: {', '.join(e['participants'])}")
    L += ["", "Распределение исходов: " + ", ".join(f"{k} – {v}" for k, v in stats["outcomes"].items()), "",
          "РАЗДЕЛ 2. СОДЕРЖАНИЕ БАЗЫ ДАННЫХ (ЗАПИСИ ТАБЛИЦЫ records)", ""]
    return L


def records() -> list[str]:
    L = []
    rows = [json.loads(s) for s in (DS / "records.jsonl").read_text(encoding="utf-8").splitlines() if s.strip()]
    for n, r in enumerate(rows, 1):
        eq = r["equivalence"] or {}
        L.append(f"---- Запись {n} из {len(rows)}: {r['record_id']} " + "-" * max(0, W - 30 - len(r["record_id"])))
        L += wrap(f"Эксперимент {r['experiment_id']} | {r['dbms']} {r['dbms_version']} | {r['query_set']} | "
                  f"запрос {r['query_key']} ({r['category']}): {r['title']}")
        L += wrap(f"Участник: {r['participant']} | промпт: {r['prompt_version'] or '—'} | исход: {r['outcome']} | "
                  f"решение: {r['verdict']} | ошибки: {', '.join(r['error_types']) or 'нет'}")
        if r["speedup"] is not None:
            L += wrap(f"Время: {r['time_before_ms']:.2f} мс → {r['time_after_ms']:.2f} мс, ускорение {r['speedup']}x | "
                      f"эквивалентность: {eq.get('status')}, строк {eq.get('rows_original')} / {eq.get('rows_optimized')}")
        L += wrap(f"Проблемы анализатора: {', '.join(r['detected_issues']) or 'нет'}")
        L.append("Исходный запрос:")
        L += wrap(r["original_sql"], "  ")
        if r["candidate_sql"]:
            L.append("Предложенный запрос:")
            L += wrap(r["candidate_sql"], "  ")
        L.append("")
    return L


def main():
    lst.OUT.mkdir(exist_ok=True)
    lines = structure() + records()
    pages = lst.paginate(lines)
    total = len(pages)
    numbered = list(enumerate(pages, 1))
    full = lst.OUT / "db_full.html"
    full.write_text(lst.render(numbered, total), encoding="utf-8")
    h, t = lst.DEPOSIT_HEAD, lst.DEPOSIT_TAIL
    note = f"Листы {h + 1}–{total - t} опущены (представлены первые {h} и последние {t} листов из {total})"
    dep = numbered[:h] + [(-1, [])] + numbered[-t:] if total > h + t else numbered
    deposit = lst.OUT / "db_deposit.html"
    deposit.write_text(lst.render(dep, total, note), encoding="utf-8")
    size = sum(p.stat().st_size for p in DS.rglob("*") if p.is_file())
    print(f"листов: {total}, объём БД: {size / 1024 / 1024:.2f} МБ")
    for p in (full, deposit):
        print("создан", lst.to_pdf(p) or p)


if __name__ == "__main__":
    main()
