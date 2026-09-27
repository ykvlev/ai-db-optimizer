"""Работа с подключённой базой: SQL-консоль, вопросы на русском (text-to-SQL), аудит структуры,
медленные запросы и описание базы (словарь данных в Word).

Всё выполняется так же, как анализ запросов: только одиночные SELECT (Safety Engine), в READ ONLY
транзакции с таймаутом, пользователем с правом на чтение.
"""

from __future__ import annotations

import base64
import datetime as dt
import decimal
import io
import json
import math
import time
import uuid

from app.config import get_settings
from app.models import Dialect, SchemaInfo, TableInfo
from app.services import safety
from app.services.ai.optimizer import extract_json
from app.services.ai.providers import LLMError, get_registry
from app.services.connectors import Connector, DBError
from app.services.sql_parser import SQLParseError, parse_statements

CONSOLE_ROW_LIMIT = 500


class WorkbenchError(Exception):
    pass


# ---------------------------------------------------------------- консоль
def _json_value(v):
    """Значение из драйвера СУБД → то, что можно отдать в JSON и показать в таблице."""
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return v if math.isfinite(v) else str(v)
    if isinstance(v, decimal.Decimal):
        return float(v) if v.is_finite() and abs(v) < 2 ** 53 else str(v)
    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return v.isoformat()
    if isinstance(v, dt.timedelta):
        return str(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        b = bytes(v)
        return "0x" + b[:32].hex() + ("…" if len(b) > 32 else "")
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False, default=str)
    return str(v)


def _with_limit(sql: str, dialect: Dialect, limit: int) -> str:
    """Добавляет LIMIT, если в запросе верхнего уровня его нет: консоль показывает первые строки,
    и тянуть из базы миллионы строк ради них незачем."""
    sql = sql.strip().rstrip(";").strip()
    try:
        tree = parse_statements(sql, dialect)[0]
    except (SQLParseError, IndexError):
        return sql
    if tree.args.get("limit") is None and tree.args.get("fetch") is None:
        return f"{sql}\nLIMIT {limit + 1}"
    return sql


def run_console(conn: Connector, dialect: Dialect, sql: str, limit: int = CONSOLE_ROW_LIMIT) -> dict:
    verdict = safety.check(sql, dialect)
    if not verdict.allowed:
        raise WorkbenchError("; ".join(verdict.reasons))
    executed = _with_limit(sql, dialect, limit)
    rows: list[list] = []

    def keep(row):
        if len(rows) <= limit:
            rows.append([_json_value(v) for v in row])

    res = conn.run(executed, row_consumer=keep)
    truncated = len(rows) > limit or res.rows_returned > limit
    return {"columns": res.columns, "rows": rows[:limit], "row_count": min(res.rows_returned, limit),
            "truncated": truncated, "elapsed_ms": round(res.elapsed_ms, 2), "executed_sql": executed,
            "warnings": verdict.warnings}


# ---------------------------------------------------------------- компактная схема для модели
def _schema_for_llm(schema: SchemaInfo, max_tables: int = 60) -> list[dict]:
    out = []
    for t in schema.tables[:max_tables]:
        out.append({"table": t.name, "rows": t.row_count,
                    "columns": [f"{c.name} {c.type}{'' if c.nullable else ' NOT NULL'}" for c in t.columns],
                    "primary_key": next((i.columns for i in t.indexes if i.primary), None),
                    "foreign_keys": [f"({', '.join(f.columns)}) → {f.ref_table}({', '.join(f.ref_columns)})"
                                     for f in t.foreign_keys]})
    return out


def _complete(system: str, user: str, model_id: str | None, json_mode: bool = True):
    reg = get_registry()
    try:
        provider, model = reg.resolve(model_id)
    except LLMError as e:
        raise WorkbenchError(str(e)) from e
    for attempt in range(3):
        try:
            return provider.complete(model, system, user, get_settings().llm_temperature, json_mode=json_mode), \
                f"{provider.name}:{model}"
        except LLMError as e:
            # лимит частоты запросов (HTTP 429, у GigaChat на личном тарифе — один запрос одновременно): ждём и повторяем
            if "429" in str(e) and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            if "429" in str(e):
                raise WorkbenchError(f"{provider.name}: сервис ограничивает частоту запросов — повторите через "
                                     "несколько секунд") from e
            raise WorkbenchError(str(e)) from e


# ---------------------------------------------------------------- «Спроси базу»: вопрос на русском → SQL
ASK_SYSTEM = """Ты — помощник аналитика данных. По вопросу пользователя на русском языке составь ОДИН запрос
SELECT к базе данных {dialect_name} {version}. Пользуйся только таблицами и колонками из схемы ниже, имена пиши
точно как в схеме. Запрос только читает данные (никаких INSERT/UPDATE/DELETE/DDL). Если вопрос про «топ» или
список — ограничь число строк (LIMIT). Колонкам результата давай понятные псевдонимы.

Ответь строго JSON-объектом:
{{"sql": "запрос", "explanation": "одно-два предложения по-русски: что считает запрос",
  "chart": {{"type": "bar" | "line" | "none", "x": "колонка для подписей", "y": "числовая колонка"}}}}
Диаграмму предлагай, только если результат — ряд подписей и чисел (bar) или динамика по времени (line)."""


def ask(conn: Connector, dialect: Dialect, version: str | None, schema: SchemaInfo, question: str,
        model_id: str | None) -> dict:
    if not question.strip():
        raise WorkbenchError("Задайте вопрос")
    system = ASK_SYSTEM.format(dialect_name="MySQL" if dialect == "mysql" else "PostgreSQL", version=version or "")
    user = json.dumps({"schema": _schema_for_llm(schema), "question": question}, ensure_ascii=False)
    attempts = []
    t0 = time.perf_counter()
    for attempt in range(2):  # вторая попытка — с текстом ошибки СУБД (самоисправление)
        llm, used_model = _complete(system, user, model_id)
        try:
            data = extract_json(llm.text)
            sql = str(data.get("sql", "")).strip()
        except (ValueError, AttributeError):
            data, sql = {}, ""
        if not sql:
            attempts.append({"sql": None, "error": "Модель не вернула запрос"})
            break
        try:
            result = run_console(conn, dialect, sql)
            chart = data.get("chart") if isinstance(data.get("chart"), dict) else None
            if chart and (chart.get("type") not in ("bar", "line") or chart.get("x") not in result["columns"]
                          or chart.get("y") not in result["columns"]):
                chart = None
            return {"sql": sql, "explanation": data.get("explanation", ""), "chart": chart, "result": result,
                    "model": used_model, "latency_ms": round((time.perf_counter() - t0) * 1000),
                    "attempts": attempts + [{"sql": sql, "error": None}]}
        except (WorkbenchError, DBError) as e:
            attempts.append({"sql": sql, "error": str(e)})
            user = json.dumps({"schema": _schema_for_llm(schema), "question": question, "previous_sql": sql,
                               "error": str(e), "task": "Исправь запрос с учётом ошибки"}, ensure_ascii=False)
    raise WorkbenchError("Не удалось составить рабочий запрос: " + "; ".join(a["error"] for a in attempts if a["error"]))


# ---------------------------------------------------------------- рабочая схема и «знакомство с базой»
def schema_of(table_name: str, default: str) -> str:
    return table_name.rsplit(".", 1)[0] if "." in table_name else default


def list_schemas(schema: SchemaInfo, default: str) -> list[dict]:
    groups: dict[str, dict] = {}
    for t in schema.tables:
        g = groups.setdefault(schema_of(t.name, default), {"tables": 0, "rows": 0})
        g["tables"] += 1
        g["rows"] += t.row_count or 0
    return sorted(({"name": k, **v, "default": k == default} for k, v in groups.items()),
                  key=lambda s: (-s["tables"], s["name"]))


def filter_schema(schema: SchemaInfo, name: str | None, default: str) -> SchemaInfo:
    """Только таблицы рабочей схемы — модель и автодополнение не путаются в чужих таблицах."""
    if not name:
        return schema
    return SchemaInfo(tables=[t for t in schema.tables if schema_of(t.name, default) == name], source=schema.source)


PROFILE_SYSTEM = """Ты — опытный аналитик баз данных. Тебе дана структура базы {dialect_name} (таблицы, столбцы, ключи,
число строк). Разберись, что это за база, и помоги человеку, который открыл её впервые.

Ответь строго JSON-объектом:
{{"summary": "2–3 предложения по-русски: что хранит база, для какой предметной области",
  "entities": [{{"table": "имя таблицы как в схеме", "meaning": "что хранит, несколько слов"}}],
  "relations": ["короткое описание ключевой связи, например: сотрудник → отдел"],
  "queries": [{{"title": "короткое название", "description": "что покажет запрос", "sql": "SELECT ..."}}]}}

Требования к queries: 6–8 полезных запросов на чтение для знакомства с данными и типичных отчётов этой предметной
области (сводки, топы, распределения, связи между таблицами). Имена таблиц и столбцов — точно как в схеме, диалект
{dialect_name}, у запросов со списками — LIMIT. Только SELECT."""


def profile(conn: Connector, dialect: Dialect, schema: SchemaInfo, model_id: str | None) -> dict:
    if not schema.tables:
        raise WorkbenchError("В выбранной схеме нет таблиц")
    dialect_name = "MySQL" if dialect == "mysql" else "PostgreSQL"
    llm, used_model = _complete(PROFILE_SYSTEM.format(dialect_name=dialect_name),
                                json.dumps({"schema": _schema_for_llm(schema, 80)}, ensure_ascii=False), model_id)
    try:
        data = extract_json(llm.text)
    except ValueError as e:
        raise WorkbenchError(f"Модель вернула ответ не в том формате: {e}") from e
    queries, rejected = [], 0
    for q in data.get("queries") or []:
        sql = str(q.get("sql", "")).strip().rstrip(";")
        if not sql or not safety.check(sql, dialect).allowed:
            rejected += 1
            continue
        try:
            conn.explain(sql)  # запрос должен быть корректным для этой базы: план строится без выполнения
        except DBError:
            rejected += 1
            continue
        queries.append({"title": str(q.get("title", "")), "description": str(q.get("description", "")), "sql": sql})
    names = {t.name.lower() for t in schema.tables}
    return {"summary": str(data.get("summary", "")),
            "entities": [e for e in data.get("entities") or [] if isinstance(e, dict)
                         and str(e.get("table", "")).lower() in names],
            "relations": [str(r) for r in data.get("relations") or []][:10],
            "queries": queries, "rejected": rejected, "model": used_model,
            "created_at": dt.datetime.now().isoformat(timespec="seconds"), "tables": len(schema.tables)}


def _profiles_file():
    from app.config import DATA_DIR
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / "console_profiles.json"


def load_profiles() -> dict:
    f = _profiles_file()
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except (OSError, ValueError):
        return {}


def save_profiles(data: dict) -> None:
    _profiles_file().write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def overview(conn: Connector, connection_id: int, schema: SchemaInfo) -> dict:
    """Схемы базы, выбранная рабочая схема и сохранённый анализ (если база уже открывалась в консоли)."""
    default = conn.default_schema()
    schemas = list_schemas(schema, default)
    store = load_profiles().get(str(connection_id), {})
    selected = store.get("selected")
    if selected not in {s["name"] for s in schemas}:
        selected = None
    return {"schemas": schemas, "default": default, "selected": selected,
            "profile": store.get("profiles", {}).get(selected) if selected else None}


def remember(connection_id: int, schema_name: str, prof: dict | None = None) -> None:
    data = load_profiles()
    entry = data.setdefault(str(connection_id), {"profiles": {}})
    entry["selected"] = schema_name
    if prof is not None:
        entry.setdefault("profiles", {})[schema_name] = prof
    save_profiles(data)


# ---------------------------------------------------------------- описание базы (словарь данных)
DESCRIBE_SYSTEM = """Ты — технический писатель. По структуре таблиц базы данных кратко опиши по-русски назначение
каждой таблицы (одно предложение) и каждого столбца (несколько слов). Не выдумывай того, чего не видно из имён и связей;
если назначение неочевидно, так и напиши. Ответ — строго JSON:
{"tables": {"имя_таблицы": {"description": "...", "columns": {"столбец": "..."}}}}"""

_desc_cache: dict[tuple[int, str], dict] = {}


def describe(schema: SchemaInfo, model_id: str | None, cache_key: int) -> dict:
    """Описания таблиц и столбцов от модели; по 12 таблиц за запрос, результат кэшируется."""
    key = (cache_key, ",".join(sorted(t.name for t in schema.tables)))
    if key in _desc_cache:
        return _desc_cache[key]
    out: dict = {}
    for i in range(0, len(schema.tables), 12):
        part = SchemaInfo(tables=schema.tables[i:i + 12], source=schema.source)
        llm, _ = _complete(DESCRIBE_SYSTEM, json.dumps(_schema_for_llm(part, 12), ensure_ascii=False), model_id)
        try:
            out.update(extract_json(llm.text).get("tables", {}))
        except (ValueError, AttributeError):
            continue
    _desc_cache[key] = out
    return out


def _key_mark(t: TableInfo, col: str) -> str:
    marks = []
    if any(i.primary and col in i.columns for i in t.indexes):
        marks.append("PK")
    for fk in t.foreign_keys:
        if col in fk.columns:
            marks.append(f"FK → {fk.ref_table}")
    return ", ".join(marks)


def data_dictionary_docx(name: str, dialect: Dialect, version: str | None, schema: SchemaInfo,
                         descriptions: dict | None, er_png: str | None = None, audit_report: dict | None = None,
                         scope: str | None = None) -> bytes:
    """Описание базы данных в Word по ГОСТ 2.105 / 7.32: Times New Roman 14, поля 30/10/20/20 мм, интервал 1,5,
    номер страницы вверху по центру, «Таблица N – …» над таблицей слева, «Рисунок N – …» под рисунком по центру.

    Разделы: общие сведения, перечень таблиц, структура таблиц, связи (ER-диаграмма в нотации IDEF1X и перечень
    внешних ключей), индексы и — по желанию — результаты аудита структуры."""
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Cm, Mm, Pt

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Mm(210), Mm(297)
    sec.left_margin, sec.right_margin, sec.top_margin, sec.bottom_margin = Mm(30), Mm(10), Mm(20), Mm(20)
    st = doc.styles["Normal"]
    st.font.name, st.font.size = "Times New Roman", Pt(14)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    st.paragraph_format.line_spacing = 1.5
    st.paragraph_format.space_after = Pt(0)
    descriptions = descriptions or {}
    # номер страницы — вверху по центру (ГОСТ 2.105)
    hp = sec.header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = hp.add_run()
    for tag, text in (("begin", None), (None, "PAGE"), ("end", None)):
        if tag:
            el = run._r.makeelement(qn("w:fldChar"), {qn("w:fldCharType"): tag})
        else:
            el = run._r.makeelement(qn("w:instrText"), {qn("xml:space"): "preserve"})
            el.text = text
        run._r.append(el)

    def short_type(t: str) -> str:
        t = t.lower()
        for long, short in (("character varying", "varchar"), ("timestamp without time zone", "timestamp"),
                            ("timestamp with time zone", "timestamptz"), ("double precision", "double"),
                            ("time without time zone", "time"), ("character", "char")):
            t = t.replace(long, short)
        return t

    def para(text, center=False, indent=True, size=None, before=0, after=0, keep=False):
        p = doc.add_paragraph()
        r = p.add_run(text)
        if size:
            r.font.size = Pt(size)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.first_line_indent = Cm(1.25) if indent and not center else Cm(0)
        p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(before), Pt(after)
        p.paragraph_format.keep_with_next = keep
        return p

    def table(headers, rows, widths):
        tb = doc.add_table(rows=1, cols=len(headers))
        tb.style = "Table Grid"
        tb.alignment = WD_TABLE_ALIGNMENT.CENTER
        for row_cells, values in ((tb.rows[0].cells, headers), *((tb.add_row().cells, r) for r in rows)):
            for cell, v, w in zip(row_cells, values, widths):
                cell.width = Cm(w)
                cell.text = ""
                p = cell.paragraphs[0]
                p.paragraph_format.line_spacing = 1.0
                p.paragraph_format.first_line_indent = Cm(0)
                r = p.add_run(str(v) if v is not None else "")
                r.font.size = Pt(12)
        # шапка повторяется на каждой странице
        tr = tb.rows[0]._tr
        trpr = tr.get_or_add_trPr()
        el = trpr.makeelement(qn("w:tblHeader"), {qn("w:val"): "true"})
        trpr.append(el)
        return tb

    dbms = "MySQL" if dialect == "mysql" else "PostgreSQL"
    tables = schema.tables
    links = [(t, fk) for t in tables for fk in t.foreign_keys]
    n_tab = 0

    def caption(text):
        nonlocal n_tab
        n_tab += 1
        para(f"Таблица {n_tab} – {text}", indent=False, keep=True, before=6)

    def heading(text):
        para(text, indent=True, before=24, after=12, keep=True)

    num = lambda v: f"{v:,}".replace(",", " ")  # noqa: E731
    rows_fmt = lambda t: num(t.row_count) if t.row_count is not None else "—"  # noqa: E731
    total_rows = sum(t.row_count or 0 for t in tables)
    total_mb = sum(t.size_bytes or 0 for t in tables) / 1048576
    what = f"схемы «{scope}» базы данных «{name.split('.')[0]}»" if scope else f"базы данных «{name}»"

    # в заголовке прописными — только слова, имена объектов базы остаются как есть
    head = (f"СХЕМЫ «{scope}» БАЗЫ ДАННЫХ «{name.split('.')[0]}»" if scope else f"БАЗЫ ДАННЫХ «{name}»")
    para(f"ОПИСАНИЕ СТРУКТУРЫ {head}", center=True, after=12)
    para(f"Документ описывает структуру {what}: назначение и состав таблиц, типы полей, ключи, связи и индексы"
         + (", а также результаты аудита структуры" if audit_report else "") + ". Описание сформировано программой "
         f"AI Database Optimizer {dt.date.today().strftime('%d.%m.%Y')} по подключённой базе"
         + (", назначение таблиц и полей предложено языковой моделью и требует проверки." if descriptions else "."))

    heading("1 Общие сведения")
    caption("Общие сведения о базе данных")
    info = [["СУБД", f"{dbms} {version or ''}".strip()], ["База данных", name.split(".")[0]]]
    if scope:
        info.append(["Схема", scope])
    info += [["Таблиц", len(tables)], ["Строк (всего)", num(total_rows)], ["Объём данных и индексов", f"{total_mb:.1f} МБ".replace(".", ",")],
             ["Внешних ключей", len(links)], ["Индексов", sum(len(t.indexes) for t in tables)]]
    if audit_report:
        info.append(["Оценка структуры", f"{audit_report['score']} из 100 ({audit_report['verdict']})"])
    table(["Показатель", "Значение"], info, [8.5, 8.5])

    heading("2 Перечень таблиц")
    caption("Перечень таблиц")
    if descriptions:
        table(["№", "Таблица", "Назначение", "Строк"],
              [[i + 1, t.name, descriptions.get(t.name, {}).get("description", ""), rows_fmt(t)]
               for i, t in enumerate(tables)], [1.0, 4.5, 9.0, 2.5])
    else:  # без описаний столбец «Назначение» остался бы пустым
        table(["№", "Таблица", "Полей", "Строк", "Объём, КБ"],
              [[i + 1, t.name, len(t.columns), rows_fmt(t), num(round((t.size_bytes or 0) / 1024))]
               for i, t in enumerate(tables)], [1.0, 8.0, 2.5, 3.0, 2.5])

    heading("3 Структура таблиц")
    for t in tables:
        d = descriptions.get(t.name, {})
        if d.get("description"):
            para(f"Таблица {t.name}: {d['description'][0].lower() + d['description'][1:]}", before=6)
        caption(f"Структура таблицы {t.name}")
        cols = d.get("columns", {}) if isinstance(d.get("columns"), dict) else {}
        if descriptions:
            table(["Поле", "Тип", "NULL", "Ключ", "Описание"],
                  [[c.name, short_type(c.type), "да" if c.nullable else "нет", _key_mark(t, c.name), cols.get(c.name, "")]
                   for c in t.columns], [3.8, 3.4, 1.4, 3.4, 5.0])
        else:
            table(["Поле", "Тип", "NULL", "Ключ"],
                  [[c.name, short_type(c.type), "да" if c.nullable else "нет", _key_mark(t, c.name)]
                   for c in t.columns], [5.5, 4.5, 2.0, 5.0])

    heading("4 Связи между таблицами")
    if er_png:
        png = base64.b64decode(er_png.split(",", 1)[-1])
        w_px, h_px = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
        width = Cm(17) if not w_px or h_px / w_px * 17 <= 22 else Cm(22 * w_px / h_px)  # не выше страницы
        para("Схема данных приведена на рисунке 1 в нотации IDEF1X: в каждом блоке над чертой — первичный ключ, "
             "под чертой — остальные атрибуты, внешние ключи помечены (FK); линия связи идёт от родительской "
             "таблицы к дочерней, точка на конце линии означает «много».")
        doc.add_picture(io.BytesIO(png), width=width)
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.paragraphs[-1].paragraph_format.keep_with_next = True
        para(f"Рисунок 1 – Схема данных {what}", center=True, after=12)
    if links:
        para(f"Внешние ключи перечислены в таблице {n_tab + 1}.")
        caption("Внешние ключи")
        table(["Дочерняя таблица", "Столбцы", "Родительская таблица", "Столбцы", "Связь"],
              [[t.name, ", ".join(fk.columns), fk.ref_table, ", ".join(fk.ref_columns),
                "1 : 0..N" if any(c.nullable for c in t.columns if c.name in fk.columns) else "1 : N"]
               for t, fk in links], [4.2, 3.0, 4.2, 3.0, 2.6])
    else:
        para("Внешние ключи не объявлены: связи между таблицами СУБД не контролирует.")

    heading("5 Индексы")
    idx_rows = [[t.name, i.name, ", ".join(i.columns), "первичный ключ" if i.primary else "уникальный" if i.unique else "обычный"]
                for t in tables for i in t.indexes]
    if idx_rows:
        caption("Индексы")
        table(["Таблица", "Индекс", "Столбцы", "Вид"], idx_rows, [4.3, 5.2, 4.5, 3.0])
    else:
        para("Индексов нет.")

    if audit_report:
        heading("6 Оценка структуры")
        para(f"Оценка структуры — {audit_report['score']} из 100 ({audit_report['verdict']}). {audit_report['how']}")
        caption("Оценка по направлениям")
        table(["Направление", "Оценка", "Замечаний", "Что проверяется"],
              [[c["title"], c["score"], c["issues"], c["about"]] for c in audit_report["categories"].values()],
              [4.0, 2.0, 2.3, 8.7])
        fs = audit_report["findings"]
        if fs:
            sev = {"high": "высокая", "medium": "средняя", "low": "низкая"}
            caption("Замечания и рекомендации")
            table(["№", "Таблица", "Замечание", "Важность", "Рекомендация"],
                  [[k + 1, f["table"], f["title"] + (f". {f['note']}" if f.get("note") else ""), sev[f["severity"]],
                    f["effect"]] for k, f in enumerate(fs[:80])], [0.9, 3.4, 5.4, 2.0, 5.3])
        else:
            para("Замечаний нет.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
