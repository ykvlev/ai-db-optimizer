"""Формирует листинг исходного текста для депонирования в Роспатенте.

    python docs/rospatent/build_listing.py

Результат (docs/rospatent/out/):
  listing_full.html / .pdf     — полный исходный текст (для архива автора)
  listing_deposit.html / .pdf  — первые 25 и последние 25 страниц (депонируемые материалы)

Страницы размечаются вручную (фиксированное число строк), поэтому нумерация в HTML и PDF совпадает.
PDF печатается локальным Microsoft Edge в headless-режиме.
"""

from __future__ import annotations

import html
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "out"
TITLE = "AI Database Optimizer"
SUBTITLE = "Интеллектуальная система анализа и оптимизации SQL-запросов в реляционных базах данных"
LINES_PER_PAGE = 64
WIDTH = 118
DEPOSIT_HEAD, DEPOSIT_TAIL = 25, 25

# Порядок: сначала ядро (идентифицирует программу), в конце — интерфейс
FILES = [
    "backend/app/__init__.py",
    "backend/app/main.py",
    "backend/app/services/pipeline.py",
    "backend/app/services/sql_parser.py",
    "backend/app/services/rules.py",
    "backend/app/services/rewriter.py",
    "backend/app/services/safety.py",
    "backend/app/services/ai/optimizer.py",
    "backend/app/services/ai/providers.py",
    "backend/app/services/ai/prompts/optimizer-v1.json",
    "backend/app/services/explain.py",
    "backend/app/services/benchmark.py",
    "backend/app/services/scoring.py",
    "backend/app/services/connectors.py",
    "backend/app/services/schema_ddl.py",
    "backend/app/models.py",
    "backend/app/db.py",
    "backend/app/config.py",
    "backend/config/scoring.json",
    "backend/app/research/runner.py",
    "backend/app/research/stats.py",
    "backend/app/research/report.py",
    "backend/app/research/api.py",
    "backend/app/research/datasets.py",
    "backend/app/examples.py",
    "frontend/src/api.ts",
    "frontend/src/App.tsx",
    "frontend/src/main.tsx",
    "frontend/src/components/ui.tsx",
    "frontend/src/components/SqlEditor.tsx",
    "frontend/src/components/PlanTree.tsx",
    "frontend/src/components/IssueList.tsx",
    "frontend/src/components/ComparisonView.tsx",
    "frontend/src/pages/Dashboard.tsx",
    "frontend/src/pages/Analyzer.tsx",
    "frontend/src/pages/Compare.tsx",
    "frontend/src/pages/Experiments.tsx",
    "frontend/src/pages/Databases.tsx",
    "frontend/src/pages/History.tsx",
    "frontend/src/index.css",
]


def source_lines() -> list[str]:
    missing = [f for f in FILES if not (ROOT / f).exists()]
    if missing:
        sys.exit(f"Нет файлов: {missing}")
    extra = sorted({str(p.relative_to(ROOT)).replace("\\", "/") for p in (ROOT / "backend/app").rglob("*.py")}
                   - set(FILES) - {"backend/app/services/__init__.py", "backend/app/services/ai/__init__.py",
                                   "backend/app/research/__init__.py"})
    if extra:
        print("ВНИМАНИЕ: файлы не включены в листинг:", extra)
    out: list[str] = []
    for f in FILES:
        text = (ROOT / f).read_text(encoding="utf-8").expandtabs(4).rstrip("\n")
        out.append(f"==== Файл: {f} " + "=" * max(0, WIDTH - len(f) - 12))
        for line in text.split("\n"):
            wrapped = textwrap.wrap(line, WIDTH, drop_whitespace=False, replace_whitespace=False,
                                    subsequent_indent="    ↪ ") or [""]
            out.extend(wrapped)
        out.append("")
    return out


def paginate(lines: list[str]) -> list[list[str]]:
    return [lines[i:i + LINES_PER_PAGE] for i in range(0, len(lines), LINES_PER_PAGE)]


CSS = """
@page { size: A4; margin: 14mm 12mm 14mm 16mm; }
body { margin: 0; font-family: Consolas, "Courier New", monospace; font-size: 7.6pt; color: #000; }
.page { page-break-after: always; height: 267mm; position: relative; }
.page:last-child { page-break-after: auto; }
.hdr { font-family: Arial, sans-serif; font-size: 7.5pt; border-bottom: 0.4pt solid #000; padding-bottom: 1mm;
       margin-bottom: 1.5mm; display: flex; justify-content: space-between; }
pre { margin: 0; white-space: pre; line-height: 1.33; }
.gap { font-family: Arial, sans-serif; font-size: 9pt; text-align: center; padding-top: 110mm; }
"""


def render(pages: list[tuple[int, list[str]]], total: int, note: str | None = None) -> str:
    parts = []
    for n, lines in pages:
        if n < 0:
            parts.append(f'<div class="page"><div class="gap">{html.escape(note or "")}</div></div>')
            continue
        parts.append(
            f'<div class="page"><div class="hdr"><span>{TITLE} — {html.escape(SUBTITLE)}</span>'
            f'<span>Лист {n} из {total}</span></div><pre>{html.escape(chr(10).join(lines))}</pre></div>')
    return f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>{CSS}</style></head><body>{"".join(parts)}</body></html>'


def to_pdf(html_path: Path) -> Path | None:
    edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
    if not edge.exists():
        print("Edge не найден — PDF не создан; откройте HTML и сохраните в PDF вручную")
        return None
    pdf = html_path.with_suffix(".pdf")
    subprocess.run([str(edge), "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf}", html_path.as_uri()], check=True, capture_output=True, timeout=180)
    return pdf


def main():
    OUT.mkdir(exist_ok=True)
    lines = source_lines()
    pages = paginate(lines)
    total = len(pages)
    full = OUT / "listing_full.html"
    full.write_text(render(list(enumerate(pages, 1)), total), encoding="utf-8")
    if total > DEPOSIT_HEAD + DEPOSIT_TAIL:
        numbered = list(enumerate(pages, 1))
        dep = numbered[:DEPOSIT_HEAD] + [(-1, [])] + numbered[-DEPOSIT_TAIL:]
        note = (f"Листы {DEPOSIT_HEAD + 1}–{total - DEPOSIT_TAIL} исходного текста опущены "
                f"(представлены первые {DEPOSIT_HEAD} и последние {DEPOSIT_TAIL} листов из {total})")
    else:
        dep, note = list(enumerate(pages, 1)), None
    deposit = OUT / "listing_deposit.html"
    deposit.write_text(render(dep, total, note), encoding="utf-8")
    size_kb = sum((ROOT / f).stat().st_size for f in FILES) / 1024
    print(f"строк: {len(lines)}, листов: {total}, объём исходного текста: {size_kb:.0f} КБ")
    for p in (full, deposit):
        pdf = to_pdf(p)
        print("создан", pdf or p)


if __name__ == "__main__":
    main()
