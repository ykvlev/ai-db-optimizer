"""Чёрно-белые рисунки и сводка по оценке корпуса «Библиотека» (Qwen2.5-Coder-7B против Phi-3.5-mini).

    python docs/articles/sql_rewrite_validation/build_library_figures.py

Читает runs/library_evaluation_20261015/results.json, пишет SVG и PNG (Edge headless)
в runs/library_evaluation_20261015/figures/ и сводку library_summary.json рядом со скриптом.
Рисунки используют только чёрный, белый и оттенки серого.
"""

from __future__ import annotations

import html
import json
import subprocess
import tempfile
from collections import Counter, OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE / "runs" / "library_evaluation_20261015"
FIG = RUN / "figures"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
F = "Times New Roman"
esc = html.escape

MODEL_LABEL = {"qwen2.5-coder:7b": "Qwen2.5-Coder-7B", "phi3.5:3.8b": "Phi-3.5-mini 3.8B"}
CASE_INTENT = {
    "no_loans": "читатели без выдач",
    "loan_count": "число выдач по читателям",
    "zero_fee": "читатели с нулевой суммой сбора",
    "returned_count": "число возвращённых книг",
    "borrowers": "читатели дешёвых книг",
    "latest_ties": "последние выдачи с повторами дней",
    "price_range": "цены в диапазоне",
    "not_returned": "невозвращённые выдачи",
    "active_outer": "все читатели с активными выдачами",
    "union_bag": "объединение с сохранением кратностей",
    "all_returned": "читатели, у которых всё возвращено",
    "top_books": "две самые дорогие книги",
}
SHADE = {"unchanged": "#ffffff", "changed": "#b3b3b3", "refuted": "#111111"}


def svg(w: int, h: int, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'font-family="{F}">{body}</svg>'
    )


def t(x, y, s, size=24, anchor="middle", weight=None, fill="#000"):
    extra = f' font-weight="{weight}"' if weight else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" '
        f'fill="{fill}"{extra}>{esc(str(s))}</text>'
    )


def bar(x, y, w, h, key):
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, 1):.1f}" height="{h}" fill="{SHADE[key]}" stroke="#000" stroke-width="1.4"/>'


# ------------------------------------------------------------------ 1. исходы по моделям
def figure_outcomes(agg):
    w, bh, gap, left = 1000, 40, 14, 330
    stages = [("ответов получено", "responses"), ("переписываний предложено", "rewrites_offered"),
              ("из них опровергнуто", "counterexamples")]
    h = len(agg) * (len(stages) * (bh + 5) + gap) + 130
    p = []
    y = 14
    mx = max(v for a in agg.values() for _, k in stages for v in [a[k]]) or 1
    for model, a in agg.items():
        p.append(t(left - 18, y + 2.0 * (bh + 5), MODEL_LABEL.get(model, model), 26, "end"))
        for label, key in stages:
            v = a[key]
            bw = (w - left - 110) * v / mx
            shade = "refuted" if key == "counterexamples" else ("changed" if key == "rewrites_offered" else "unchanged")
            p.append(bar(left, y, bw, bh, shade))
            p.append(t(left + bw + 10, y + bh * 0.74, v, 23, "start"))
            y += bh + 5
        y += gap
    lx = 24
    for label, shade in [("предложено/получено", "unchanged"), ("изменённые", "changed"), ("опровергнуто", "refuted")]:
        p.append(f'<rect x="{lx}" y="{h - 52}" width="22" height="22" fill="{SHADE[shade]}" stroke="#000"/>')
        p.append(t(lx + 30, h - 34, label, 21, "start"))
        lx += 70 + len(label) * 11
    return svg(w, h, "".join(p))


# ------------------------------------------------------------------ 2. матрица по запросам
def figure_matrix(matrix, models, cases):
    left, top, cw, ch = 560, 62, 250, 42
    w = left + cw * len(models) + 20
    h = top + ch * len(cases) + 56
    p = [t(left + cw * j + cw / 2, 46, MODEL_LABEL.get(m, m), 23) for j, m in enumerate(models)]
    for i, c in enumerate(cases):
        y = top + ch * i
        p.append(t(left - 14, y + ch * 0.68, f"{c} — {CASE_INTENT.get(c, '')}", 20, "end"))
        for j, m in enumerate(models):
            cell = matrix[m][c]
            st = cell["status"]
            key = "refuted" if st == "counterexample" else ("unchanged" if cell.get("unchanged") else "changed")
            text = "опровергнут" if st == "counterexample" else ("без изменений" if cell.get("unchanged") else "изменён, не опровергнут")
            fill = "#fff" if key == "refuted" else "#000"
            p.append(bar(left + cw * j + 3, y + 3, cw - 6, ch - 6, key))
            p.append(t(left + cw * j + cw / 2, y + ch * 0.68, text, 19, fill=fill))
    return svg(w, h, "".join(p))


# ------------------------------------------------------------------ 3. какие состояния ловят ошибку
def figure_refuters(matrix, models, cases):
    rows = []
    for m in models:
        for c in cases:
            cell = matrix[m][c]
            if cell["status"] == "counterexample":
                rows.append((f"{MODEL_LABEL.get(m, m)} · {c}", len(cell["refuting_states"]),
                             cell.get("witness_state"), cell["refuting_states"]))
    rows.sort(key=lambda r: -r[1])
    w, bh, gap, left = 1000, 38, 44, 430
    h = len(rows) * (bh + gap) + 120
    mx = max(r[1] for r in rows) or 1
    p = []
    y = 16
    for label, n, witness, states in rows:
        bw = (w - left - 120) * n / mx
        p.append(t(left - 14, y + bh * 0.7, label, 21, "end"))
        p.append(bar(left, y, bw, bh, "refuted"))
        p.append(t(left + bw + 10, y + bh * 0.7, f"{n} из 28", 21, "start"))
        p.append(t(left + 4, y + bh + 22, f"минимальный свидетель: {witness}", 18, "start", fill="#333"))
        y += bh + gap
    return svg(w, h, "".join(p))


def render(items):
    FIG.mkdir(parents=True, exist_ok=True)
    for name, markup in items.items():
        (FIG / f"{name}.svg").write_text(markup, encoding="utf-8")
        head = markup[: markup.index(">")]
        width = int(head.split('width="')[1].split('"')[0])
        height = int(head.split('height="')[1].split('"')[0])
        page = (
            '<!doctype html><html><head><meta charset="utf-8"><style>'
            f'html,body{{margin:0;padding:0;background:#fff}}#c{{width:{width}px;height:{height}px}}'
            "</style></head><body><div id=\"c\">" + markup + "</div></body></html>"
        )
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / f"{name}.html"
            src.write_text(page, encoding="utf-8")
            png = FIG / f"{name}.png"
            subprocess.run(
                [str(EDGE), "--headless=new", "--disable-gpu", "--no-sandbox",
                 f"--user-data-dir={Path(tmp) / 'profile'}", "--hide-scrollbars",
                 "--force-device-scale-factor=2", f"--screenshot={png}",
                 f"--window-size={width},{height}", src.as_uri()],
                check=True, capture_output=True, timeout=120,
            )
        print("PNG", png.name, png.stat().st_size, "bytes")


def main():
    res = json.loads((RUN / "results.json").read_text(encoding="utf-8"))
    models = list(OrderedDict.fromkeys(r["model"] for r in res))
    cases = list(OrderedDict.fromkeys(r["case"] for r in res))
    tbl = {(r["model"], r["case"]): r for r in res}

    agg = {}
    for m in models:
        rows = [r for r in res if r["model"] == m]
        agg[m] = {
            "responses": len(rows),
            "rewrites_offered": sum(1 for r in rows if not r.get("unchanged")),
            "counterexamples": sum(1 for r in rows if r["status"] == "counterexample"),
            "checks": sum(len(r["checks"]) for r in rows),
            "refuting_checks": sum(1 for r in rows for k in r["checks"] if k["status"] == "counterexample"),
            "execution_errors": sum(1 for r in rows for k in r["checks"] if k["status"] == "execution_error"),
            "interface_mismatches": sum(1 for r in rows for k in r["checks"] if not k.get("interface_equal", True)),
            "unsupported": sum(1 for r in rows if r["status"] == "unsupported_or_unparsed"),
        }
    matrix = {
        m: {
            c: {
                "status": tbl[(m, c)]["status"],
                "unchanged": tbl[(m, c)].get("unchanged"),
                "candidate_sql": tbl[(m, c)].get("candidate_sql"),
                "refuting_states": [k["state"] for k in tbl[(m, c)]["checks"] if k["status"] == "counterexample"],
                "witness_state": (tbl[(m, c)].get("witness") or {}).get("state", {}).get("id"),
            }
            for c in cases
        }
        for m in models
    }
    shared = sorted({c for c in cases if all(matrix[m][c]["status"] == "counterexample" for m in models)})
    only = {m: sorted(c for c in cases if matrix[m][c]["status"] == "counterexample"
                      and not all(matrix[o][c]["status"] == "counterexample" for o in models)) for m in models}

    summary = {
        "source_run": str(RUN.relative_to(HERE.parent.parent.parent)),
        "corpus_sha256": json.loads((RUN / "summary.json").read_text(encoding="utf-8"))["corpus_sha256"],
        "models": agg,
        "shared_errors": shared,
        "errors_unique_to_model": only,
        "cases": cases,
        "matrix": matrix,
        "universal_equivalence_claim": False,
    }
    (HERE / "library_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print("wrote library_summary.json")

    render({
        "library_outcomes": figure_outcomes(agg),
        "library_case_matrix": figure_matrix(matrix, models, cases),
        "library_refuting_states": figure_refuters(matrix, models, cases),
    })


if __name__ == "__main__":
    main()
