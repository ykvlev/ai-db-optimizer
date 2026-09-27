"""Дополнительные схемы для отчёта о НИР: UML-диаграммы компонентов, развёртывания, деятельности (с дорожками),
классов и диаграмма потоков данных. Чёрно-белые SVG в том же стиле, что diagrams.py.

    python docs/nir/diagrams2.py
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("dg", HERE / "diagrams.py")
dg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dg)
Svg, mf = dg.Svg, dg.mf


def component_icon(s: Svg, x, y, w, h, t, size=13):
    """Компонент UML: прямоугольник со значком компонента в правом верхнем углу."""
    s.box(x, y, w, h, t, size=size)
    ix, iy = x + w - 26, y + 8
    s.parts.append(f'<rect x="{ix}" y="{iy}" width="16" height="20" fill="#fff" stroke="#000" stroke-width="1.2"/>'
                   f'<rect x="{ix - 5}" y="{iy + 4}" width="10" height="4" fill="#fff" stroke="#000" stroke-width="1.2"/>'
                   f'<rect x="{ix - 5}" y="{iy + 12}" width="10" height="4" fill="#fff" stroke="#000" stroke-width="1.2"/>')
    return x, y, w, h


def lollipop(s: Svg, x, y, label, left=True):
    """Предоставляемый интерфейс: кружок на ножке."""
    s.parts.append(f'<circle cx="{x}" cy="{y}" r="8" fill="#fff" stroke="#000" stroke-width="1.5"/>')
    s.text(x + (-14 if left else 14), y - 16, label, anchor="end" if left else "start", size=12, italic=True)


def components() -> str:
    s = Svg(1100, 640, 14)
    component_icon(s, 40, 40, 250, 70, "Веб-интерфейс\n(React, Monaco)")
    component_icon(s, 425, 40, 250, 70, "REST API\n(FastAPI)")
    component_icon(s, 810, 40, 250, 70, "Research Mode\n(эксперименты, отчёты)")
    component_icon(s, 425, 200, 250, 70, "Конвейер оптимизации\n(pipeline)")
    names = [("Разбор SQL\n(sqlglot)", 40, 350), ("Правила\nи переписыватель", 250, 350), ("ИИ-модуль\n(промпты)", 460, 350),
             ("Проверка\nбезопасности", 670, 350), ("План выполнения\n(explain)", 880, 350),
             ("Эквивалентность\nи бенчмарк", 145, 490), ("Оценка\n(scoring)", 355, 490), ("Коннекторы СУБД", 565, 490),
             ("Поставщики LLM", 775, 490)]
    for t, x, y in names:
        component_icon(s, x, y, 190, 66, t, size=13)
    # зависимости (пунктир со стрелкой — «использует»)
    s.line([(290, 75), (425, 75)], dashed=True); s.text(357, 62, "HTTP/JSON", size=12)
    s.line([(810, 75), (675, 75)], dashed=True)
    s.line([(550, 110), (550, 200)], dashed=True)
    s.line([(935, 110), (935, 160), (640, 160), (640, 200)], dashed=True)
    for x in (135, 345, 555, 765, 975):
        s.line([(550, 270), (550, 310), (x, 310), (x, 350)], dashed=True)
    # нижний ряд: отдельная шина слева, чтобы линии не проходили через блоки среднего ряда
    s.line([(425, 250), (20, 250), (20, 465), (240, 465), (240, 490)], dashed=True)
    for x in (450, 660):
        s.line([(240, 465), (x, 465), (x, 490)], dashed=True)
    s.line([(620, 416), (620, 445), (870, 445), (870, 490)], dashed=True)
    s.box(20, 590, 1060, 34, "", sw=1, dashed=True)
    s.text(30, 607, "Пунктирная стрелка — зависимость «использует»; значок в углу — компонент UML", anchor="start", size=12, italic=True)
    return s.svg()


def node(s: Svg, x, y, w, h, title, d=14):
    """Узел UML: параллелепипед."""
    s.parts.append(f'<polygon points="{x},{y} {x + d},{y - d} {x + w + d},{y - d} {x + w},{y}" fill="#fff" stroke="#000" stroke-width="1.5"/>'
                   f'<polygon points="{x + w},{y} {x + w + d},{y - d} {x + w + d},{y + h - d} {x + w},{y + h}" fill="#fff" stroke="#000" stroke-width="1.5"/>')
    s.box(x, y, w, h, "")
    s.text(x + 12, y + 20, title, anchor="start", size=14, bold=True)


def deployment() -> str:
    s = Svg(1120, 620, 14)
    node(s, 30, 50, 760, 530, "«устройство» Компьютер пользователя (Windows / Linux / macOS)")
    s.box(60, 100, 220, 90, "«браузер»\nВеб-интерфейс\nlocalhost:5173", rx=4)
    s.box(330, 100, 240, 90, "«процесс Python»\nСервер FastAPI\nlocalhost:8000", rx=4)
    s.box(330, 250, 240, 70, "«файл»\nБД результатов\ndata/optimizer.db", rx=4)
    node(s, 60, 380, 480, 170, "«Docker»")
    s.box(90, 430, 200, 90, "«контейнер»\nMySQL 8.4\n:3307", rx=4)
    s.box(320, 430, 200, 90, "«контейнер»\nPostgreSQL 16\n:5434", rx=4)
    s.box(590, 250, 180, 90, "«процесс»\nOllama\n:11434", rx=4)
    node(s, 850, 120, 240, 150, "«облако»")
    s.box(870, 170, 200, 80, "GigaChat API\n(HTTPS, сертификат\nМинцифры)", rx=4)
    node(s, 850, 380, 240, 150, "«сервер организации»")
    s.box(870, 430, 200, 80, "Рабочая СУБД\n(только чтение)", rx=4)
    s.line([(280, 145), (330, 145)]); s.text(305, 132, "HTTP", size=12)
    s.line([(450, 190), (450, 250)]); s.text(460, 222, "SQLAlchemy", anchor="start", size=12)
    s.line([(380, 190), (380, 225), (300, 225), (300, 360), (190, 360), (190, 430)]); s.text(310, 290, "SQL", anchor="start", size=12)
    s.line([(300, 360), (420, 360), (420, 430)])
    s.line([(570, 160), (680, 160), (680, 250)]); s.text(690, 205, "HTTP", anchor="start", size=12)
    s.line([(570, 115), (835, 115), (835, 210), (870, 210)]); s.text(720, 103, "HTTPS", size=12)
    s.line([(570, 175), (815, 175), (815, 470), (870, 470)]); s.text(805, 330, "SQL,\nREAD ONLY", anchor="end", size=12)
    return s.svg()


def activity() -> str:
    """Диаграмма деятельности с дорожками: пользователь, сервер, СУБД, языковая модель."""
    lanes = ["Пользователь", "Сервер программы", "СУБД", "Языковая модель"]
    lw, top, h = 270, 20, 1010
    s = Svg(lw * len(lanes) + 20, h + 40, 13)
    for i, t in enumerate(lanes):
        s.box(10 + i * lw, top, lw, h, "", sw=1.2)
        s.box(10 + i * lw, top, lw, 36, t, bold=True)
    cx = [10 + i * lw + lw / 2 for i in range(len(lanes))]

    def act(lane, y, t, w=210, hh=52):
        s.box(cx[lane] - w / 2, y, w, hh, t, rx=16, size=13)
        return y + hh

    s.parts.append(f'<circle cx="{cx[0]}" cy="80" r="11" fill="#000"/>')
    s.line([(cx[0], 91), (cx[0], 115)])
    act(0, 115, "Ввести запрос,\nвыбрать базу и модель")
    s.line([(cx[0], 167), (cx[0], 190), (cx[1], 190), (cx[1], 205)])
    act(1, 205, "Разобрать запрос,\nпроверить безопасность")
    s.line([(cx[1], 257), (cx[1], 280), (cx[2], 280), (cx[2], 295)])
    act(2, 295, "Вернуть схему\nи план выполнения")
    s.line([(cx[2], 347), (cx[2], 370), (cx[1], 370), (cx[1], 385)])
    act(1, 385, "Применить правила,\nсобрать контекст")
    s.line([(cx[1], 437), (cx[1], 460), (cx[3], 460), (cx[3], 475)])
    act(3, 475, "Предложить\nновый запрос")
    s.line([(cx[3], 527), (cx[3], 550), (cx[1], 550), (cx[1], 565)])
    act(1, 565, "Проверить схему\nи безопасность ответа")
    s.diamond(cx[1], 675, 190, 70, "Ответ\nкорректен?")
    s.line([(cx[1], 617), (cx[1], 640)])
    s.line([(cx[1] + 95, 675), (cx[2] - 10, 675), (cx[2] - 10, 700)]); s.text(cx[1] + 130, 662, "да", size=12)
    act(2, 700, "Выполнить оба запроса:\nрезультат и замеры", w=230)
    s.line([(cx[2], 752), (cx[2], 775), (cx[1], 775), (cx[1], 790)])
    act(1, 790, "Сравнить результаты,\nвычислить ускорение")
    s.line([(cx[1] - 95, 675), (cx[0], 675), (cx[0], 880)]); s.text(cx[1] - 130, 662, "нет", size=12)
    s.line([(cx[1], 842), (cx[1], 860), (cx[0] + 40, 860), (cx[0] + 40, 880)])
    act(0, 880, "Получить вердикт:\nпринята / отклонена", w=220)
    s.line([(cx[0], 932), (cx[0], 960)])
    s.parts.append(f'<circle cx="{cx[0]}" cy="975" r="14" fill="#fff" stroke="#000" stroke-width="1.5"/>'
                   f'<circle cx="{cx[0]}" cy="975" r="8" fill="#000"/>')
    return s.svg()


def uml_class(s: Svg, x, y, w, name, attrs, methods, abstract=False):
    rows = [(name, True)] + [(a, False) for a in attrs] + [(m, False) for m in methods]
    hh = 30 + 19 * (len(attrs) + len(methods)) + 22 + (12 if abstract else 0)
    s.box(x, y, w, hh, "")
    s.text(x + w / 2, y + 16, ("«abstract»\n" if abstract else "") + name, italic=abstract, bold=True, size=13)
    top = y + (44 if abstract else 32)
    s.line([(x, top), (x + w, top)], arrow=False, sw=1.2)
    yy = top + 16
    for a in attrs:
        s.text(x + 8, yy, a, anchor="start", size=12); yy += 19
    s.line([(x, yy - 8), (x + w, yy - 8)], arrow=False, sw=1.2)
    yy += 6
    for m in methods:
        s.text(x + 8, yy, m, anchor="start", size=12); yy += 19
    return x, y, w, yy - y


def classes() -> str:
    s = Svg(1180, 700, 13)
    uml_class(s, 30, 20, 330, "ProviderRegistry", ["- providers: dict"], ["+ register(provider)", "+ model_ids(): list", "+ resolve(model_id): (LLMProvider, str)"])
    uml_class(s, 440, 20, 330, "LLMProvider", ["+ name: str", "+ models: list[str]"],
              ["+ complete(model, system, user,", "    temperature, json_mode): LLMResult"], abstract=True)
    subs = [("GigaChatProvider", 20), ("YandexGPTProvider", 310), ("OpenAICompatibleProvider", 600), ("OllamaProvider", 890)]
    for n, x in subs:
        uml_class(s, x, 250, 270, n, [], ["+ complete(...): LLMResult"])
        s.line([(x + 135, 250), (x + 135, 225), (605, 225), (605, 186)], open_head=True)
    s.line([(360, 80), (440, 80)]); s.text(400, 66, "1..*", size=12)
    uml_class(s, 30, 420, 330, "Connector", ["# config: ConnectionConfig"],
              ["+ server_version(): str", "+ introspect(): SchemaInfo", "+ explain(sql, analyze): plan", "+ run(sql): ExecResult", "+ privilege_report()"], abstract=True)
    for n, x in (("MySQLConnector", 440), ("PostgresConnector", 740)):
        uml_class(s, x, 500, 260, n, [], ["+ explain(...)", "+ run(...)"])
        s.line([(x + 130, 500), (x + 130, 470)], arrow=False)
    s.line([(870, 470), (400, 470), (400, 520), (360, 520)], open_head=True)
    uml_class(s, 900, 20, 260, "PromptTemplate", ["+ id, system, user", "+ sha256", "+ exclude_context", "+ response_format"], [])
    s.line([(770, 60), (900, 60)], dashed=True); s.text(835, 46, "«use»", size=12)
    return s.svg()


def dfd() -> str:
    """Диаграмма потоков данных (нотация Гейна — Сарсона)."""
    s = Svg(1120, 560, 13)

    def ext(x, y, w, h, t):
        s.box(x, y, w, h, t, sw=2.2)

    def proc(x, y, w, h, n, t):
        s.box(x, y, w, h, "", rx=14)
        s.text(x + w / 2, y + 16, n, size=12)
        s.line([(x, y + 28), (x + w, y + 28)], arrow=False, sw=1.2)
        s.text(x + w / 2, y + 28 + (h - 28) / 2, t)

    def store(x, y, w, t):
        s.parts.append(f'<polyline points="{x + w},{y} {x},{y} {x},{y + 40} {x + w},{y + 40}" fill="none" stroke="#000" stroke-width="1.5"/>'
                       f'<line x1="{x + 44}" y1="{y}" x2="{x + 44}" y2="{y + 40}" stroke="#000" stroke-width="1.5"/>')
        s.text(x + 22, y + 20, t.split("|")[0], size=12)
        s.text(x + 44 + (w - 44) / 2, y + 20, t.split("|")[1], size=12)

    ext(20, 230, 150, 70, "Пользователь")
    proc(250, 60, 200, 110, "1", "Анализ\nзапроса")
    proc(250, 330, 200, 110, "2", "Получение\nрекомендации")
    proc(560, 200, 200, 110, "3", "Проверка\nрекомендации")
    proc(860, 330, 200, 110, "4", "Сохранение\nрезультатов")
    ext(860, 60, 200, 70, "Исследуемая СУБД")
    ext(560, 440, 200, 70, "Языковая модель")
    store(830, 480, 260, "D1|БД результатов")
    s.line([(170, 250), (210, 250), (210, 115), (250, 115)]); s.text(215, 180, "SQL-запрос", anchor="start", size=12)
    s.line([(450, 100), (860, 100)]); s.text(655, 88, "запросы схемы и плана", size=12)
    s.line([(860, 118), (500, 118), (500, 150), (450, 150)]); s.text(655, 132, "схема, план", size=12)
    s.line([(350, 170), (350, 330)]); s.text(358, 250, "проблемы, контекст", anchor="start", size=12)
    s.line([(400, 440), (400, 475), (560, 475)]); s.text(480, 462, "промпт", size=12)
    s.line([(560, 495), (330, 495), (330, 440)]); s.text(470, 510, "новый запрос", size=12)
    s.line([(450, 385), (520, 385), (520, 255), (560, 255)]); s.text(528, 320, "кандидат", anchor="start", size=12)
    s.line([(760, 230), (960, 230), (960, 130)]); s.text(870, 218, "выполнение", size=12)
    s.line([(760, 275), (960, 275), (960, 330)]); s.text(880, 292, "вердикт, замеры", size=12)
    s.line([(960, 440), (960, 480)])
    s.line([(560, 290), (100, 290), (100, 300)]); s.text(230, 278, "вердикт и отчёт", size=12)
    return s.svg()


def main():
    items = {"d_components": components(), "d_deployment": deployment(), "d_activity": activity(),
             "d_classes": classes(), "d_dfd": dfd()}
    jobs = {}
    for name, svg in items.items():
        w = int(re.search(r'viewBox="0 0 (\d+)', svg).group(1))
        jobs[name] = (mf.page(svg, w), w)
    mf.render(jobs)


if __name__ == "__main__":
    main()
