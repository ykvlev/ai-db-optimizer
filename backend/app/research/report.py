"""Автоматический научный отчёт по эксперименту (ТЗ, п. 35): Markdown и печатный HTML с SVG-графиками."""

from __future__ import annotations

import html
import math

from app.research.datasets import CATEGORIES
from app.services.ai.optimizer import BASELINE_MODEL
from app.research.stats import OUTCOME_NAMES, OUTCOMES

OUTCOME_COLORS = {"improved": "#2e9d57", "unchanged": "#9aa4b1", "worse": "#d9822b", "invalid": "#d64545", "error": "#6b5fc7"}
MODEL_COLORS = ["#2f6fdb", "#d9822b", "#2e9d57", "#8e44ad", "#c0392b", "#16a085"]


def _pct(v) -> str:
    return "—" if v is None else f"{v:.1f}%"


def _x(v) -> str:
    return "—" if v is None else f"{v:.2f}x"


def _ms(v) -> str:
    return "—" if v is None else f"{v:.1f}"


def _sec(v) -> str:
    return "—" if v is None else f"{v / 1000:.1f} с"


def conclusions(meta: dict, summary: dict) -> list[str]:
    models = summary["models"]
    if not models:
        return ["Результатов нет."]
    out = []
    n_queries = meta["n_queries"]
    for m, s in models.items():
        o = s["outcomes"]
        out.append(
            f"Модель {m}: из {s['n']} запросов улучшено {o['improved']} ({_pct(s['outcomes_pct']['improved'])}), "
            f"без изменений {o['unchanged']}, ухудшено {o['worse']}, некорректно {o['invalid']}"
            + (f", сбоев вызова {o['error']}" if o["error"] else "") + ". "
            + (f"Медианное ускорение среди эквивалентных кандидатов {_x(s['median_speedup'])}"
               + (f" (95% ДИ {_x(s['median_speedup_ci95'][0])}–{_x(s['median_speedup_ci95'][1])})" if s["median_speedup_ci95"] else "")
               + f", геометрическое среднее {_x(s['geomean_speedup'])}." if s["median_speedup"] else "Измеренных эквивалентных кандидатов нет."))
    if len(models) > 1:
        improved = {m: s["outcomes"]["improved"] for m, s in models.items()}
        top = max(improved.values())
        leaders = [m for m, v in improved.items() if v == top]
        if len(leaders) == 1:
            out.append(f"Наибольшее число подтверждённых улучшений — у {leaders[0]} ({top} из {n_queries}).")
        bad = {m: s["outcomes"]["invalid"] + s["outcomes"]["worse"] for m, s in models.items()}
        low = min(bad.values())
        safest = [m for m, v in bad.items() if v == low]
        if len(safest) == 1:
            out.append(f"Меньше всего некорректных и ухудшающих кандидатов — у {safest[0]} ({low}).")
    halluc = {m: s["hallucinations"] for m, s in models.items() if s["hallucinations"]}
    if halluc:
        out.append("Обнаружены галлюцинации схемы (несуществующие таблицы, колонки, индексы): "
                   + ", ".join(f"{m} — {v}" for m, v in halluc.items()) + ".")
    ctrl = summary["categories"].get("control")
    if ctrl:
        bad = {m: c["invalid"] + c["worse"] for m, c in ctrl.items() if c["invalid"] + c["worse"]}
        out.append("На контрольной группе (уже оптимальные запросы) "
                   + ("ни одна модель не ухудшила и не сломала запросы." if not bad else
                      "ухудшения или ошибки допустили: " + ", ".join(f"{m} — {v}" for m, v in bad.items()) + "."))
    return out


def markdown(meta: dict, summary: dict, rows: list[dict]) -> str:
    L = [f"# Отчёт по эксперименту №{meta['id']}: {meta['name']}", ""]
    L += ["## Параметры (воспроизводимость)", ""]
    for k, v in reproducibility(meta):
        L.append(f"- **{k}:** {v}")
    L += ["", "## Итоги по моделям", "",
          "| Модель | N | Улучшено | Без изм. | Ухудшено | Некорр. | Сбой | Предложено | Корр. SQL | Эквив. | Медиана ускорения (95% ДИ) | Геом. ср. | Галлюц. | Ср. время ответа |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for m, s in summary["models"].items():
        o, ci = s["outcomes"], s["median_speedup_ci95"]
        L.append(f"| {m} | {s['n']} | {o['improved']} | {o['unchanged']} | {o['worse']} | {o['invalid']} | {o['error']} | "
                 f"{s['proposed']} | {_pct(s['correct_sql_pct'])} | {_pct(s['equivalent_pct'])} | "
                 f"{_x(s['median_speedup'])}{f' ({_x(ci[0])}–{_x(ci[1])})' if ci else ''} | {_x(s['geomean_speedup'])} | "
                 f"{s['hallucinations']} | {_sec(s['avg_latency_ms'])} |")
    L += ["", "## Выводы", ""] + [f"- {c}" for c in conclusions(meta, summary)]
    models = list(summary["models"])
    L += ["", "## По категориям (улучшено / всего)", "", "| Категория | " + " | ".join(models) + " |",
          "|---|" + "---|" * len(models)]
    for cat, per in summary["categories"].items():
        L.append(f"| {CATEGORIES.get(cat, cat)} | " + " | ".join(
            f"{per[m]['improved']}/{per[m]['n']}" if m in per else "—" for m in models) + " |")
    L += ["", "## Типы ошибок", ""]
    for m, s in summary["models"].items():
        L.append(f"- {m}: " + (", ".join(f"{k} — {v}" for k, v in s["error_types"].items()) or "нет"))
    L += ["", "## Методика", "", *[f"- {x}" for x in methodology(meta)]]
    L += ["", "## Результаты по запросам", "", "| Запрос | Модель | Исход | Ускорение | До, мс | После, мс | Ошибки |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['key']} | {r['model']} | {OUTCOME_NAMES[r['outcome']]} | {_x(r['speedup'])} | "
                 f"{_ms(r['time_before_ms'])} | "
                 f"{_ms(r['time_after_ms'])} | "
                 f"{', '.join(r['error_types']) or '—'} |")
    return "\n".join(L) + "\n"


def reproducibility(meta: dict) -> list[tuple[str, str]]:
    llm_used = any(m != BASELINE_MODEL for m in meta["models"])
    return [
        ("experiment_id", str(meta["id"])),
        ("dataset_version", f"{meta['dataset_version']} ({meta['n_queries']} запросов)"),
        ("database_seed", str(meta["database_seed"])),
        ("dbms_version", f"{meta['dbms']} {meta['dbms_version'] or ''}"),
        ("application_version", meta["app_version"]),
        ("models", ", ".join(meta["models"])),
        ("model_parameters", str(meta["model_parameters"]) if llm_used else "не используются (только базовая линия)"),
        ("prompt_version", f"{meta['prompt_version']} (sha256 {str(meta['prompt_sha256'])[:12]}…)" if llm_used
         else "не используется (только базовая линия)"),
        ("benchmark", f"прогрев {meta['warmup']}, прогонов {meta['runs']}, чередование исходного и нового запроса"),
        ("timestamp", f"{meta['started_at']} — {meta['finished_at'] or 'не завершён'}"),
        ("status", meta["status"]),
    ]


def methodology(meta: dict) -> list[str]:
    return [
        "Для каждого запроса датасета и каждой модели выполнялся один и тот же конвейер: разбор SQL, получение схемы и "
        "плана выполнения, детерминированный анализ правилами, вызов модели со структурированным JSON-контекстом.",
        "Ответ модели проходил статическую проверку: безопасность (только один read-only SELECT), синтаксис, "
        "существование таблиц, колонок и индексов.",
        "Эквивалентность проверялась выполнением обоих запросов на одной БД: сравнивались мультимножества строк "
        "(порядконезависимая контрольная сумма), число колонок и порядок строк при ORDER BY.",
        f"Бенчмарк: {meta['warmup']} прогревочных и {meta['runs']} измеряемых прогонов, запуски исходного и "
        "оптимизированного запроса чередовались; метрика — медиана времени на клиенте.",
        "Исход «Улучшено» — результат совпал и ускорение ≥ 1,05x; «Без изменений» — модель не предложила изменений или "
        "ускорение в пределах ±5%; «Ухудшено» — результат совпал, но запрос медленнее более чем на 5%; "
        "«Некорректно» — ошибка синтаксиса, схемы, безопасности или изменение результата; «Сбой вызова» — ошибка "
        "инфраструктуры LLM (не учитывается как ошибка модели).",
        "Медиана ускорения считается по всем эквивалентным кандидатам (включая неизменившиеся и ухудшенные); "
        "95% доверительный интервал — перцентильный bootstrap (2000 выборок, seed 42).",
        "Рекомендованные моделями индексы не создавались: измерения отражают исходную схему БД.",
    ]


# ---------------------------------------------------------------- SVG
def svg_outcomes(summary: dict) -> str:
    models = list(summary["models"].items())
    if not models:
        return ""
    w, bar_h, gap, left = 760, 26, 14, 190
    h = len(models) * (bar_h + gap) + 40
    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Исходы по моделям">']
    for i, (m, s) in enumerate(models):
        y = i * (bar_h + gap) + 6
        parts.append(f'<text x="{left - 8}" y="{y + bar_h * 0.68}" text-anchor="end" font-size="12">{html.escape(m)}</text>')
        x = left
        for o in OUTCOMES:
            v = s["outcomes"][o]
            if not v:
                continue
            bw = (w - left - 10) * v / s["n"]
            parts.append(f'<rect x="{x:.1f}" y="{y}" width="{bw:.1f}" height="{bar_h}" fill="{OUTCOME_COLORS[o]}">'
                         f'<title>{OUTCOME_NAMES[o]}: {v}</title></rect>')
            if bw > 22:
                parts.append(f'<text x="{x + bw / 2:.1f}" y="{y + bar_h * 0.68}" text-anchor="middle" font-size="11" fill="#fff">{v}</text>')
            x += bw
    ly = len(models) * (bar_h + gap) + 20
    lx = left
    for o in OUTCOMES:
        parts.append(f'<rect x="{lx}" y="{ly - 9}" width="10" height="10" fill="{OUTCOME_COLORS[o]}"/>'
                     f'<text x="{lx + 14}" y="{ly}" font-size="11">{OUTCOME_NAMES[o]}</text>')
        lx += 22 + len(OUTCOME_NAMES[o]) * 6.5
    parts.append("</svg>")
    return "".join(parts)


def svg_speedups(rows: list[dict], models: list[str]) -> str:
    keys = list(dict.fromkeys(r["key"] for r in rows))
    pts = [r for r in rows if r["speedup"] and r["equivalent"]]
    if not pts or not keys:
        return ""
    w, h, left, bottom, top = 760, 300, 50, 90, 10
    lo = min(0.1, min(r["speedup"] for r in pts))
    hi = max(10.0, max(r["speedup"] for r in pts))
    ly0, ly1 = math.log10(lo), math.log10(hi)
    y = lambda v: top + (h - top - bottom) * (1 - (math.log10(v) - ly0) / (ly1 - ly0))
    step = (w - left - 10) / len(keys)
    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Ускорение по запросам (лог. шкала)">']
    for tick in (0.1, 0.5, 1, 2, 5, 10, 20, 50, 100):
        if lo <= tick <= hi:
            parts.append(f'<line x1="{left}" x2="{w - 10}" y1="{y(tick):.1f}" y2="{y(tick):.1f}" '
                         f'stroke="{"#555" if tick == 1 else "#ddd"}" stroke-width="{1.2 if tick == 1 else 0.6}"/>'
                         f'<text x="{left - 6}" y="{y(tick) + 4:.1f}" text-anchor="end" font-size="10">{tick:g}x</text>')
    for i, k in enumerate(keys):
        cx = left + step * (i + 0.5)
        parts.append(f'<text transform="translate({cx:.1f},{h - bottom + 8}) rotate(60)" font-size="9">{html.escape(k)}</text>')
    for r in pts:
        mi = models.index(r["model"]) if r["model"] in models else 0
        cx = left + step * (keys.index(r["key"]) + 0.5) + (mi - (len(models) - 1) / 2) * min(6, step / (len(models) + 1))
        parts.append(f'<circle cx="{cx:.1f}" cy="{y(r["speedup"]):.1f}" r="4" fill="{MODEL_COLORS[mi % len(MODEL_COLORS)]}" '
                     f'opacity="0.85"><title>{html.escape(r["key"])} · {html.escape(r["model"])}: {r["speedup"]:.2f}x</title></circle>')
    lx = left
    for mi, m in enumerate(models):
        parts.append(f'<circle cx="{lx + 5}" cy="{h - 8}" r="4" fill="{MODEL_COLORS[mi % len(MODEL_COLORS)]}"/>'
                     f'<text x="{lx + 13}" y="{h - 4}" font-size="11">{html.escape(m)}</text>')
        lx += 30 + len(m) * 6.5
    parts.append("</svg>")
    return "".join(parts)


def html_report(meta: dict, summary: dict, rows: list[dict]) -> str:
    e = html.escape
    models = list(summary["models"])
    model_rows = "".join(
        f"<tr><td>{e(m)}</td><td>{s['n']}</td>"
        + "".join(f"<td>{s['outcomes'][o]} <small>({_pct(s['outcomes_pct'][o])})</small></td>" for o in OUTCOMES)
        + f"<td>{_pct(s['correct_sql_pct'])}</td><td>{_pct(s['equivalent_pct'])}</td><td>{_x(s['median_speedup'])}"
        + (f"<br><small>ДИ {_x(s['median_speedup_ci95'][0])}–{_x(s['median_speedup_ci95'][1])}</small>" if s["median_speedup_ci95"] else "")
        + f"</td><td>{_x(s['geomean_speedup'])}</td><td>{s['hallucinations']}</td>"
        + f"<td>{_sec(s['avg_latency_ms'])}</td></tr>"
        for m, s in summary["models"].items())
    cat_rows = "".join(
        f"<tr><td>{e(CATEGORIES.get(c, c))}</td>" + "".join(
            f"<td>{per[m]['improved']}/{per[m]['n']}</td>" if m in per else "<td>—</td>" for m in models) + "</tr>"
        for c, per in summary["categories"].items())
    detail = "".join(
        f"<tr><td>{e(r['key'])}</td><td>{e(r['model'])}</td><td><span class='o o-{r['outcome']}'>{OUTCOME_NAMES[r['outcome']]}</span></td>"
        f"<td>{_x(r['speedup'])}</td><td>{'—' if r['time_before_ms'] is None else round(r['time_before_ms'], 1)}</td>"
        f"<td>{'—' if r['time_after_ms'] is None else round(r['time_after_ms'], 1)}</td><td>{e(', '.join(r['error_types']) or '—')}</td></tr>"
        for r in rows)
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>Эксперимент {meta['id']}: {e(meta['name'])}</title>
<style>
html{{color-scheme:light;background:#fff}} body{{background:#fff;font-family:"Segoe UI",system-ui,sans-serif;color:#1d232b;max-width:980px;margin:32px auto;padding:0 20px;line-height:1.5;font-size:14px}}
h1{{font-size:22px}} h2{{font-size:17px;margin-top:28px;border-bottom:1px solid #ddd;padding-bottom:4px}}
table{{border-collapse:collapse;width:100%;font-size:12.5px}} th,td{{border:1px solid #d8dde3;padding:4px 6px;text-align:left;vertical-align:top}}
th{{background:#f3f5f7}} small{{color:#666}} dl{{display:grid;grid-template-columns:200px 1fr;gap:2px 12px}} dt{{color:#666}}
.o{{padding:1px 6px;border-radius:3px;color:#fff;font-size:11.5px}} {''.join(f'.o-{k}{{background:{v}}}' for k, v in OUTCOME_COLORS.items())}
@media print{{body{{margin:0}} h2{{break-after:avoid}} tr{{break-inside:avoid}}}}
</style></head><body>
<h1>Эксперимент №{meta['id']}: {e(meta['name'])}</h1>
<p>AI Database Optimizer v{e(meta['app_version'])}. Отчёт сформирован автоматически; все показатели получены фактическим выполнением запросов.</p>
<h2>Параметры и воспроизводимость</h2>
<dl>{''.join(f'<dt>{e(k)}</dt><dd>{e(v)}</dd>' for k, v in reproducibility(meta))}</dl>
<h2>Итоги по моделям</h2>
<table><tr><th>Модель</th><th>N</th>{''.join(f'<th>{OUTCOME_NAMES[o]}</th>' for o in OUTCOMES)}<th>Корректный SQL*</th><th>Эквивалентно*</th><th>Медиана ускорения</th><th>Геом. среднее</th><th>Галлюцинации</th><th>Ср. время ответа</th></tr>{model_rows}</table>
<p><small>* доля среди запросов, где модель предложила изменённый SQL. Ускорение — по эквивалентным кандидатам.</small></p>
{svg_outcomes(summary)}
<h2>Выводы</h2><ul>{''.join(f'<li>{e(c)}</li>' for c in conclusions(meta, summary))}</ul>
<h2>Ускорение по запросам (логарифмическая шкала)</h2>
{svg_speedups(rows, models) or '<p>Нет измеренных эквивалентных кандидатов.</p>'}
<h2>По категориям (улучшено / всего)</h2>
<table><tr><th>Категория</th>{''.join(f'<th>{e(m)}</th>' for m in models)}</tr>{cat_rows}</table>
<h2>Типы ошибок</h2>
<ul>{''.join(f"<li>{e(m)}: {e(', '.join(f'{k} — {v}' for k, v in s['error_types'].items()) or 'нет')}</li>" for m, s in summary['models'].items())}</ul>
<h2>Методика</h2><ul>{''.join(f'<li>{e(x)}</li>' for x in methodology(meta))}</ul>
<h2>Результаты по запросам</h2>
<table><tr><th>Запрос</th><th>Модель</th><th>Исход</th><th>Ускорение</th><th>До, мс</th><th>После, мс</th><th>Ошибки</th></tr>{detail}</table>
</body></html>"""
