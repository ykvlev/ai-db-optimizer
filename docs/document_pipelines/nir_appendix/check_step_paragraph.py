"""Проверка влияния вставки «степени разработанности» на объём НИР.

    python check_step_paragraph.py

Собирает тестовый вариант во временную папку: во введение добавляется абзац
о степени разработанности темы, затем проверяется, что основная часть
по-прежнему занимает 30 страниц, а приложение начинается с 31-й.

Готовая редакция не изменяется.
"""

from __future__ import annotations

import importlib.util
import shutil
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

SCIENCE = Path(r"C:\Users\Артём\Documents\Science")
WORK = SCIENCE / "tmp" / "nir_step_check"
SRC = SCIENCE / "Научные материалы/05 Заявки и конкурсы/Наука 3.5 — ВоГУ 2026/Комплект к подаче — 15 октября 2026/01 НИР.docx"

PARAGRAPH = (
    "Степень разработанности темы. Формальные инструменты проверки эквивалентности — "
    "Cosette [5], VeriEQL [3] и доказательство через линейную целочисленную арифметику [6] — "
    "работают для поддерживаемых конструкций и требуют явной формализации запроса. "
    "Поиск контрпримеров развит в методах Pivoted Query Synthesis [17], NoREC [18] и "
    "разбиении запроса [24]. Сравнение двух языковых моделей на одном замороженном корпусе, "
    "при котором отдельно измеряется вклад профилей допустимых состояний, в рассмотренных "
    "работах не описывается."
)


def insert_paragraph(src: Path, dst: Path) -> None:
    """Вставить абзац после последнего абзаца введения, клонируя оформление."""
    doc = Document(src)
    paras = doc.paragraphs
    intro = max(i for i, p in enumerate(paras) if p.text.strip().startswith("Цель работы"))
    anchor = paras[intro]
    new_p = deepcopy(anchor._p)
    text_nodes = [n for n in new_p.iter() if n.tag == qn("w:t")]
    for i, node in enumerate(text_nodes):
        node.text = PARAGRAPH if i == 0 else ""
    anchor._p.addnext(new_p)
    doc.save(dst)


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    prepared = WORK / "01 НИР — со степенью разработанности.docx"
    insert_paragraph(SRC, prepared)
    print(f"абзац вставлен: {prepared.name}")

    spec = importlib.util.spec_from_file_location(
        "ba", SCIENCE / "tmp/nir_appendix_20261016/build_appendix.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.SRC = prepared
    m.OUTDIR = WORK
    m.main()
    print("тестовый вариант собран")


if __name__ == "__main__":
    main()
