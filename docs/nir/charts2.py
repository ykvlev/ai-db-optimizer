"""Диаграммы по данным экспериментов 5–11 для отчёта о НИР (PNG в figures/, сводка в charts2.json).

    python docs/nir/charts2.py   (нужен запущенный backend на :8000)
"""

from __future__ import annotations

import html
import importlib.util
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("mf", HERE / "make_figures.py")
mf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mf)

API = "http://127.0.0.1:8000"
F = "Times New Roman"
M = [("gigachat:GigaChat-2", "GigaChat-2"), ("gigachat:GigaChat-2-Pro", "GigaChat-2-Pro"), ("gigachat:GigaChat-2-Max", "GigaChat-2-Max"),
     ("ollama:qwen2.5-coder:7b", "Qwen2.5-Coder-7B"), ("baseline:rule-based", "Базовая линия")]
esc = html.escape
fx = lambda v, d=1: f"{v:.{d}f}".replace(".", ",")


def svg(w, h, body):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" font-family="{F}">{body}</svg>'


def t(x, y, s, size=24, anchor="middle", **kw):
    extra = "".join(f' {k.replace("_", "-")}="{v}"' for k, v in kw.items())
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}"{extra}>{esc(str(s))}</text>'


# ---------------------------------------------------------------- 1. воронка рекомендаций
def funnel(rows):
    """rows: [(имя, предложено, выполнено, совпало, улучшено)] из 80 задач."""
    w, left, bh, gap = 1000, 250, 34, 14
    stages = ["предложено", "выполнено", "результат совпал", "стало быстрее"]
    shades = ["#d9d9d9", "#a6a6a6", "#6e6e6e", "#2e9d57"]
    h = len(rows) * (4 * (bh + 4) + gap) + 90
    p = []
    y = 10
    for name, *vals in rows:
        p.append(t(left - 16, y + 2 * (bh + 4), name, 26, "end"))
        for i, v in enumerate(vals):
            bw = (w - left - 90) * v / 80
            p.append(f'<rect x="{left}" y="{y}" width="{max(bw, 1):.1f}" height="{bh}" fill="{shades[i]}" stroke="#000" stroke-width="1"/>')
            p.append(t(left + bw + 8, y + bh * 0.75, v, 22, "start"))
            y += bh + 4
        y += gap
    lx = 20
    for s, c in zip(stages, shades):
        p.append(f'<rect x="{lx}" y="{h - 40}" width="22" height="22" fill="{c}" stroke="#000"/>' + t(lx + 30, h - 22, s, 22, "start"))
        lx += 60 + len(s) * 11
    return svg(w, h, "".join(p))


# ---------------------------------------------------------------- 2. тепловая карта
def heatmap(cats, cols, cell):
    cw, ch, left, top = 150, 40, 330, 60
    w, h = left + cw * len(cols) + 10, top + ch * len(cats) + 10
    p = [t(left + cw * j + cw / 2, 40, c, 22) for j, c in enumerate(cols)]
    for i, (key, label, n) in enumerate(cats):
        y = top + ch * i
        p.append(t(left - 12, y + ch * 0.66, label, 21, "end"))
        for j, c in enumerate(cols):
            v = cell(key, j)
            a = v / n if n else 0
            fill = f"rgba(46,157,87,{0.1 + 0.85 * a:.2f})" if v else "#f2f2f2"
            p.append(f'<rect x="{left + cw * j + 2}" y="{y + 2}" width="{cw - 4}" height="{ch - 4}" fill="{fill}" stroke="#999" stroke-width="0.8"/>')
            p.append(t(left + cw * j + cw / 2, y + ch * 0.66, f"{v}/{n}" if v else "—", 20, fill="#fff" if a > 0.6 else "#000"))
    return svg(w, h, "".join(p))


# ---------------------------------------------------------------- 3. компромисс «скорость ответа — результат»
def tradeoff(points):
    w, h, l, b, r, tp = 1000, 560, 110, 90, 40, 30
    xs = [math.log10(x) for _, x, _ in points]
    x0, x1 = math.floor(min(xs)), math.ceil(max(xs))
    y1 = max(y for *_, y in points) + 4
    sx = lambda v: l + (w - l - r) * (math.log10(v) - x0) / (x1 - x0)
    sy = lambda v: h - b - (h - b - tp) * v / y1
    p = [f'<line x1="{l}" y1="{h - b}" x2="{w - r}" y2="{h - b}" stroke="#000"/>', f'<line x1="{l}" y1="{tp}" x2="{l}" y2="{h - b}" stroke="#000"/>']
    for e in range(x0, x1 + 1):
        x = sx(10 ** e)
        p.append(f'<line x1="{x}" y1="{h - b}" x2="{x}" y2="{h - b + 8}" stroke="#000"/>' + t(x, h - b + 34, fx(10 ** e, 0 if e >= 0 else 1) + " с", 22))
    for v in range(0, int(y1) + 1, 5):
        y = sy(v)
        p.append(f'<line x1="{l - 8}" y1="{y}" x2="{w - r}" y2="{y}" stroke="#ddd"/>' + t(l - 14, y + 7, v, 22, "end"))
    p.append(t((l + w - r) / 2, h - 12, "Среднее время ответа модели (логарифмическая шкала)", 24))
    p.append(f'<text transform="translate(28,{(tp + h - b) / 2}) rotate(-90)" font-size="24" text-anchor="middle">Улучшено запросов из 80</text>')
    for name, x, y in points:
        p.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="9" fill="#2e9d57" stroke="#000"/>' + t(sx(x) + 14, sy(y) - 12, name, 22, "start"))
    return svg(w, h, "".join(p))


# ---------------------------------------------------------------- 4. распределение ускорений
def strip(groups):
    """groups: [(имя, [ускорения])] — точки на логарифмической оси."""
    w, left, rowh = 1000, 250, 60
    h = len(groups) * rowh + 80
    lo, hi = -1, 2.2
    sx = lambda v: left + (w - left - 30) * (math.log10(v) - lo) / (hi - lo)
    p = []
    for e in (-1, 0, 1, 2):
        x = sx(10 ** e)
        p.append(f'<line x1="{x}" y1="0" x2="{x}" y2="{h - 60}" stroke="{"#000" if e == 0 else "#ccc"}" stroke-width="{2 if e == 0 else 1}"/>'
                 + t(x, h - 34, f"{fx(10 ** e, 0 if e >= 0 else 1)}x", 22))
    p.append(t((left + w) / 2, h - 6, "Ускорение (логарифмическая шкала; левее 1x — замедление)", 22))
    for i, (name, vals) in enumerate(groups):
        y = i * rowh + rowh / 2
        p.append(t(left - 14, y + 8, name, 24, "end"))
        for k, v in enumerate(sorted(vals)):
            jitter = ((k * 37) % 21 - 10) * 1.3
            col = "#2e9d57" if v >= 1.05 else ("#e08a2b" if v < 0.95 else "#888")
            p.append(f'<circle cx="{sx(max(v, 0.1)):.1f}" cy="{y + jitter:.1f}" r="6" fill="{col}" fill-opacity="0.75" stroke="#000" stroke-width="0.6"/>')
    return svg(w, h, "".join(p))


# ---------------------------------------------------------------- 5. стоимость плана против реального времени
def cost_vs_time(pts):
    """pts: [(отношение стоимости плана до/после, измеренное ускорение)]."""
    w, h, l, b, r, tp = 1000, 640, 110, 90, 30, 30
    lo, hi = -1.3, 2.3
    s = lambda v, a, bb, A, B: A + (B - A) * (math.log10(min(max(v, 10 ** lo), 10 ** hi)) - lo) / (hi - lo)
    sx = lambda v: s(v, lo, hi, l, w - r)
    sy = lambda v: s(v, lo, hi, h - b, tp)
    p = []
    for e in (-1, 0, 1, 2):
        p.append(f'<line x1="{sx(10 ** e)}" y1="{tp}" x2="{sx(10 ** e)}" y2="{h - b}" stroke="{"#000" if e == 0 else "#ddd"}"/>'
                 f'<line x1="{l}" y1="{sy(10 ** e)}" x2="{w - r}" y2="{sy(10 ** e)}" stroke="{"#000" if e == 0 else "#ddd"}"/>'
                 + t(sx(10 ** e), h - b + 32, f"{fx(10 ** e, 0 if e >= 0 else 1)}x", 22) + t(l - 12, sy(10 ** e) + 8, f"{fx(10 ** e, 0 if e >= 0 else 1)}x", 22, "end"))
    p.append(f'<line x1="{sx(10 ** lo)}" y1="{sy(10 ** lo)}" x2="{sx(10 ** hi)}" y2="{sy(10 ** hi)}" stroke="#999" stroke-dasharray="8,6"/>')
    for c, v in pts:
        same = abs(math.log10(c)) < 0.01  # оценка стоимости не изменилась — направление не предсказано
        agree = (c > 1) == (v > 1)
        fill = "#9a9a9a" if same else ("#2e9d57" if agree else "#d64545")
        p.append(f'<circle cx="{sx(c):.1f}" cy="{sy(v):.1f}" r="7" fill="{fill}" fill-opacity="0.7" stroke="#000" stroke-width="0.6"/>')
    p.append(t((l + w - r) / 2, h - 16, "Во сколько раз снизилась оценка стоимости плана", 24))
    p.append(f'<text transform="translate(30,{(tp + h - b) / 2}) rotate(-90)" font-size="24" text-anchor="middle">Измеренное ускорение</text>')
    return svg(w, h, "".join(p))


# ---------------------------------------------------------------- 6. устойчивость по прогонам
def stability(keys, runs_by_model):
    """runs_by_model: [(имя, {key: [исходы]})] — клетка на каждый прогон."""
    col = {"improved": "#2e9d57", "unchanged": "#e6e6e6", "worse": "#e08a2b", "invalid": "#d64545", "error": "#666"}
    cs, left, top = 22, 270, 70
    width_runs = [len(next(iter(d.values()))) for _, d in runs_by_model]
    w = max(left + sum(n * cs + 120 for n in width_runs) + 20, 900)
    h = top + cs * len(keys) + 80
    p = []
    x0 = left
    for (name, d), n in zip(runs_by_model, width_runs):
        p.append(t(x0 + n * cs / 2, 26, name, 20))
        p.append(t(x0 + n * cs / 2, 52, f"{n} прогона", 17))
        for i, k in enumerate(keys):
            for j, o in enumerate(d.get(k, [])):
                p.append(f'<rect x="{x0 + j * cs}" y="{top + i * cs}" width="{cs - 2}" height="{cs - 2}" fill="{col[o]}" stroke="#999" stroke-width="0.5"/>')
        x0 += n * cs + 120
    for i, k in enumerate(keys):
        p.append(t(left - 10, top + i * cs + cs * 0.72, k, 15, "end"))
    lx = 20
    for o, name in (("improved", "улучшено"), ("unchanged", "без изменений"), ("worse", "ухудшено"), ("invalid", "некорректно")):
        p.append(f'<rect x="{lx}" y="{h - 32}" width="18" height="18" fill="{col[o]}" stroke="#000"/>' + t(lx + 26, h - 17, name, 20, "start"))
        lx += 50 + len(name) * 10
    return svg(w, h, "".join(p))


# ---------------------------------------------------------------- 7. типы ошибок
def error_types(rows, types, bw=False):
    w, left, bh, gap = 1000, 250, 40, 16
    shades = ["#1a1a1a", "#7a7a7a", "#b5b5b5", "#4d4d4d", "#dcdcdc"] if bw else ["#d64545", "#e08a2b", "#8c564b", "#555", "#999"]
    h = len(rows) * (bh + gap) + 90
    mx = max(sum(c.values()) for _, c in rows) or 1
    p = []
    for i, (name, c) in enumerate(rows):
        y = i * (bh + gap)
        p.append(t(left - 14, y + bh * 0.7, name, 24, "end"))
        x = left
        for tp, sh in zip(types, shades):
            v = c.get(tp, 0)
            if not v:
                continue
            bw_ = (w - left - 60) * v / mx
            p.append(f'<rect x="{x:.1f}" y="{y}" width="{bw_:.1f}" height="{bh}" fill="{sh}" stroke="#000"/>')
            if bw_ > 26:
                p.append(t(x + bw_ / 2, y + bh * 0.7, v, 20, fill="#000" if bw and sh in ("#b5b5b5", "#dcdcdc") else "#fff"))
            x += bw_
        p.append(t(x + 8, y + bh * 0.7, sum(c.values()), 22, "start"))
    lx, ly = 20, h - 40
    names = {"RESULT_CHANGED": "изменён результат", "PERFORMANCE_REGRESSION": "замедление", "WRONG_COLUMN": "неверная колонка",
             "SYNTAX_ERROR": "синтаксис", "INVALID_RESPONSE": "формат ответа"}
    for tp, sh in zip(types, shades):
        nm = names.get(tp, tp)
        p.append(f'<rect x="{lx}" y="{ly}" width="20" height="20" fill="{sh}" stroke="#000"/>' + t(lx + 28, ly + 17, nm, 20, "start"))
        lx += 50 + len(nm) * 10
    return svg(w, h, "".join(p))


def main():
    c = httpx.Client(base_url=API, timeout=120)
    ex = {i: c.get(f"/api/experiments/{i}").json() for i in (5, 6, 7, 8, 9, 10, 11)}
    res = lambda i, m: [r for r in ex[i]["results"] if r["model"] == m]
    out = {}

    # воронка и тепловая карта — эксперименты 7 и 8 (одинаковые условия для всех участников)
    rows = []
    for mid, name in M:
        rr = res(7, mid) + res(8, mid)
        rows.append((name, sum(r["proposed"] for r in rr), sum(r["executed"] for r in rr),
                     sum(bool(r["equivalent"]) for r in rr), sum(r["outcome"] == "improved" for r in rr)))
    out["funnel"] = rows
    cats = [("date_function", "DATE()", 4), ("year_function", "YEAR() + LIMIT", 3), ("year_aggregate", "YEAR() в агрегате", 2),
            ("correlated_select", "подзапросы в SELECT", 3), ("correlated_exists", "EXISTS", 2), ("not_in", "NOT IN", 3),
            ("distinct_join", "DISTINCT + JOIN", 3), ("or_columns", "OR", 2), ("type_mismatch", "типы", 2), ("big_offset", "OFFSET", 3),
            ("leading_like", "LIKE '%…'", 2), ("in_subquery_agg", "IN + агрегат", 2), ("report", "отчёт с JOIN", 2),
            ("count_distinct_subquery", "COUNT DISTINCT", 1), ("max_per_group", "максимум в группе", 2), ("control", "контроль", 4)]
    cats2 = [(k, l, n * 2) for k, l, n in cats]
    cell = lambda key, j: sum(r["outcome"] == "improved" for r in res(7, M[j][0]) + res(8, M[j][0]) if r["category"] == key)

    # компромисс скорость/результат
    pts = []
    for mid, name in M[:4]:
        lat = statistics.fmean(v for i in (7, 8) for v in [ex[i]["summary"]["models"][mid]["avg_latency_ms"]]) / 1000
        pts.append((name, lat, sum(r["outcome"] == "improved" for r in res(7, mid) + res(8, mid))))
    out["tradeoff"] = pts

    # распределение ускорений (выполненные и эквивалентные кандидаты, эксп. 7–8)
    groups = [(name, [r["speedup"] for r in res(7, mid) + res(8, mid) if r["equivalent"] and r["speedup"]]) for mid, name in M]

    # стоимость плана против реального времени (эксп. 5–8, эквивалентные кандидаты)
    cv = []
    for i in (5, 6, 7, 8):
        for r in ex[i]["results"]:
            if r["equivalent"] and r["speedup"] and r["run_id"]:
                cmp_ = (c.get(f"/api/runs/{r['run_id']}").json()["result"].get("comparison") or {})
                a, b = (cmp_.get("plan_original") or {}).get("total_cost"), (cmp_.get("plan_optimized") or {}).get("total_cost")
                if a and b:
                    cv.append((a / b, r["speedup"]))
    changed = [(a, v) for a, v in cv if abs(math.log10(a)) >= 0.01]
    out["cost_vs_time"] = {"n": len(cv), "cost_unchanged": len(cv) - len(changed), "changed": len(changed),
                           "agree": sum((a > 1) == (v > 1) for a, v in changed),
                           "cost_better_but_slower": sum(a > 1 and v < 0.95 for a, v in changed),
                           "cost_worse_but_faster": sum(a < 1 and v > 1.05 for a, v in changed),
                           "unchanged_but_faster": sum(abs(math.log10(a)) < 0.01 and v >= 1.05 for a, v in cv)}

    # устойчивость: Pro — эксп. 7, 9, 10, 11 (с планом); Max — 7, 9, 10
    keys = [r["key"] for r in res(7, M[1][0])]
    stab = []
    for mid, name, exps in ((M[1][0], "Pro", (7, 9, 10, 11)), (M[2][0], "Max", (7, 9, 10))):
        d = defaultdict(list)
        for i in exps:
            for r in res(i, mid):
                d[r["key"]].append(r["outcome"])
        stab.append((name, dict(d)))
    out["stability"] = {name: {"always": sum(all(o == "improved" for o in v) for v in d.values()),
                               "ever": sum(any(o == "improved" for o in v) for v in d.values()),
                               "same": sum(len(set(v)) == 1 for v in d.values())} for name, d in stab}

    # типы ошибок (эксп. 7–8)
    types = ["RESULT_CHANGED", "PERFORMANCE_REGRESSION", "WRONG_COLUMN", "SYNTAX_ERROR", "INVALID_RESPONSE"]
    erows = []
    for mid, name in M:
        cnt = Counter(e for r in res(7, mid) + res(8, mid) for e in r["error_types"] if e in types)
        erows.append((name, cnt))
    out["errors"] = {n: dict(cn) for n, cn in erows}

    jobs = {
        "c_funnel": (mf.page(funnel(rows), 1000), 1000),
        "c_heatmap": (mf.page(heatmap(cats2, ["GigaChat-2", "Pro", "Max", "Qwen", "Правила"], cell), 1090), 1090),
        "c_tradeoff": (mf.page(tradeoff(pts), 1000), 1000),
        "c_speedups": (mf.page(strip(groups), 1000), 1000),
        "c_cost_time": (mf.page(cost_vs_time(cv), 1000), 1000),
        "c_stability": (mf.page(stability(keys, stab), 900), 900),
        "c_errors": (mf.page(error_types(erows, types), 1000), 1000),
        "c_errors_bw": (mf.page(error_types(erows, types, bw=True), 1000), 1000),
    }
    mf.render(jobs)
    (HERE / "charts2.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("cost_vs_time", "stability", "tradeoff")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
