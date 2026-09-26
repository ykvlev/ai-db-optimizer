"""Отчёт «GigaChat в задаче оптимизации SQL-запросов: независимая экспериментальная оценка».

    python docs/gigachat/build_gigachat_report.py   (нужен запущенный backend на :8000)

Данные — эксперименты 7 (MySQL) и 8 (PostgreSQL). Результат: docs/gigachat/GigaChat_SQL_report.html и .pdf.
"""

from __future__ import annotations

import html
import math
import statistics
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
API = "http://127.0.0.1:8000"
EXPS = {"MySQL 8.4": 7, "PostgreSQL 16": 8}
M = [("gigachat:GigaChat-2", "GigaChat-2"), ("gigachat:GigaChat-2-Pro", "GigaChat-2-Pro"),
     ("gigachat:GigaChat-2-Max", "GigaChat-2-Max"), ("ollama:qwen2.5-coder:7b", "Qwen2.5-Coder-7B (локально)"),
     ("baseline:rule-based", "Правила (без ИИ)")]
SHORT = {"gigachat:GigaChat-2": "GigaChat-2", "gigachat:GigaChat-2-Pro": "Pro", "gigachat:GigaChat-2-Max": "Max",
         "ollama:qwen2.5-coder:7b": "Qwen", "baseline:rule-based": "Правила"}
OC = {"improved": "#2f9e5b", "unchanged": "#b8c0cc", "worse": "#e8913a", "invalid": "#d64545", "error": "#6b7280"}
ON = {"improved": "улучшено", "unchanged": "без изменений", "worse": "ухудшено", "invalid": "отклонено", "error": "сбой сети"}
CAT = {
    "date_function": "DATE() над колонкой", "year_function": "YEAR() и сортировка", "year_aggregate": "YEAR() в агрегате",
    "correlated_select": "подзапросы в SELECT", "correlated_exists": "коррелированный EXISTS", "not_in": "NOT IN с подзапросом",
    "distinct_join": "DISTINCT + JOIN", "or_columns": "OR по разным колонкам", "type_mismatch": "несовпадение типов",
    "big_offset": "большой OFFSET", "leading_like": "LIKE '%…'", "in_subquery_agg": "IN с агрегатом",
    "report": "отчёт с JOIN", "count_distinct_subquery": "COUNT по DISTINCT", "max_per_group": "максимум в группе",
    "control": "контроль (оптимальные)",
}
fx = lambda v, d=1: "—" if v is None else f"{v:.{d}f}".replace(".", ",")
esc = html.escape


def load():
    c = httpx.Client(base_url=API, timeout=60)
    data = {db: c.get(f"/api/experiments/{e}").json() for db, e in EXPS.items()}
    runs = {}

    def run(db, key, model):
        r = next(r for r in data[db]["results"] if r["key"] == key and r["model"] == model)
        x = c.get(f"/api/runs/{r['run_id']}").json()
        eq = ((x["result"].get("comparison") or {}).get("equivalence") or {})
        return {"row": r, "sql": x["sql"], "new": x["result"].get("optimized_query"), "eq": eq}

    runs["notin"] = run("MySQL 8.4", "not_in-1", "gigachat:GigaChat-2-Pro")
    runs["notin_pg"] = run("PostgreSQL 16", "not_in-1", "gigachat:GigaChat-2-Pro")
    runs["window"] = run("PostgreSQL 16", "max_per_group-1", "gigachat:GigaChat-2-Pro")
    runs["join_slow"] = run("MySQL 8.4", "correlated_select-1", "gigachat:GigaChat-2-Pro")
    runs["offset"] = run("MySQL 8.4", "big_offset-3", "gigachat:GigaChat-2")
    runs["using"] = run("MySQL 8.4", "distinct_join-1", "gigachat:GigaChat-2-Pro")
    runs["phone"] = run("MySQL 8.4", "type_mismatch-2", "gigachat:GigaChat-2-Max")
    idx = 0
    for d in data.values():
        for r in d["results"]:
            if r["model"] == "gigachat:GigaChat-2-Max" and not r["proposed"] and r["run_id"]:
                ai = c.get(f"/api/runs/{r['run_id']}").json()["result"].get("ai") or {}
                idx += bool(ai.get("recommended_indexes"))
    runs["max_only_index"] = idx
    return data, runs


def metrics(data):
    out = {}
    for db, d in data.items():
        for mid, _ in M:
            rows = [r for r in d["results"] if r["model"] == mid]
            o = Counter(r["outcome"] for r in rows)
            imp = [r["speedup"] for r in rows if r["outcome"] == "improved"]
            lat = [r["latency_ms"] for r in rows if r["latency_ms"] and mid.startswith(("gigachat", "ollama"))]
            proposed = sum(r["proposed"] for r in rows)
            out[(db, mid)] = {
                "n": len(rows), "o": o, "proposed": proposed,
                "hit": o["improved"] / proposed * 100 if proposed else None,  # доля полезных среди предложенных
                "geo_imp": math.exp(statistics.fmean(math.log(v) for v in imp)) if imp else None,
                "max": max(imp) if imp else None,
                "lat": statistics.median(lat) / 1000 if lat else None,
                "tok": statistics.fmean(r["prompt_tokens"] + r["completion_tokens"] for r in rows if r["prompt_tokens"]) if lat else None,
                "ctrl_touched": sum(1 for r in rows if r["category"] == "control" and r["proposed"]),
            }
    return out


# ------------------------------------------------------------------ графики
def stacked(data_rows, width=760):
    """Горизонтальные стековые полосы исходов: [(подпись, Counter, n)]."""
    bh, gap, left = 26, 10, 250
    h = len(data_rows) * (bh + gap) + 44
    p = [f'<svg viewBox="0 0 {width} {h}" class="chart" role="img">']
    for i, (label, o, n, group) in enumerate(data_rows):
        y = i * (bh + gap) + (8 if group else 0)
        p.append(f'<text x="{left - 10}" y="{y + bh * 0.7}" text-anchor="end" class="lbl">{esc(label)}</text>')
        x = left
        for k in OC:
            v = o.get(k, 0)
            if not v:
                continue
            w = (width - left - 4) * v / n
            p.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{bh}" fill="{OC[k]}"/>')
            if w > 18:
                p.append(f'<text x="{x + w / 2:.1f}" y="{y + bh * 0.7}" text-anchor="middle" class="val{" dark" if k == "unchanged" else ""}">{v}</text>')
            x += w
    ly, lx = h - 12, left
    for k in OC:
        p.append(f'<rect x="{lx}" y="{ly - 10}" width="11" height="11" fill="{OC[k]}"/><text x="{lx + 16}" y="{ly}" class="leg">{ON[k]}</text>')
        lx += 30 + len(ON[k]) * 7.2
    p.append("</svg>")
    return "".join(p)


def heat(data):
    cats = list(CAT)
    cw, ch, left, top = 84, 24, 190, 36
    w, h = left + cw * len(M), top + ch * len(cats) + 6
    p = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img">']
    for j, (mid, _) in enumerate(M):
        p.append(f'<text x="{left + cw * j + cw / 2}" y="22" text-anchor="middle" class="hd">{esc(SHORT[mid])}</text>')
    for i, cat in enumerate(cats):
        y = top + ch * i
        p.append(f'<text x="{left - 8}" y="{y + ch * 0.68}" text-anchor="end" class="lbl sm">{esc(CAT[cat])}</text>')
        for j, (mid, _) in enumerate(M):
            rows = [r for d in data.values() for r in d["results"] if r["model"] == mid and r["category"] == cat]
            n, imp = len(rows), sum(r["outcome"] == "improved" for r in rows)
            bad = sum(r["outcome"] in ("worse", "invalid") for r in rows)
            if cat == "control":
                fill = "#fde2e2" if bad else "#eef1f5"
                txt = f"{bad} ✗" if bad else "✓"
            else:
                a = imp / n if n else 0
                fill = f"rgba(47,158,91,{0.12 + 0.88 * a:.2f})" if imp else "#eef1f5"
                txt = f"{imp}/{n}" if imp else "·"
            p.append(f'<rect x="{left + cw * j + 2}" y="{y + 2}" width="{cw - 4}" height="{ch - 4}" rx="3" fill="{fill}"/>'
                     f'<text x="{left + cw * j + cw / 2}" y="{y + ch * 0.68}" text-anchor="middle" class="cell">{txt}</text>')
    p.append("</svg>")
    return "".join(p)


def latency_chart(mt):
    items = [(SHORT[mid], statistics.fmean(v for v in (mt[(db, mid)]["lat"] for db in EXPS) if v is not None))
             for mid, _ in M if not mid.startswith("baseline")]
    width, bh, gap, left = 760, 24, 10, 120
    mx = math.log10(max(v for _, v in items) * 1.5)
    mn = math.log10(1)
    sx = lambda v: left + (width - left - 80) * (math.log10(max(v, 1)) - mn) / (mx - mn)
    h = len(items) * (bh + gap) + 10
    p = [f'<svg viewBox="0 0 {width} {h}" class="chart" role="img">']
    for i, (lab, v) in enumerate(items):
        y = i * (bh + gap)
        color = "#3b6fd8" if lab != "Qwen" else "#8a94a6"
        p.append(f'<text x="{left - 10}" y="{y + bh * 0.7}" text-anchor="end" class="lbl">{esc(lab)}</text>'
                 f'<rect x="{left}" y="{y}" width="{sx(v) - left:.1f}" height="{bh}" rx="3" fill="{color}"/>'
                 f'<text x="{sx(v) + 8:.1f}" y="{y + bh * 0.7}" class="lbl">{fx(v)} с</text>')
    p.append("</svg>")
    return "".join(p)


# ------------------------------------------------------------------ страница
def sql(s):
    return f'<pre class="sql">{esc(s.strip())}</pre>'


def build():
    data, runs = load()
    mt = metrics(data)
    tot = lambda mid, k: sum(mt[(db, mid)]["o"][k] for db in EXPS)
    best = max((mid for mid, _ in M), key=lambda m: tot(m, "improved"))
    pro, g2, mx_ = "gigachat:GigaChat-2-Pro", "gigachat:GigaChat-2", "gigachat:GigaChat-2-Max"
    giga = [pro, g2, mx_]
    rejected_giga = sum(tot(m, "invalid") + tot(m, "worse") for m in giga)
    giga_lat = statistics.fmean(mt[(db, m)]["lat"] for db in EXPS for m in giga)
    qwen_lat = statistics.fmean(mt[(db, "ollama:qwen2.5-coder:7b")]["lat"] for db in EXPS)
    max_giga = max(mt[(db, m)]["max"] or 0 for db in EXPS for m in giga)
    corr = [r["speedup"] for d in data.values() for r in d["results"]
            if r["category"] == "correlated_select" and r["model"] in giga and r["speedup"]]
    corr_min, corr_max = min(corr), max(corr)
    only_idx = sum(1 for d in data.values() for r in d["results"] if r["model"] == mx_ and not r["proposed"])
    notin_max = max(r["speedup"] or 0 for d in data.values() for r in d["results"]
                    if r["model"] == pro and r["category"] == "not_in" and r["outcome"] == "improved")

    rows_tbl = []
    for db in EXPS:
        for mid, name in M:
            s = mt[(db, mid)]
            o = s["o"]
            dbs = db.split()[0]
            rows_tbl.append(
                f"<tr{' class=\"sep\"' if mid == M[0][0] and db != list(EXPS)[0] else ''}><td>{dbs}</td><td>{esc(name.replace(' (локально)', ''))}</td>"
                f"<td class='n g'>{o['improved']}</td><td class='n'>{o['unchanged']}</td><td class='n o'>{o['worse']}</td>"
                f"<td class='n r'>{o['invalid']}</td><td class='n'>{s['proposed']}</td><td class='n'>{fx(s['hit'], 0)}{' %' if s['hit'] is not None else ''}</td>"
                f"<td class='n'>{fx(s['geo_imp'])}{'x' if s['geo_imp'] else ''}</td><td class='n'>{fx(s['lat'], 0 if (s['lat'] or 0) > 20 else 1)}{' с' if s['lat'] else ''}</td></tr>")

    bars = []
    for db in EXPS:
        for i, (mid, name) in enumerate(M):
            s = mt[(db, mid)]
            bars.append((f"{db} · {SHORT[mid]}", s["o"], s["n"], i == 0 and db != list(EXPS)[0]))

    r = runs
    body = f"""
<header class="cover">
  <div class="kicker">Независимая экспериментальная оценка · сентябрь 2026</div>
  <h1>GigaChat в задаче оптимизации SQL-запросов</h1>
  <p class="lead">Три модели GigaChat, локальная модель и набор правил на одних и тех же 40 запросах к MySQL и PostgreSQL.
  Каждая рекомендация засчитывалась, только если результат запроса совпал с исходным, а время выполнения
  подтверждено замерами на реальной базе данных.</p>
  <div class="author">Артём Яковлев · студент Политехнического колледжа НовГУ им. Ярослава Мудрого<br>
  Программа: github.com/ykvlev/ai-db-optimizer · Данные: DOI 10.5281/zenodo.22982517</div>
</header>

<section class="kpis">
  <div class="kpi"><b>{tot(best, 'improved')}<small>/80</small></b><span>запросов ускорил {esc(SHORT[best] if best != pro else 'GigaChat-2-Pro')} — лучший результат среди всех участников</span></div>
  <div class="kpi"><b>{fx(max_giga, 0)}x</b><span>максимальное подтверждённое ускорение запроса моделью GigaChat</span></div>
  <div class="kpi"><b>{fx(giga_lat)} с</b><span>медианное время ответа GigaChat против {fx(qwen_lat, 0)} с у локальной 7B-модели</span></div>
  <div class="kpi"><b>{rejected_giga}</b><span>ответов GigaChat отклонено проверкой: изменён результат или запрос стал медленнее</span></div>
</section>

<section>
  <h2>Коротко</h2>
  <ul class="tldr">
    <li><b>GigaChat-2-Pro — самый результативный участник:</b> {tot(pro, 'improved')} улучшенных запросов из 80, больше, чем у правил ({tot('baseline:rule-based', 'improved')}) и локальной модели ({tot('ollama:qwen2.5-coder:7b', 'improved')}). Он единственный стабильно исправляет <code>NOT IN</code> (до {fx(notin_max, 0)}x) и «максимум в группе» через оконные функции.</li>
    <li><b>Смелость стоит ошибок.</b> Модели GigaChat предлагают изменения почти для каждого запроса, но часть переписываний меняет результат или замедляет запрос. Без автоматической проверки эти варианты выглядели бы как успех.</li>
    <li><b>GigaChat-2-Max самый осторожный:</b> в {only_idx} случаях из 80 он не стал переписывать запрос (в {runs['max_only_index']} из них предложил только индексы) и почти не допускал некорректных ответов.</li>
    <li><b>Скорость ответа 2–7 секунд</b> делает GigaChat пригодным для интерактивной работы, в отличие от локальной модели на процессоре.</li>
  </ul>
</section>

<section class="keep">
  <h2>Исходы по участникам</h2>
  <p class="note">По 40 запросов на каждой СУБД. «Отклонено» — изменён результат, ошибка схемы или формата ответа; «ухудшено» — результат совпал, но запрос медленнее более чем на 5 %.</p>
  {stacked(bars)}
</section>

<section class="pb">
  <h2>Сводная таблица</h2>
  <table class="t">
    <thead><tr><th>СУБД</th><th>Участник</th><th>Улучшено</th><th>Без изм.</th><th>Хуже</th><th>Откл.</th><th>Предложено</th><th>Точность*</th><th>Ускорение**</th><th>Ответ</th></tr></thead>
    <tbody>{''.join(rows_tbl)}</tbody>
  </table>
  <p class="note">* доля улучшений среди предложенных изменений. ** геометрическое среднее ускорения по улучшенным запросам.</p>
</section>

<section class="keep">
  <h2>Какие задачи решает каждый участник</h2>
  <p class="note">Число улучшенных запросов категории на двух СУБД. В строке контрольной группы (запросы, которые уже оптимальны) — число случаев, когда участник их ухудшил или сломал.</p>
  {heat(data)}
</section>

<section class="keep pb">
  <h2>Скорость ответа модели</h2>
  <p class="note">Медианное время ответа, логарифмическая шкала. Время ответа не входит в замер ускорения запроса.</p>
  {latency_chart(mt)}
</section>

<section>
  <h2>Сильные стороны: примеры</h2>
  <div class="case good">
    <h3>NOT IN → анти-соединение · GigaChat-2-Pro · MySQL · {fx(r['notin']['row']['speedup'], 1)}x</h3>
    <p>Модель заменила <code>NOT IN</code> с подзапросом на <code>LEFT JOIN … IS NULL</code>. Время выполнения — с {fx(r['notin']['row']['time_before_ms'], 0)} до {fx(r['notin']['row']['time_after_ms'], 1)} мс, результат совпал ({r['notin']['eq'].get('rows_original')} строк). На PostgreSQL то же преобразование дало {fx(r['notin_pg']['row']['speedup'], 1)}x. Правила переписывания для этого случая в системе нет.</p>
    <div class="two">{sql(r['notin']['sql'])}{sql(r['notin']['new'])}</div>
  </div>
  <div class="case good">
    <h3>Коррелированный подзапрос → оконная функция · GigaChat-2-Pro · PostgreSQL · {fx(r['window']['row']['speedup'], 1)}x</h3>
    <div class="two">{sql(r['window']['sql'])}{sql(r['window']['new'])}</div>
  </div>
</section>

<section class="pb">
  <h2>Где модели ошибаются</h2>
  <div class="case bad">
    <h3>Правдоподобно, быстро и неверно · GigaChat-2 · {fx(r['offset']['row']['speedup'], 0)}x, но отклонено</h3>
    <p>Модель заменила <code>OFFSET 450000</code> условием <code>id &gt; 450020</code>, предположив, что идентификаторы идут без пропусков. Запрос вернул те же 20 строк по количеству, но другие по содержанию; это выявила только контрольная сумма результата. Без проверки эквивалентности это выглядело бы как ускорение в {fx(r['offset']['row']['speedup'], 0)} раз.</p>
    <div class="two">{sql(r['offset']['sql'])}{sql(r['offset']['new'])}</div>
  </div>
  <div class="case bad">
    <h3>«Учебное» правило, которое замедляет · все три модели GigaChat · {fx(corr_min, 2)}–{fx(corr_max, 2)}x</h3>
    <p>Коррелированные подзапросы в <code>SELECT</code> модели заменяют соединением с агрегатом по всей таблице заказов. Результат верный, но на MySQL запрос стал медленнее в {fx(1 / r['join_slow']['row']['speedup'], 0)} раз ({fx(r['join_slow']['row']['time_before_ms'], 0)} → {fx(r['join_slow']['row']['time_after_ms'], 0)} мс): исходный запрос читал заказы только отобранных клиентов по индексу.</p>
    <div class="two">{sql(r['join_slow']['sql'])}{sql(r['join_slow']['new'])}</div>
  </div>
  <div class="case bad small">
    <h3>Другие типичные ошибки</h3>
    <ul>
      <li><b>Несуществующая колонка:</b> <code>JOIN orders o USING(user_id)</code> — в таблице users нет колонки user_id (GigaChat-2-Pro).</li>
      <li><b>Смена типа сравнения:</b> <code>phone = 79000012345</code> → <code>phone = '79000012345'</code>; числовое и строковое сравнение в MySQL дают разный результат ({r['phone']['eq'].get('rows_original')} строка → {r['phone']['eq'].get('rows_optimized')}) (GigaChat-2-Max).</li>
      <li><b>Изменение уже оптимальных запросов:</b> модели GigaChat трогали контрольную группу и в нескольких случаях ухудшали её; правила и локальная модель оставляли такие запросы без изменений.</li>
      <li><b>Нестабильность:</b> в пробном запуске GigaChat-2-Max ускорил запрос с <code>YEAR()</code> в 123 раза, а в эксперименте на том же запросе ограничился рекомендацией индекса (температура 0,1).</li>
    </ul>
  </div>
</section>

<section>
  <h2>Что могло бы улучшить модели GigaChat в этой задаче</h2>
  <ol class="rec">
    <li><b>Учитывать данные о селективности из плана выполнения.</b> Замена коррелированного подзапроса соединением выгодна не всегда: если внешний запрос фильтрует мало строк, исходный вариант быстрее.</li>
    <li><b>Не делать допущений о данных,</b> которые не следуют из схемы (непрерывность идентификаторов, отсутствие NULL, формат строк).</li>
    <li><b>Сверять колонки со схемой</b> перед использованием <code>USING</code> и именованных соединений.</li>
    <li><b>Оставлять оптимальные запросы без изменений:</b> ответ «изменения не требуются» тоже ценен.</li>
    <li><b>Стабильность ответа</b> при низкой температуре важна для инструментов, которые применяются к рабочим базам данных.</li>
  </ol>
</section>

<section class="keep">
  <h2>Методика</h2>
  <ul class="method">
    <li><b>Набор запросов:</b> shop-bench-v1 — 40 запросов 16 категорий, включая контрольную группу из 4 уже оптимальных запросов; для PostgreSQL — эквивалентные формулировки.</li>
    <li><b>Данные:</b> база интернет-магазина (100 000 клиентов, 500 000 заказов, 1,5 млн позиций), генерируется детерминированно.</li>
    <li><b>Контекст модели:</b> одинаковый для всех: запрос, схема с индексами и числом строк, план выполнения, проблемы, найденные правилами. Промпт optimizer-v1, температура 0,1.</li>
    <li><b>Проверки:</b> безопасность (только SELECT), соответствие схеме, эквивалентность результата (SHA-256 контрольная сумма набора строк с учётом повторов и порядка), бенчмарк: 2 прогрева и 5 замеров с чередованием исходного и нового запроса, медиана.</li>
    <li><b>Исходы:</b> улучшено — ускорение ≥ 1,05x при совпавшем результате; ухудшено — &lt; 0,95x.</li>
    <li><b>Стенд:</b> Intel Core i5-13420H, 16 ГБ ОЗУ, MySQL 8.4 и PostgreSQL 16 в Docker. Модели GigaChat — через GigaChat API (тариф для физических лиц), Qwen2.5-Coder-7B — через Ollama на процессоре.</li>
    <li><b>Ограничения:</b> каждый запрос обработан каждой моделью один раз; исходы вблизи порогов 0,95 и 1,05 чувствительны к шуму измерений; данные синтетические.</li>
  </ul>
  <h2>Воспроизводимость</h2>
  <p>Код системы, набор запросов, генератор базы данных и все 400 записей этих экспериментов, включая полные промпты и ответы моделей, открыты:
  github.com/ykvlev/ai-db-optimizer, датасет SQL Optimization Dataset (DOI 10.5281/zenodo.22982517, лицензия CC BY 4.0).</p>
  <p class="contact">Автор: Артём Яковлев · GitHub: ykvlev</p>
</section>
"""
    css = """
@page { size: A4; margin: 14mm 14mm 16mm; }
:root { --ink:#1b2330; --muted:#5b6678; --line:#dfe4ec; --accent:#2e5bd3; }
* { box-sizing: border-box; }
body { margin:0; font-family:"Segoe UI", Arial, sans-serif; color:var(--ink); font-size:10.5pt; line-height:1.45; background:#fff; }
h1 { font-size:26pt; line-height:1.15; margin:6px 0 10px; letter-spacing:-.3px; }
h2 { font-size:14pt; margin:18px 0 6px; color:var(--ink); border-left:4px solid var(--accent); padding-left:8px; }
h3 { font-size:11pt; margin:0 0 6px; }
.cover { border-bottom:1px solid var(--line); padding-bottom:12px; }
.kicker { color:var(--accent); font-weight:600; font-size:9.5pt; text-transform:uppercase; letter-spacing:.6px; }
.lead { font-size:11.5pt; color:#2d3748; margin:0 0 10px; }
.author { color:var(--muted); font-size:9.5pt; }
.kpis { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin:14px 0 4px; }
.kpi { border:1px solid var(--line); border-radius:8px; padding:10px 12px; background:#f7f9fc; }
.kpi b { display:block; font-size:22pt; color:var(--accent); line-height:1.1; }
.kpi b small { font-size:11pt; color:var(--muted); font-weight:500; }
.kpi span { font-size:8.8pt; color:#3a4556; }
.tldr li, .method li, .rec li { margin:4px 0; }
.note { color:var(--muted); font-size:9pt; margin:2px 0 8px; }
.chart { width:100%; height:auto; display:block; }
.chart .lbl { font-size:12px; fill:#1b2330; } .chart .lbl.sm { font-size:11.5px; }
.chart .val { font-size:11.5px; fill:#fff; font-weight:600; } .chart .val.dark { fill:#1b2330; }
.chart .leg { font-size:11px; fill:#3a4556; } .chart .hd { font-size:12px; font-weight:600; fill:#1b2330; }
.chart .cell { font-size:11.5px; fill:#1b2330; }
table.t { width:100%; border-collapse:collapse; font-size:8.9pt; }
.t th { text-align:left; font-weight:600; color:var(--muted); border-bottom:1.5px solid #b9c2d0; padding:4px 5px; }
.t td { border-bottom:1px solid var(--line); padding:3.5px 5px; }
.t tr.sep td { border-top:1.5px solid #b9c2d0; }
.t .n { text-align:right; font-variant-numeric:tabular-nums; }
.t .g { color:#1f7a44; font-weight:600; } .t .o { color:#b8640f; } .t .r { color:#b42f2f; }
.case { border:1px solid var(--line); border-radius:8px; padding:10px 12px; margin:10px 0; break-inside:avoid; }
.case.good { border-left:5px solid #2f9e5b; } .case.bad { border-left:5px solid #d64545; }
.case p { margin:0 0 8px; }
.two { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
pre.sql { margin:0; background:#f4f6fa; border-radius:6px; padding:8px; font:8.3pt/1.35 Consolas, "Courier New", monospace; white-space:pre-wrap; word-break:break-word; }
code { font-family:Consolas, "Courier New", monospace; font-size:.92em; background:#f1f3f7; padding:0 3px; border-radius:3px; }
.pb { break-before:page; }
.keep { break-inside:avoid; }
.t td { white-space:nowrap; }
section { break-inside:auto; }
.contact { color:var(--muted); }
"""
    page = f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>GigaChat и оптимизация SQL</title><style>{css}</style></head><body>{body}</body></html>'
    out = HERE / "GigaChat_SQL_report.html"
    out.write_text(page, encoding="utf-8")
    edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
    pdf = out.with_suffix(".pdf")
    subprocess.run([str(edge), "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf}", out.as_uri()],
                   check=True, capture_output=True, timeout=180)
    print("готово:", out.name, pdf.name)
    for mid, _ in M:
        print(f"{SHORT[mid]:8}", {db: dict(mt[(db, mid)]['o']) for db in EXPS})


if __name__ == "__main__":
    build()
