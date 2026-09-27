"""Схемы для отчёта о НИР: IDEF0, UML, архитектура, ER-диаграмма, блок-схемы алгоритмов (ГОСТ 19.701).
Чёрно-белые SVG, рендер в PNG через make_figures.render.

    python docs/nir/diagrams.py
"""

from __future__ import annotations

import html
import importlib.util
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("mf", HERE / "make_figures.py")
mf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mf)

FONT = "Arial, Helvetica, sans-serif"


class Svg:
    def __init__(self, w: int, h: int, fs: int = 14):
        self.w, self.h, self.fs, self.parts = w, h, fs, []

    # ---------------------------------------------------------- текст
    def text(self, x, y, t, anchor="middle", size=None, italic=False, bold=False, fill="#000"):
        size = size or self.fs
        lines = t.split("\n")
        y0 = y - (len(lines) - 1) * size * 0.6
        style = (' font-style="italic"' if italic else "") + (' font-weight="bold"' if bold else "")
        for i, line in enumerate(lines):
            self.parts.append(f'<text x="{x:.1f}" y="{y0 + i * size * 1.2 + size * 0.35:.1f}" text-anchor="{anchor}" '
                              f'font-size="{size}"{style} fill="{fill}" stroke="#fff" stroke-width="4" paint-order="stroke" '
                              f'stroke-linejoin="round">{html.escape(line)}</text>')

    # ---------------------------------------------------------- фигуры
    def box(self, x, y, w, h, t="", rx=0, dashed=False, size=None, bold=False, fill="#fff", sw=1.5):
        d = ' stroke-dasharray="6,4"' if dashed else ""
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="#000" stroke-width="{sw}"{d}/>')
        if t:
            self.text(x + w / 2, y + h / 2, t, size=size, bold=bold)
        return (x, y, w, h)

    def terminator(self, cx, cy, w, h, t):
        return self.box(cx - w / 2, cy - h / 2, w, h, t, rx=h / 2, bold=True)

    def diamond(self, cx, cy, w, h, t, size=None):
        pts = f"{cx},{cy - h / 2} {cx + w / 2},{cy} {cx},{cy + h / 2} {cx - w / 2},{cy}"
        self.parts.append(f'<polygon points="{pts}" fill="#fff" stroke="#000" stroke-width="1.5"/>')
        self.text(cx, cy, t, size=size)

    def ellipse(self, cx, cy, rx, ry, t, size=None):
        self.parts.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="#fff" stroke="#000" stroke-width="1.5"/>')
        self.text(cx, cy, t, size=size)

    def actor(self, cx, y, label):
        s = self.parts
        s.append(f'<circle cx="{cx}" cy="{y + 12}" r="12" fill="#fff" stroke="#000" stroke-width="1.5"/>')
        s.append(f'<line x1="{cx}" y1="{y + 24}" x2="{cx}" y2="{y + 62}" stroke="#000" stroke-width="1.5"/>')
        s.append(f'<line x1="{cx - 22}" y1="{y + 36}" x2="{cx + 22}" y2="{y + 36}" stroke="#000" stroke-width="1.5"/>')
        s.append(f'<line x1="{cx}" y1="{y + 62}" x2="{cx - 18}" y2="{y + 90}" stroke="#000" stroke-width="1.5"/>')
        s.append(f'<line x1="{cx}" y1="{y + 62}" x2="{cx + 18}" y2="{y + 90}" stroke="#000" stroke-width="1.5"/>')
        self.text(cx, y + 110, label)

    def line(self, pts, arrow=True, dashed=False, open_head=False, sw=1.5):
        d = ' stroke-dasharray="6,4"' if dashed else ""
        mk = ' marker-end="url(#ah)"' if arrow and not open_head else (' marker-end="url(#oh)"' if arrow else "")
        p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        self.parts.append(f'<polyline points="{p}" fill="none" stroke="#000" stroke-width="{sw}"{d}{mk}/>')

    def dot(self, x, y, r=3.5):
        self.parts.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#000"/>')

    def svg(self) -> str:
        defs = ('<defs><marker id="ah" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse">'
                '<path d="M0,0 L10,5 L0,10 z" fill="#000"/></marker>'
                '<marker id="oh" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="10" markerHeight="10" orient="auto">'
                '<path d="M0,0 L10,5 L0,10" fill="none" stroke="#000" stroke-width="1.5"/></marker></defs>')
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" '
                f'font-family="{FONT}">{defs}<rect width="{self.w}" height="{self.h}" fill="#fff"/>{"".join(self.parts)}</svg>')


# =================================================================== IDEF0
def idef0_context() -> str:
    s = Svg(1200, 600, 15)
    bx, by, bw, bh = 400, 190, 400, 210
    s.box(bx, by, bw, bh, "ОПТИМИЗИРОВАТЬ\nSQL-ЗАПРОС\nС ПРОВЕРКОЙ\nРЕКОМЕНДАЦИЙ ИИ", bold=True, size=16)
    s.text(bx + bw - 22, by + bh - 12, "A0", bold=True)
    s.text(30, 170, "ВХОДЫ", anchor="start", size=13, italic=True)
    for i, t in enumerate(["Исходный SQL-запрос или скрипт", "Схема БД (DDL, метаданные)", "Данные исследуемой БД"]):
        y = by + 45 + i * 60
        s.line([(20, y), (bx, y)])
        s.text(25, y - 13, t, anchor="start")
    s.text(1170, 170, "ВЫХОДЫ", anchor="end", size=13, italic=True)
    for i, t in enumerate(["Проверенный запрос", "Проблемы и рекомендации", "Замеры и отчёт"]):
        y = by + 45 + i * 60
        s.line([(bx + bw, y), (1180, y)])
        s.text(1175, y - 13, t, anchor="end")
    s.text(bx + bw / 2, 22, "УПРАВЛЕНИЕ", size=13, italic=True)
    for i, t in enumerate(["Правила\nанализа", "Требования\nбезопасности", "Шаблон\nпромпта", "Пороги\nисходов"]):
        x = bx + 50 + i * 100
        s.line([(x, 105), (x, by)])
        s.text(x, 72, t, size=13)
    s.text(bx + bw / 2, 588, "МЕХАНИЗМЫ", size=13, italic=True)
    for i, t in enumerate(["Исследо-\nватель", "Языковая\nмодель", "СУБД MySQL,\nPostgreSQL", "AI Database\nOptimizer"]):
        x = bx + 50 + i * 100
        s.line([(x, 490), (x, by + bh)])
        s.text(x, 520, t, size=13)
    return s.svg()


def idef0_decomposition() -> str:
    s = Svg(1330, 720, 14)
    ox = 90
    B = [("A1", "Проанализировать\nзапрос", ox + 0, 90), ("A2", "Получить\nрекомендацию\nмодели", ox + 220, 200),
         ("A3", "Проверить\nрекомендацию", ox + 440, 310), ("A4", "Измерить\nэффективность", ox + 660, 420),
         ("A5", "Сохранить результат,\nсформировать отчёт", ox + 880, 530)]
    w, h = 190, 100
    for code, t, x, y in B:
        s.box(x, y, w, h, t)
        s.text(x + w - 16, y + h - 10, code, size=12, bold=True)
    labels = ["Проблемы, схема,\nплан выполнения", "Кандидат\nзапроса", "Допущенный\nзапрос", "Замеры,\nвердикт"]
    for i in range(4):
        _, _, x, y = B[i]
        _, _, nx, ny = B[i + 1]
        s.line([(x + w, y + 35), (nx - 25, y + 35), (nx - 25, ny + 30), (nx, ny + 30)])
        s.text(x + w + 8, y + 15, labels[i], anchor="start", size=12)
    a3x, a3y = B[2][2], B[2][3]
    a5x, a5y = B[4][2], B[4][3]
    s.line([(a3x + 60, a3y + h), (a3x + 60, a5y + 75), (a5x, a5y + 75)])
    s.text(a3x + 70, a5y + 62, "Отклонённый вариант, тип ошибки", anchor="start", size=12)
    s.line([(5, 140), (ox, 140)])
    s.text(8, 112, "Исходный\nSQL", anchor="start", size=12)
    s.line([(a5x + w, a5y + 50), (1325, a5y + 50)])
    s.text(a5x + w + 10, a5y + 22, "Проверенный\nзапрос, отчёт", anchor="start", size=12)
    for (code, t, x, y), c in zip(B, ["Правила анализа", "Шаблон промпта", "Требования безопасности", "Пороги исходов", "Метаданные эксперимента"]):
        s.line([(x + 95, y - 40), (x + 95, y)])
        s.text(x + 95, y - 52, c, size=12)
    for (code, t, x, y), c in zip(B, ["Rule Engine", "Языковая модель", "СУБД", "СУБД", "БД результатов"]):
        s.line([(x + 150, y + h + 40), (x + 150, y + h)])
        s.text(x + 150, y + h + 54, c, size=12)
    return s.svg()


# =================================================================== UML
def use_case() -> str:
    s = Svg(1050, 640, 14)
    s.box(260, 20, 520, 600, "", sw=1.5)
    s.text(520, 42, "AI Database Optimizer", bold=True)
    cases = ["Анализировать запрос", "Анализировать SQL-скрипт", "Оптимизировать\nс помощью ИИ",
             "Сравнить исходный\nи новый запросы", "Подключить базу данных", "Провести эксперимент",
             "Сформировать отчёт", "Экспортировать датасет"]
    ys = [90, 155, 225, 300, 370, 435, 500, 565]
    rx, ry = 150, 28
    s.actor(120, 250, "Пользователь")
    for y in ys:
        s.line([(142, 290), (520 - rx, y)], arrow=False)
    s.actor(930, 120, "Языковая\nмодель")
    s.actor(930, 380, "СУБД")
    for y in (225, 435):
        s.line([(908, 165), (520 + rx, y)], arrow=False)
    for y in (90, 300, 370, 435):
        s.line([(908, 425), (520 + rx, y)], arrow=False)
    for t, y in zip(cases, ys):
        s.ellipse(520, y, rx, ry, t, size=13)
    s.line([(520, 225 + ry), (520, 300 - ry)], dashed=True, open_head=True)
    s.text(530, 262, "«include»", anchor="start", size=12)
    return s.svg()


def sequence() -> str:
    s = Svg(1080, 700, 13)
    L = [("Пользователь", 95), ("Веб-интерфейс", 255), ("API (FastAPI)", 425), ("Конвейер", 595), ("Языковая\nмодель", 775), ("СУБД", 965)]
    for name, x in L:
        s.box(x - 72, 15, 144, 46, name, size=13)
        s.line([(x, 61), (x, 680)], arrow=False, dashed=True, sw=1)
    X = dict((n.split("\n")[0], x) for n, x in L)
    msgs = [("Пользователь", "Веб-интерфейс", "Оптимизировать", False),
            ("Веб-интерфейс", "API (FastAPI)", "POST /api/query/optimize", False),
            ("API (FastAPI)", "Конвейер", "optimize(запрос)", False),
            ("Конвейер", "СУБД", "схема, EXPLAIN", False),
            ("СУБД", "Конвейер", "метаданные, план", True),
            ("Конвейер", "Конвейер", "правила анализа", False),
            ("Конвейер", "Языковая", "контекст JSON", False),
            ("Языковая", "Конвейер", "кандидат JSON", True),
            ("Конвейер", "Конвейер", "безопасность, схема", False),
            ("Конвейер", "СУБД", "оба запроса", False),
            ("СУБД", "Конвейер", "контрольные суммы", True),
            ("Конвейер", "СУБД", "бенчмарк: 2 + 5 прогонов", False),
            ("СУБД", "Конвейер", "время, строки", True),
            ("Конвейер", "API (FastAPI)", "вердикт, метрики", True),
            ("API (FastAPI)", "Веб-интерфейс", "OptimizeResponse", True),
            ("Веб-интерфейс", "Пользователь", "результат и сравнение", True)]
    y = 95
    for a, b, t, ret in msgs:
        xa, xb = X[a], X[b]
        if xa == xb:
            s.line([(xa, y), (xa + 45, y), (xa + 45, y + 18), (xa + 4, y + 18)])
            s.text(xa + 52, y + 9, t, anchor="start", size=12)
            y += 40
            continue
        s.line([(xa, y), (xb, y)], dashed=ret, open_head=ret)
        # подпись — у начала стрелки, чтобы не попадать на чужие линии жизни
        mid = xa + (60 if xb > xa else -60) if abs(xb - xa) > 250 else (xa + xb) / 2
        s.text(mid, y - 10, t, anchor=("start" if xb > xa else "end") if abs(xb - xa) > 250 else "middle", size=12)
        y += 36
    return s.svg()


def states() -> str:
    s = Svg(1060, 520, 14)
    s.parts.append('<circle cx="35" cy="110" r="11" fill="#000"/>')
    st = {"got": (70, 80, 160, 60, "Получен ответ\nмодели"), "static": (330, 80, 160, 60, "Статически\nпроверен"),
          "run": (590, 80, 160, 60, "Выполнен\nна БД"), "meas": (850, 80, 160, 60, "Замерен"),
          "acc": (860, 360, 170, 56, "Принят"), "same": (560, 360, 190, 56, "Без изменений"),
          "rej": (200, 360, 190, 56, "Отклонён")}
    for k, (x, y, w, h, t) in st.items():
        s.box(x, y, w, h, t, rx=14)
    s.line([(46, 110), (70, 110)])
    s.line([(230, 110), (330, 110)]); s.text(280, 88, "формат\nверен", size=12)
    s.line([(490, 110), (590, 110)]); s.text(540, 88, "проверки\nпройдены", size=12)
    s.line([(750, 110), (850, 110)]); s.text(800, 88, "результат\nсовпал", size=12)
    s.line([(970, 140), (970, 360)]); s.text(978, 250, "k ≥ 1,05", anchor="start", size=12)
    s.line([(930, 140), (930, 270), (690, 270), (690, 360)]); s.text(810, 262, "0,95 ≤ k < 1,05", size=12)
    s.line([(890, 140), (890, 240), (350, 240), (350, 360)]); s.text(620, 232, "k < 0,95 (регресс)", size=12)
    s.line([(650, 140), (650, 210), (310, 210), (310, 360)]); s.text(480, 202, "результат изменился", size=12)
    s.line([(400, 140), (400, 180), (270, 180), (270, 360)]); s.text(408, 170, "ошибка схемы / безопасности", anchor="start", size=12)
    s.line([(110, 140), (110, 390), (200, 390)]); s.text(118, 300, "формат\nневерен", anchor="start", size=12)
    s.line([(190, 140), (190, 160), (230, 160), (230, 330), (620, 330), (620, 360)])
    s.text(430, 322, "запрос не предложен или совпадает с исходным", size=12)
    for x in (295, 655, 945):
        s.line([(x, 416), (x, 470)])
        s.parts.append(f'<circle cx="{x}" cy="482" r="11" fill="#fff" stroke="#000" stroke-width="1.5"/><circle cx="{x}" cy="482" r="6" fill="#000"/>')
    return s.svg()


# =================================================================== архитектура и ER
def architecture() -> str:
    s = Svg(1100, 660, 14)
    bands = [(20, 150, "Уровень представления (браузер)", "top"), (230, 200, "Уровень приложения (сервер FastAPI)", "top"),
             (490, 150, "Уровень данных и внешних сервисов", "bottom")]
    for y, h, t, pos in bands:
        s.box(10, y, 1080, h, "", sw=1.2, dashed=True)
        s.text(24, y + 18 if pos == "top" else y + h - 14, t, anchor="start", size=13, italic=True)
    for i, t in enumerate(["SQL Analyzer", "Сравнение", "Эксперименты", "Базы данных", "История\nи датасет"]):
        s.box(40 + i * 208, 55, 180, 70, t)
    s.text(550, 150, "React + TypeScript, Monaco Editor", size=12)
    mods = ["SQL Parser\n(sqlglot)", "Rule Engine,\nRewriter", "Safety Engine", "AI-модуль,\nпромпты", "Explain\nAnalyzer",
            "Equivalence,\nBenchmark", "Scoring", "Research Mode", "Хранилище\n(SQLAlchemy)", "REST API"]
    for i, t in enumerate(mods):
        s.box(30 + (i % 5) * 212, 265 + (i // 5) * 80, 190, 62, t, size=13)
    for t, x in [("БД результатов\n(SQLite / PostgreSQL)", 40), ("Исследуемые СУБД\n(MySQL, PostgreSQL)", 400),
                 ("Поставщики LLM (GigaChat,\nYandexGPT, OpenAI-совм., Ollama)", 760)]:
        s.box(x, 515, 300, 70, t, size=13)
    s.line([(550, 170), (550, 230)]); s.line([(530, 230), (530, 170)])
    s.text(565, 202, "HTTP, JSON (REST API)", anchor="start", size=12)
    for x, t in ((190, "SQL"), (550, "SQL, READ ONLY, таймаут"), (910, "HTTPS API")):
        s.line([(x, 430), (x, 515)])
        s.text(x + 10, 462, t, anchor="start", size=12)
    return s.svg()


ER = {
    "projects": (20, 20, ["PK id", "name", "created_at"]),
    "queries": (20, 200, ["PK id", "FK project_id", "sql_text", "sql_hash", "query_type, dbms"]),
    "database_connections": (20, 430, ["PK id", "FK project_id", "dbms, host, port", "database, username", "password_enc", "read_only_user"]),
    "analysis_runs": (340, 200, ["PK id", "FK query_id", "FK connection_id", "kind", "model_name", "prompt_version, prompt_sha256", "verdict, speedup", "result_equivalent", "app_version, dbms_version"]),
    "query_versions": (660, 20, ["PK id", "FK run_id", "source", "sql_text"]),
    "execution_plans": (660, 160, ["PK id", "FK run_id", "label, total_cost", "analyzed, raw"]),
    "benchmarks": (660, 300, ["PK id", "FK run_id", "label, runs, warmup", "median_ms, stdev_ms", "rows_examined"]),
    "ai_recommendations": (660, 460, ["PK id", "FK run_id", "provider, model", "system_prompt, user_prompt", "raw_response, parsed"]),
    "index_recommendations": (660, 620, ["PK id", "FK run_id", "table_name, columns", "sql, reason"]),
    "datasets": (980, 20, ["PK id", "name, version", "dbms, database_seed"]),
    "dataset_queries": (980, 160, ["PK id", "FK dataset_id", "key, title", "category, sql_text"]),
    "experiments": (980, 320, ["PK id", "FK dataset_id", "FK connection_id", "models, prompt_version", "status, progress"]),
    "experiment_results": (980, 510, ["PK id", "FK experiment_id", "FK dataset_query_id", "FK run_id", "model, outcome", "speedup, error_types"]),
}
ER_W = 250


def er_box(name):
    x, y, attrs = ER[name]
    return x, y, ER_W, 28 + 20 * len(attrs)


def er() -> str:
    s = Svg(1270, 860, 13)

    def rel(pts, one, many):
        """Связь 1:N по ломаной; one/many — координаты подписей."""
        s.line(pts, arrow=False)
        s.text(*one, "1", size=12)
        s.text(*many, "N", size=12)

    def mid(name, side):
        x, y, w, h = er_box(name)
        return {"l": (x, y + h / 2), "r": (x + w, y + h / 2), "t": (x + w / 2, y), "b": (x + w / 2, y + h)}[side]

    # projects -> queries (вниз), projects -> database_connections (левый канал)
    rel([mid("projects", "b"), mid("queries", "t")], (155, 116), (155, 192))
    p, d = mid("projects", "l"), mid("database_connections", "l")
    rel([p, (8, p[1]), (8, d[1]), d], (14, p[1] - 6), (14, d[1] - 6))
    # queries -> analysis_runs
    q = mid("queries", "r")
    rel([q, (340, q[1])], (q[0] + 8, q[1] - 6), (330, q[1] - 6))
    # database_connections -> analysis_runs
    d = mid("database_connections", "r")
    rel([d, (305, d[1]), (305, 380), (340, 380)], (d[0] + 8, d[1] - 6), (330, 374))
    # analysis_runs -> дочерние таблицы через канал x = 630
    r = mid("analysis_runs", "r")
    s.line([r, (630, r[1])], arrow=False)
    s.text(r[0] + 8, r[1] - 6, "1", size=12)
    for t in ("query_versions", "execution_plans", "benchmarks", "ai_recommendations", "index_recommendations"):
        c = mid(t, "l")
        s.line([(630, r[1]), (630, c[1]), c], arrow=False)
        s.text(c[0] - 10, c[1] - 6, "N", size=12)
    # datasets -> dataset_queries, experiments -> experiment_results (вниз)
    rel([mid("datasets", "b"), mid("dataset_queries", "t")], (1115, 116), (1115, 152))
    rel([mid("experiments", "b"), mid("experiment_results", "t")], (1115, 456), (1115, 502))
    # datasets -> experiments (правый канал 1245), dataset_queries -> experiment_results (правый канал 1260)
    a, b = mid("datasets", "r"), mid("experiments", "r")
    rel([a, (1245, a[1]), (1245, b[1]), b], (a[0] + 6, a[1] - 6), (b[0] + 8, b[1] - 6))
    a, b = mid("dataset_queries", "r"), mid("experiment_results", "r")
    rel([a, (1262, a[1]), (1262, b[1] + 30), (b[0], b[1] + 30)], (a[0] + 6, a[1] - 6), (b[0] + 8, b[1] + 24))
    # analysis_runs -> experiment_results (нижний канал y = 800)
    rb = mid("analysis_runs", "b")
    er_l = mid("experiment_results", "l")
    rel([rb, (rb[0], 800), (955, 800), (955, er_l[1] + 20), (980, er_l[1] + 20)], (rb[0] + 10, rb[1] + 14), (968, er_l[1] + 14))
    # database_connections -> experiments (нижний канал y = 830)
    db = mid("database_connections", "b")
    ex = mid("experiments", "l")
    rel([db, (db[0], 830), (940, 830), (940, ex[1]), (980, ex[1])], (db[0] + 10, db[1] + 14), (968, ex[1] - 6))

    for name, (x, y, attrs) in ER.items():
        _, _, w, h = er_box(name)
        s.box(x, y, w, h, "")
        s.box(x, y, w, 28, name, bold=True, fill="#eee")
        for i, a in enumerate(attrs):
            s.text(x + 8, y + 28 + 10 + i * 20, a, anchor="start", size=12)
    return s.svg()

# =================================================================== блок-схемы
def flow(steps, side_x=330, side_w=200, bus_x=570, w_main=240, width=620):
    """steps: ('term'|'proc'|'dec', текст, [текст ветки «Нет»]). Ветки «Нет» уходят вправо, их результаты собираются на шине."""
    cx = 30 + w_main / 2
    y = 40
    s = Svg(width, 10, 13)
    joins = []
    prev_bottom = None
    for kind, t, *rest in steps:
        h = 44 if kind == "term" else 70 if kind == "proc" else 90
        top = y
        if prev_bottom is not None:
            s.line([(cx, prev_bottom), (cx, top)], arrow=True)
            if prev_label:
                s.text(cx + 8, prev_bottom + 12, prev_label, anchor="start", size=12)
        prev_label = None
        if kind == "term":
            s.terminator(cx, top + h / 2, 170, h, t)
        elif kind == "proc":
            s.box(cx - w_main / 2, top, w_main, h, t)
        else:
            s.diamond(cx, top + h / 2, w_main, h, t, size=12)
            no = rest[0]
            by = top + h / 2
            s.line([(cx + w_main / 2, by), (side_x, by)])
            s.text(cx + w_main / 2 + 8, by - 8, "Нет", anchor="start", size=12)
            s.box(side_x, by - 30, side_w, 60, no, size=12)
            s.line([(side_x + side_w, by), (bus_x, by)], arrow=False)
            joins.append(by)
            prev_label = "Да"
        prev_bottom = top + h
        y = top + h + 34
    return s, cx, joins, prev_bottom, y


def flow_with_bus(steps_before, merge_text, end=True, width=640):
    s, cx, joins, bottom, y = flow(steps_before, width=width)
    bus_x = 570
    merge_y = y + 10
    # шина результатов
    top_join = min(joins)
    s.line([(bus_x, top_join), (bus_x, merge_y), (cx + 4, merge_y)])
    for j in joins:
        s.dot(bus_x, j)
    s.line([(cx, bottom), (cx, merge_y + 34 - 0)])
    s.dot(cx, merge_y)
    s.box(cx - 120, merge_y + 34, 240, 60, merge_text)
    s.line([(cx, merge_y + 94), (cx, merge_y + 128)])
    s.terminator(cx, merge_y + 150, 170, 44, "КОНЕЦ")
    s.h = merge_y + 190
    return s.svg()


def flow_decision() -> str:
    steps = [
        ("term", "НАЧАЛО"),
        ("proc", "Получить ответ\nязыковой модели"),
        ("dec", "Ответ в формате\nJSON?", "Отклонить:\nINVALID_RESPONSE"),
        ("dec", "Предложен\nновый запрос?", "Исход:\nбез изменений"),
        ("dec", "Безопасность и\nсхема в порядке?", "Отклонить:\nтип ошибки"),
        ("dec", "Подключена\nбаза данных?", "Статус:\nне проверено"),
        ("proc", "Выполнить оба запроса,\nсравнить контрольные\nсуммы результатов"),
        ("dec", "Результат\nсовпал?", "Отклонить:\nRESULT_CHANGED"),
        ("proc", "Бенчмарк: 2 прогрева,\n5 прогонов, k = t₀ / t₁"),
        ("dec", "k ≥ 0,95?", "Отклонить:\nPERFORMANCE_\nREGRESSION"),
        ("dec", "k ≥ 1,05?", "Исход:\nбез изменений"),
        ("proc", "Исход: принять\nрекомендацию"),
    ]
    return flow_with_bus(steps, "Сохранить результат\nи сформировать ответ")


def flow_equivalence() -> str:
    steps = [
        ("term", "НАЧАЛО"),
        ("proc", "Выполнить исходный запрос,\nдля каждой строки\nвычислить SHA-256"),
        ("proc", "Выполнить предложенный\nзапрос аналогично"),
        ("dec", "Число колонок\nсовпадает?", "Результат:\nразличаются"),
        ("dec", "Контрольные\nсуммы равны?", "Различаются,\nпоказать примеры\nстрок"),
        ("dec", "В исходном\nесть ORDER BY?", "Результат:\nэквивалентны"),
        ("dec", "Порядок строк\nсовпадает?", "Эквивалентны,\nпредупредить\nо порядке"),
        ("proc", "Результат:\nэквивалентны"),
    ]
    return flow_with_bus(steps, "Вернуть статус\nи подробности")


def main():
    import re
    items = {
        "d_idef0_a0": idef0_context(), "d_idef0_dec": idef0_decomposition(), "d_usecase": use_case(),
        "d_sequence": sequence(), "d_states": states(), "d_er": er(),  # d_arch — в diagrams2.py
        "d_flow_decision": flow_decision(), "d_flow_equiv": flow_equivalence(),
    }
    jobs = {}
    for name, svg in items.items():
        w = int(re.search(r'viewBox="0 0 (\d+)', svg).group(1))  # ширина берётся из самой схемы
        jobs[name] = (mf.page(svg, w), w)
    mf.render(jobs)


if __name__ == "__main__":
    main()
