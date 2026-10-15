"""Сборка редакции конкурсной НИР с приложением о сравнении двух моделей.

    python build_appendix.py

Основная часть документа не изменяется: приложение дописывается в конец, после
списка источников. По правилам конкурса объём 30 страниц считается без приложений,
поэтому согласованная редакция сохраняет ровно 30 страниц.

Оформление новых абзацев клонируется с существующих абзацев документа, чтобы
шрифт, отступы и интервалы совпали.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

SCIENCE = Path(r"C:\Users\Артём\Documents\Science")
COMP = SCIENCE / "Научные материалы/05 Заявки и конкурсы/Наука 3.5 — ВоГУ 2026"
SRC = COMP / "Комплект к подаче — 15 октября 2026/01 НИР.docx"
OUTDIR = COMP / "Редакция с приложением — 16 октября 2026"
RUNS = SCIENCE / "ai-db-optimizer/docs/articles/sql_rewrite_validation/runs/library_evaluation_20261015"
FIGDIR = Path(r"C:\Users\Артём\Documents\Science\tmp\nir_appendix_20261016\figures_word")

TITLE = "ПРИЛОЖЕНИЕ А"
SUBTITLE = "Сравнение двух языковых моделей на замороженном корпусе"


def w(tag: str) -> str:
    return "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}" + tag


class Styler:
    """Клонирует оформление существующих абзацев документа."""

    def __init__(self, doc: Document):
        head = next(p for p in doc.paragraphs if p.text.strip().startswith("2.1 "))
        body = next(p for p in doc.paragraphs if len(p.text) > 300 and p.runs)
        self.head_pPr = copy.deepcopy(head._p.pPr)
        self.head_rPr = copy.deepcopy(head.runs[0]._r.rPr) if head.runs[0]._r.rPr is not None else None
        self.body_pPr = copy.deepcopy(body._p.pPr)
        self.body_rPr = copy.deepcopy(body.runs[0]._r.rPr) if body.runs[0]._r.rPr is not None else None
        print(f"образец заголовка: {head.text[:50]!r}; образец текста: {body.text[:50]!r}")
        print(f"rPr заголовка: {self.head_rPr is not None}; rPr текста: {self.body_rPr is not None}")

    def paragraph(self, doc: Document, text: str, kind: str = "body"):
        p = doc.add_paragraph()
        pPr = self.head_pPr if kind == "head" else self.body_pPr
        if pPr is not None:
            p._p.insert(0, copy.deepcopy(pPr))
        run = p.add_run(text)
        rPr = self.head_rPr if kind == "head" else self.body_rPr
        if rPr is not None:
            run._r.insert(0, copy.deepcopy(rPr))
        return p


def add_table(doc: Document, st: Styler, header: list[str], rows: list[list[str]], widths: list[float]):
    t = doc.add_table(rows=1, cols=len(header))
    try:
        t.style = "Table Grid"
    except KeyError:
        pass
    t.autofit = False
    tblPr = t._tbl.tblPr
    # ВАЖНО: autofit=False уже создаёт w:tblLayout. Дописывать второй нельзя —
    # дубликат элемента нарушает схему OOXML, и Word перестаёт открывать файл
    # (LibreOffice такой файл открывает, поэтому ошибку легко не заметить).
    # Переиспользуем существующее свойство и выставляем правильный порядок детей.
    layout = tblPr.find(qn("w:tblLayout"))
    if layout is None:
        layout = tblPr.makeelement(qn("w:tblLayout"), {})
        tblPr.append(layout)
    layout.set(qn("w:type"), "fixed")

    # Узкие поля ячеек: больше места под текст в узких столбцах.
    mar = tblPr.find(qn("w:tblCellMar"))
    if mar is None:
        mar = tblPr.makeelement(qn("w:tblCellMar"), {})
        tblPr.append(mar)
    for child in list(mar):
        mar.remove(child)
    for side, value in (("top", 20), ("left", 60), ("bottom", 20), ("right", 60)):
        mar.append(mar.makeelement(qn(f"w:{side}"), {qn("w:w"): str(value), qn("w:type"): "dxa"}))

    # Порядок детей tblPr строго задан схемой: tblLayout и tblCellMar идут
    # после tblBorders/shd и до tblLook.
    ORDER = ["tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize",
             "tblStyleColBandSize", "tblW", "jc", "tblCellSpacing", "tblInd", "tblBorders",
             "shd", "tblLayout", "tblCellMar", "tblLook", "tblCaption", "tblDescription",
             "tblPrChange"]
    rank = {name: i for i, name in enumerate(ORDER)}
    children = list(tblPr)
    children.sort(key=lambda el: rank.get(el.tag.split("}")[-1], len(ORDER)))
    for child in children:
        tblPr.append(child)
    grid = t._tbl.find(qn("w:tblGrid"))
    if grid is not None:
        for gc, width in zip(grid.findall(qn("w:gridCol")), widths):
            gc.set(qn("w:w"), str(int(width * 567)))

    def fill(cell, text: str, bold: bool):
        cell.text = ""
        p = cell.paragraphs[0]
        # Ячейки не должны наследовать абзацный отступ и полуторный интервал:
        # иначе текст смещается и таблица раздувается по высоте.
        pf = p.paragraph_format
        pf.left_indent = Cm(0)
        pf.right_indent = Cm(0)
        pf.first_line_indent = Cm(0)
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)
        pf.line_spacing = 1.0
        run = p.add_run(text)
        run.bold = bold
        # Правила конкурса: кегль основного текста 14, в таблицах и рисунках — 12.
        run.font.size = Pt(12)
        run.font.name = "Times New Roman"

    for i, text in enumerate(header):
        fill(t.rows[0].cells[i], text, True)
    for row in rows:
        cells = t.add_row().cells
        for i, text in enumerate(row):
            fill(cells[i], text, False)
    for r in t.rows:
        # Строка таблицы не разрывается между страницами.
        trPr = r._tr.get_or_add_trPr()
        trPr.append(trPr.makeelement(qn("w:cantSplit"), {}))
        for i, c in enumerate(r.cells):
            c.width = Cm(widths[i])
    # Связывать все строки таблицы «держать со следующей» НЕ следует: вместе с
    # запретом разрыва строки (cantSplit) и подписью это создаёт длинную цепочку
    # keep-with-next, на которой Word уходит в цикл разметки и перестаёт открывать
    # документ (LibreOffice при этом файл открывает). Достаточно cantSplit для
    # строк и keep-with-next для подписи таблицы.
    return t


def caption(doc: Document, st: Styler, text: str):
    """Подпись таблицы: держится вместе с самой таблицей, кегль 12."""
    p = st.paragraph(doc, text, "body")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    for run in p.runs:
        run.font.size = Pt(12)
    return p


def add_figure(doc: Document, st: Styler, path: Path, caption: str, width_cm: float = 16.0):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(path), width=Cm(width_cm))
    cap = st.paragraph(doc, caption, "body")
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in cap.runs:
        run.font.size = Pt(12)
    return p


def add_appendix_toc_entry(doc: Document, head_par, title: str) -> bool:
    """Добавить пункт приложения в содержание.

    Содержание в этом документе — не поле TOC, а готовый список: Word обновляет
    в нём только номера страниц (поля PAGEREF). Поэтому новый пункт вставляется
    копией последнего существующего пункта и связывается закладкой с заголовком
    приложения; номер страницы подставит Word при обновлении полей.
    """
    bookmark = "_TocAppendixA"
    start = head_par._p.makeelement(qn("w:bookmarkStart"), {qn("w:id"): "901", qn("w:name"): bookmark})
    end = head_par._p.makeelement(qn("w:bookmarkEnd"), {qn("w:id"): "901"})
    head_par._p.insert(0, start)
    head_par._p.append(end)

    toc = [p for p in doc.paragraphs if p.style is not None and p.style.name == "toc 1"]
    if not toc:
        return False
    src = toc[-1]
    new_p = copy.deepcopy(src._p)
    src._p.addnext(new_p)

    replaced = False
    for child in new_p.iter():
        tag = child.tag.split("}")[-1]
        if tag == "t":
            child.text = "" if replaced else title
            replaced = True
        elif tag == "instrText" and child.text:
            child.text = re.sub(r"_Toc\d+", bookmark, child.text)
    return True


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    doc = Document(SRC)
    st = Styler(doc)

    head = st.paragraph(doc, TITLE, "head")
    head.alignment = WD_ALIGN_PARAGRAPH.CENTER
    head.paragraph_format.page_break_before = True
    sub = st.paragraph(doc, SUBTITLE, "head")
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER

    st.paragraph(doc, "А.1 Постановка проверки", "head")
    st.paragraph(
        doc,
        "Проверялось, какие изменения результата предлагают две разные языковые модели на одинаковых "
        "задачах и какие допустимые состояния базы обнаруживают эти изменения. Использован корпус из "
        "12 вручную составленных запросов в одном дополнительном домене (библиотека: читатели, книги, "
        "выдачи), по 28 допустимых состояний на запрос и четыре положительных контроля. Корпус заморожен "
        "до получения ответов моделей; preflight исполнил 672 эталонных и 224 контрольных обращения на "
        "MySQL 8.4.11 и PostgreSQL 16.15.",
    )
    st.paragraph(
        doc,
        "Участвовали Qwen2.5-Coder-7B (квантование Q4_K_M, 7,6 млрд параметров) и Phi-3.5-mini 3.8B "
        "(Q4_0, 3,8 млрд). Условия одинаковы: локальная служба Ollama 0.40.4, температура 0, контекст "
        "4096 токенов, предел ответа 1200 токенов, один ответ на запрос. Получено 24 ответа, служебных "
        "ошибок нет. Выполнено 672 проверки «запрос × состояние». Время исполнения в этой серии не "
        "измерялось.",
    )

    st.paragraph(doc, "А.2 Результаты", "head")
    st.paragraph(doc, "Исходы обеих моделей сведены в таблице А.1.")
    caption(doc, st, "Таблица А.1 — Исходы двух моделей на 12 запросах")
    add_table(
        doc, st,
        ["Участник", "Ответов", "Предложено переписываний", "Опровергнуто"],
        [
            ["Qwen2.5-Coder-7B", "12", "5", "3"],
            ["Phi-3.5-mini 3.8B", "12", "2", "1"],
        ],
        [5.0, 2.7, 5.3, 4.0],
    )
    st.paragraph(
        doc,
        "Более крупная модель, специализированная на программном коде, ошиблась чаще и предложила больше "
        "переписываний. Направление совпадает с прежними сериями: готовность переписывать связана с риском "
        "ошибки.",
    )

    st.paragraph(doc, "А.3 Обнаруженные ошибки", "head")
    st.paragraph(
        doc,
        "Обнаруженные ошибки и состояние, которое подтвердило каждую из них, приведены в таблице А.2.",
    )
    caption(doc, st, "Таблица А.2 — Ошибки, подтверждённые допустимым состоянием")
    add_table(
        doc, st,
        ["Модель", "Запрос", "Механизм ошибки", "Опровергнуто", "Свидетель"],
        [
            ["Qwen2.5-Coder-7B", "all_returned", "Обращение условия: выбраны читатели с активной выдачей вместо читателей, у которых возвращено всё", "23 из 28", "базовое состояние"],
            ["Qwen2.5-Coder-7B", "zero_fee", "Агрегатное условие заменено построчным: «есть выдача с нулевым сбором» вместо «сумма сборов равна нулю»", "9 из 28", "кратности"],
            ["Qwen2.5-Coder-7B", "union_bag", "UNION ALL заменён на OR: выдача, попадающая в оба условия, схлопывается в одну строку", "3 из 28", "кратности"],
            ["Phi-3.5-mini 3.8B", "union_bag", "То же преобразование, что у Qwen2.5-Coder-7B", "3 из 28", "кратности"],
        ],
        [3.0, 2.3, 6.4, 2.9, 2.4],
    )

    st.paragraph(doc, "А.4 Совпадающая ошибка", "head")
    st.paragraph(
        doc,
        "Обе модели независимо предложили одну и ту же замену UNION ALL на OR. Выдача, для которой "
        "одновременно выполнены оба условия, в исходном запросе присутствует дважды, а после замены — один "
        "раз: эталон возвращает четыре строки, кандидат три. Расхождение обнаруживают только состояния с "
        "повторяющимися строками.",
    )
    st.paragraph(
        doc,
        "Существенно, что эту ошибку не обнаружило ни одно из двадцати случайных состояний корпуса. "
        "Следовательно, совпадение двух независимых моделей не является свидетельством корректности: "
        "перекрёстная проверка по признаку «модели согласились» пропустила бы это расхождение.",
    )

    st.paragraph(doc, "А.5 Какие состояния обнаруживают ошибку", "head")
    st.paragraph(
        doc,
        "Вклад профилей допустимых состояний в обнаружение ошибок показан в таблице А.3.",
    )
    caption(doc, st, "Таблица А.3 — Вклад профилей состояний в обнаружение")
    add_table(
        doc, st,
        ["Профиль состояния", "Что проверяет", "Обнаружено ошибок"],
        [
            ["С кратностями (multiplicity)", "несколько выдач на читателя, повторяющиеся строки", "4 из 4"],
            ["Равные ключи сортировки (ties)", "совпадение ключей при упорядочении", "4 из 4"],
            ["С NULL (nullable)", "NULL в столбце, допускающем NULL", "3 из 4"],
            ["Нулевой сбор (zero_fee)", "нулевая сумма сбора", "2 из 4"],
            ["Двадцать случайных состояний", "общее покрытие", "2 из 4"],
            ["Включающие границы (boundary)", "значения на границах диапазонов", "1 из 4"],
            ["Базовое фиксированное состояние", "простейший допустимый набор строк", "1 из 4"],
        ],
        [5.6, 7.0, 4.4],
    )
    st.paragraph(
        doc,
        "Решающими оказались намеренно построенные граничные профили, а не объём случайного покрытия. "
        "Обращение условия видно уже в базовом состоянии, тогда как ошибки, связанные с кратностями и "
        "агрегацией, требуют состояния с несколькими выдачами на читателя.",
    )

    st.paragraph(
        doc,
        "Исходы по каждому из двенадцати запросов для двух моделей показаны на рисунке А.1, "
        "а число состояний, обнаруживших каждую ошибку, и её минимальный свидетель — на рисунке А.2.",
    )
    add_figure(doc, st, FIGDIR / "library_case_matrix.png",
               "Рисунок А.1 — Исходы по двенадцати запросам для двух моделей")
    add_figure(doc, st, FIGDIR / "library_refuting_states.png",
               "Рисунок А.2 — Число состояний, обнаруживших каждую ошибку, и минимальный свидетель")

    st.paragraph(doc, "А.6 Воспроизведение", "head")
    st.paragraph(
        doc,
        "Оценка выполнена дважды независимыми прогонами на одном замороженном корпусе и одних и тех же "
        "сохранённых ответах. Счётчики совпали, а набор опровергнутых пар совпал по всем 24 парам «модель × "
        "запрос» без единого расхождения.",
    )

    st.paragraph(doc, "А.7 Ограничения", "head")
    for text in [
        "Корпус синтетический и составлен вручную; это не независимая выборка рабочих запросов.",
        "Совпадение на 28 состояниях не является доказательством эквивалентности. Двадцать пар прошли "
        "проверку без расхождения, и их эквивалентность не утверждается.",
        "Кандидаты моделей исполнялись только на MySQL; переносимость на PostgreSQL этой серией не "
        "установлена, хотя эталоны исполнены на обеих СУБД.",
        "Время исполнения не измерялось, поэтому выводов об ускорении из этой серии не следует.",
        "Две модели различаются одновременно числом параметров, семейством и квантованием, поэтому "
        "различие результатов нельзя приписать только размеру или специализации.",
        "Ошибка union_bag представляет собой одну ошибку с двумя наблюдениями, а не два независимых случая.",
    ]:
        st.paragraph(doc, text)

    add_appendix_toc_entry(
        doc, head, "ПРИЛОЖЕНИЕ А — Сравнение двух моделей на замороженном корпусе"
    )

    out = OUTDIR / "НИР — с приложением о сравнении моделей — Наука 3.5.docx"
    doc.save(out)

    src_sha = hashlib.sha256(SRC.read_bytes()).hexdigest()
    out_sha = hashlib.sha256(out.read_bytes()).hexdigest()
    (OUTDIR / "Происхождение приложения.json").write_text(
        json.dumps(
            {
                "source": str(SRC),
                "source_sha256": src_sha,
                "output": str(out),
                "output_sha256": out_sha,
                "main_part_unchanged": True,
                "appendix_paragraphs_added": len(doc.paragraphs) - 182,
                "figures": [str(FIGDIR / "library_case_matrix.png"), str(FIGDIR / "library_refuting_states.png")],
                "sources": [
                    str(RUNS / "summary.json"),
                    str(RUNS.parent / "library_models_20261015/summary.json"),
                ],
                "new_corpus_sha256": "ff7d02331e7c5a4b650eff35742bb7d466753e7a2ed51d59310a6e8c3581ca58",
                "rules": "Объём НИР не более 30 страниц без приложений; приложение в лимит не входит.",
                "ci_cd": "Конвейер конкурсных документов не настроен; это локальная сборка.",
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"сохранено: {out}")
    print(f"абзацев было 182, стало {len(doc.paragraphs)}; таблиц было 6, стало {len(doc.tables)}")


if __name__ == "__main__":
    main()
