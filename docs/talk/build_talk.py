"""Презентация научного доклада (16:9, PDF) по результатам экспериментов 1–11.

    python docs/talk/build_talk.py   → docs/talk/Доклад_AI_Database_Optimizer.pdf
Рисунки берутся из docs/nir/figures (make_figures.py, charts2.py), числа — из docs/nir/data.json и charts2.json.
"""

from __future__ import annotations

import html
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
NIR = HERE.parent / "nir"
FIG = NIR / "figures"
D = json.loads((NIR / "data.json").read_text(encoding="utf-8"))
C2 = json.loads((NIR / "charts2.json").read_text(encoding="utf-8"))
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
esc = html.escape

fun = {r[0]: r for r in C2["funnel"]}
st, ct = C2["stability"], C2["cost_vs_time"]
llm_rows = [r for k in ("3", "4", "5", "6", "7", "8", "9", "10", "11") for r in D["exp"][k]["results"] if not r["model"].startswith("baseline")]
n_llm = len(llm_rows)
n_prop = sum(r["proposed"] for r in llm_rows)
n_bad = sum(r["outcome"] in ("invalid", "worse") for r in llm_rows)
n_records = sum(len(D["exp"][k]["results"]) for k in D["exp"])


def img(name, h=440):
    return f'<img src="{(FIG / name).as_uri()}" style="max-height:{h}px;max-width:100%">'


def slide(n, kicker, title, body, cls=""):
    return (f'<section class="s {cls}"><div class="k">{esc(kicker)}</div><h2>{title}</h2>{body}'
            f'<div class="foot"><span>А. С. Яковлев · Политехнический колледж НовГУ</span><span>{n}</span></div></section>')


def kpi(v, label):
    return f'<div class="kpi"><b>{v}</b><span>{esc(label)}</span></div>'


S = []
S.append(f'''<section class="s title"><div class="k">Научный доклад · 2026</div>
<h1>Языковые модели в оптимизации SQL-запросов: что они умеют и почему их нужно проверять</h1>
<p class="lead">Экспериментальное исследование на СУБД MySQL и PostgreSQL</p>
<div class="who">Артём Сергеевич Яковлев<br>студент группы 5996, Политехнический колледж<br>Новгородского государственного университета имени Ярослава Мудрого</div>
<div class="links">github.com/ykvlev/ai-db-optimizer · DOI 10.5281/zenodo.22982517</div></section>''')
S.append(slide(2, "Проблема", "Медленный запрос — не всегда вина сервера", '''
<div class="two"><ul>
<li>Функция над колонкой, коррелированный подзапрос, <code>NOT IN</code> — и индекс не используется</li>
<li>Оптимизатор СУБД не исправляет формулировку запроса</li>
<li>Языковые модели умеют переписывать SQL, но склонны к <b>галлюцинациям</b>: другой результат, несуществующие колонки, замедление</li></ul>
<div class="q">Можно ли доверять модели ускорение запроса к рабочей базе данных?</div></div>'''))
S.append(slide(3, "Цель и вопросы", "Оценить пользу и надёжность моделей при обязательной проверке", '''
<ol class="big"><li>Сколько запросов модели реально ускоряют — по сравнению с набором правил?</li>
<li>Какие ошибки они допускают и чем их поймать?</li>
<li>Насколько устойчивы ответы моделей?</li>
<li>Можно ли заменить замеры оценкой оптимизатора СУБД?</li></ol>'''))
S.append(slide(4, "Метод", "Модель — только один шаг конвейера; решение принимают проверки", f'''
<div class="center">{img("fig_pipeline.png", 380)}</div>
<p class="note">Рекомендация принимается, только если результат совпал с исходным (контрольная сумма набора строк) и ускорение подтверждено замерами: 2 прогрева + 5 измерений с чередованием.</p>'''))
S.append(slide(5, "Стенд и данные", "Воспроизводимый эксперимент и открытые данные", f'''
<div class="kpis">{kpi("40", "запросов 16 категорий, включая контрольную группу")}{kpi("2 млн", "строк в базе интернет-магазина")}
{kpi("11", "экспериментов, MySQL 8.4 и PostgreSQL 16")}{kpi(str(n_records), "измеренных записей в открытом датасете")}</div>
<p class="note">Участники: GigaChat-2, GigaChat-2-Pro, GigaChat-2-Max (API), Qwen2.5-Coder-7B (локально), набор правил без ИИ. Одинаковый контекст и промпт, температура 0,1.</p>'''))
pro, bl = fun["GigaChat-2-Pro"], fun["Базовая линия"]
S.append(slide(6, "Результат 1", f"Лучшая модель ускорила {pro[4]} запросов из 80 — правила {bl[4]}", f'''
<div class="two"><div>{img("c_funnel.png", 430)}</div>
<ul><li>GigaChat-2-Pro: <b>{pro[4]}</b> улучшений из {pro[1]} предложенных изменений</li>
<li>Правила: <b>{bl[4]}</b> из {bl[1]} — предлагают редко, но точно</li>
<li>Размер модели не решает: старшая GigaChat-2-Max улучшила {fun["GigaChat-2-Max"][4]}</li>
<li>Результат определяет <b>склонность модели переписывать</b> — она же даёт ошибки</li></ul></div>'''))
S.append(slide(7, "Результат 2", "Модель находит то, чего нет в правилах", f'''
<div class="two"><div>{img("c_heatmap.png", 430)}</div>
<ul><li><code>NOT IN</code> → анти-соединение: ускорение до <b>31 раза</b></li>
<li>максимум в группе → оконная функция: до <b>4,2 раза</b></li>
<li>функции над датами исправляют все участники: до <b>100 раз</b></li></ul></div>'''))
S.append(slide(8, "Результат 3", f"{n_bad} ошибочных исходов на {n_prop} предложенных изменений", f'''
<div class="two"><div>{img("c_errors.png", 330)}</div>
<ul><li><b>Нарушение смысла</b>: <code>OFFSET 450000</code> → <code>id &gt; 450020</code> — те же 20 строк по числу, но другие</li>
<li><b>Галлюцинации схемы</b>: соединение по несуществующей колонке</li>
<li><b>Корректно, но медленнее</b>: подзапрос → <code>JOIN</code> замедлил в 1,3–7,8 раза</li>
<li>Все ошибки пойманы автоматически</li></ul></div>'''))
S.append(slide(9, "Результат 4", "Ответы модели нестабильны", f'''
<div class="two"><div>{img("c_stability.png", 440)}</div>
<ul><li>GigaChat-2-Pro: число улучшений стабильно (13–14), но во всех 4 прогонах — только <b>{st["Pro"]["always"]}</b> запросов, хотя бы раз — <b>{st["Pro"]["ever"]}</b></li>
<li>Один запрос ускорен в 118 раз лишь в 1 прогоне из 4</li>
<li>Вывод: несколько попыток с проверкой лучше одной</li></ul></div>'''))
S.append(slide(10, "Результат 5", "Оценка оптимизатора СУБД не заменяет замеров", f'''
<div class="two"><div>{img("c_cost_time.png", 420)}</div>
<ul><li>Направление угадано в <b>{round(ct["agree"] / ct["changed"] * 100)} %</b> случаев</li>
<li>{ct["cost_better_but_slower"]} раз оптимизатор считал запрос дешевле, а он стал медленнее</li>
<li>{ct["unchanged_but_faster"]} раз оценка не изменилась, а запрос ускорился</li></ul></div>'''))
S.append(slide(11, "Результат 6", "Одно и то же преобразование: быстрее на одной СУБД, медленнее на другой", f'''
<div class="center">{img("fig_divergent.png", 380)}</div>
<p class="note">Замена <code>YEAR(col) = N</code> диапазоном ускорила агрегирующий запрос на PostgreSQL и замедлила на MySQL — «учебные» правила нужно подтверждать измерением.</p>'''))
S.append(slide(12, "Выводы", "Модель — генератор кандидатов, решение — за измерением", '''
<ol class="big"><li>Лучшая модель превосходит набор правил и находит новые преобразования</li>
<li>Ошибки систематичны: для каждого типа есть проверка, которая его ловит</li>
<li>Ответы нестабильны — полезны повторные попытки</li>
<li>Ни самооценка модели, ни оценка оптимизатора не заменяют замеров</li></ol>'''))
S.append(slide(13, "Результаты работы", "Что сделано", '''
<div class="kpis">
<div class="kpi"><b>Программа</b><span>AI Database Optimizer: анализ, оптимизация, проверка, эксперименты; открытый код</span></div>
<div class="kpi"><b>Датасет</b><span>SQL Optimization Dataset с DOI на Zenodo, лицензия CC BY 4.0</span></div>
<div class="kpi"><b>Публикации</b><span>отчёт о НИР, статьи, тезисы, технический отчёт</span></div>
<div class="kpi"><b>Практика</b><span>поддержка GigaChat, YandexGPT и локальных моделей; только чтение из рабочих БД</span></div></div>
<p class="note">github.com/ykvlev/ai-db-optimizer · DOI 10.5281/zenodo.22982517 · Спасибо за внимание!</p>'''))

CSS = """
@page { size: 1280px 720px; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; font-family: "Segoe UI", Arial, sans-serif; color: #171717; background: #fafafa; }
.s { width: 1280px; height: 720px; padding: 56px 72px 40px; position: relative; page-break-after: always; background: #fafafa; }
.k { font-family: Consolas, "Courier New", monospace; font-size: 15px; letter-spacing: .07em; text-transform: uppercase; color: #666; }
h1 { font-size: 52px; font-weight: 500; letter-spacing: -0.03em; line-height: 1.05; margin: 18px 0 16px; max-width: 1050px; }
h2 { font-size: 34px; font-weight: 500; letter-spacing: -0.02em; line-height: 1.12; margin: 12px 0 26px; max-width: 1120px; }
.lead { font-size: 22px; color: #4d4d4d; margin: 0; }
.who { position: absolute; left: 72px; bottom: 96px; font-size: 19px; line-height: 1.45; color: #4d4d4d; }
.links { position: absolute; left: 72px; bottom: 50px; font-family: Consolas, monospace; font-size: 15px; color: #666; }
.title { border-left: 10px solid #171717; }
ul, ol { font-size: 22px; line-height: 1.45; margin: 0; padding-left: 26px; color: #262626; }
li { margin-bottom: 10px; }
ol.big { font-size: 27px; line-height: 1.5; }
.two { display: grid; grid-template-columns: 1.15fr 1fr; gap: 36px; align-items: center; }
.center { text-align: center; }
.note { font-size: 19px; color: #4d4d4d; margin-top: 18px; line-height: 1.45; }
.q { font-size: 30px; font-weight: 500; line-height: 1.25; border-left: 4px solid #297a3a; padding-left: 22px; }
.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 10px 0 8px; }
.kpi { background: #fff; border-radius: 8px; box-shadow: 0 0 0 1px rgba(0,0,0,.08); padding: 20px; }
.kpi b { display: block; font-size: 38px; font-weight: 500; letter-spacing: -0.03em; }
.kpi span { font-size: 16px; color: #4d4d4d; line-height: 1.35; display: block; margin-top: 6px; }
code { font-family: Consolas, monospace; font-size: .9em; background: #fff; box-shadow: 0 0 0 1px #ebebeb; border-radius: 4px; padding: 0 4px; }
b { font-weight: 600; }
.foot { position: absolute; left: 72px; right: 72px; bottom: 22px; display: flex; justify-content: space-between; font-family: Consolas, monospace; font-size: 13px; color: #a8a8a8; }
img { border-radius: 6px; }
"""
page = f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Доклад</title><style>{CSS}</style></head><body>{"".join(S)}</body></html>'
src = HERE / "talk.html"
src.write_text(page, encoding="utf-8")
out = HERE / "Доклад_AI_Database_Optimizer.pdf"
subprocess.run([EDGE, "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={out}", src.as_uri()],
               check=True, capture_output=True, timeout=240)
print(out.name, len(S), "слайдов")
