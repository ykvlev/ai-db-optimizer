"""Готовит рисунки (PNG) и числовые данные (data.json) для отчёта о НИР из результатов экспериментов.

    python docs/nir/make_figures.py
"""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
import websockets

HERE = Path(__file__).resolve().parent
FIG = HERE / "figures"
API = "http://127.0.0.1:8000"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

spec = importlib.util.spec_from_file_location("bm", HERE.parent / "konkurs" / "build_materials.py")
bm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bm)


PIPELINE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 430" width="1000" height="430" font-family="Times New Roman" font-size="19">
<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#000"/></marker></defs>
{boxes}
</svg>"""


def pipeline_svg() -> str:
    steps = [("1. Синтаксический", "разбор запроса"), ("2. Схема БД и", "план выполнения"), ("3. Детерминированный", "анализ (правила)"),
             ("4. Языковая модель:", "кандидат запроса"), ("5. Проверка", "безопасности"), ("6. Проверка", "соответствия схеме"),
             ("7. Проверка", "эквивалентности"), ("8. Бенчмарк и", "сравнение планов")]
    parts = []
    w, h = 205, 82
    xs = [30, 275, 520, 765]
    for i, (a, b) in enumerate(steps):
        row = i // 4
        col = i % 4 if row == 0 else 3 - i % 4
        x, y = xs[col], 40 + row * 190
        dash = ' stroke-dasharray="7,4"' if i == 3 else ""
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="#fff" stroke="#000" stroke-width="2"{dash}/>')
        parts.append(f'<text x="{x + w / 2}" y="{y + 35}" text-anchor="middle">{a}</text>'
                     f'<text x="{x + w / 2}" y="{y + 60}" text-anchor="middle">{b}</text>')
    for c in range(3):  # стрелки первой строки
        parts.append(f'<line x1="{xs[c] + w}" y1="81" x2="{xs[c + 1] - 4}" y2="81" stroke="#000" stroke-width="2" marker-end="url(#a)"/>')
    parts.append(f'<line x1="{xs[3] + w / 2}" y1="{40 + h}" x2="{xs[3] + w / 2}" y2="{226}" stroke="#000" stroke-width="2" marker-end="url(#a)"/>')
    for c in range(3, 0, -1):  # стрелки второй строки (справа налево)
        parts.append(f'<line x1="{xs[c]}" y1="271" x2="{xs[c - 1] + w + 4}" y2="271" stroke="#000" stroke-width="2" marker-end="url(#a)"/>')
    parts.append('<text x="500" y="370" text-anchor="middle" font-size="18">Отклонение кандидата на шагах 5–8: изменение результата, ошибка схемы,</text>'
                 '<text x="500" y="396" text-anchor="middle" font-size="18">опасная команда или замедление запроса</text>')
    return PIPELINE_SVG.format(boxes="".join(parts))


OC = {"improved": "#2e9d57", "unchanged": "#a3acb8", "worse": "#e08a2b", "invalid": "#d64545"}
ON = {"improved": "Улучшено", "unchanged": "Без изменений", "worse": "Ухудшено", "invalid": "Некорректно"}


def bars_big(rows) -> str:
    """Диаграмма исходов для печати: крупный шрифт при ширине рисунка 15–16 см."""
    w, bh, gap, left = 1000, 64, 26, 300
    h = len(rows) * (bh + gap) + 70
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" font-family="Times New Roman">']
    for i, (label, s) in enumerate(rows):
        y = i * (bh + gap)
        p.append(f'<text x="{left - 16}" y="{y + bh * 0.66}" text-anchor="end" font-size="32">{label}</text>')
        xx = left
        for o in OC:
            v = s["outcomes"][o]
            if not v:
                continue
            bw = (w - left - 6) * v / s["n"]
            p.append(f'<rect x="{xx:.1f}" y="{y}" width="{bw:.1f}" height="{bh}" fill="{OC[o]}" stroke="#000" stroke-width="1"/>')
            if bw > 34:
                p.append(f'<text x="{xx + bw / 2:.1f}" y="{y + bh * 0.68}" text-anchor="middle" font-size="32" fill="#000">{v}</text>')
            xx += bw
    lx, ly = 20, len(rows) * (bh + gap) + 44
    for o in OC:
        p.append(f'<rect x="{lx}" y="{ly - 22}" width="24" height="24" fill="{OC[o]}" stroke="#000" stroke-width="1"/>'
                 f'<text x="{lx + 32}" y="{ly}" font-size="28">{ON[o]}</text>')
        lx += 60 + len(ON[o]) * 14
    p.append("</svg>")
    return "".join(p)


def speed_big(items) -> str:
    """Горизонтальные бары ускорения, логарифмическая шкала, крупный шрифт."""
    import math
    w, bh, gap, left = 1000, 44, 16, 470
    h = len(items) * (bh + gap) + 50
    mx = math.log10(max(v for _, v in items) * 1.6)
    mn = math.log10(min(0.3, min(v for _, v in items) / 1.6))
    sx = lambda v: left + (w - left - 110) * (math.log10(v) - mn) / (mx - mn)
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" font-family="Times New Roman">',
         f'<line x1="{sx(1):.1f}" x2="{sx(1):.1f}" y1="0" y2="{h - 40}" stroke="#000" stroke-width="2"/>',
         f'<text x="{sx(1):.1f}" y="{h - 10}" font-size="24" text-anchor="middle">1x</text>']
    for i, (label, v) in enumerate(items):
        y = i * (bh + gap)
        x0, x1 = sorted((sx(1), sx(v)))
        color = "#2e9d57" if v >= 1.05 else ("#e08a2b" if v < 0.95 else "#a3acb8")
        p.append(f'<text x="{left - 12}" y="{y + bh * 0.7}" text-anchor="end" font-size="26">{label}</text>')
        p.append(f'<rect x="{x0:.1f}" y="{y}" width="{max(x1 - x0, 2):.1f}" height="{bh}" fill="{color}" stroke="#000" stroke-width="1"/>')
        tx, anchor = (x1 + 10, "start") if v >= 1 else (x0 - 10, "end")
        label_v = f"{v:.2f}".replace(".", ",") + "x"
        p.append(f'<text x="{tx:.1f}" y="{y + bh * 0.7}" font-size="26" text-anchor="{anchor}">{label_v}</text>')
    p.append("</svg>")
    return "".join(p)


def page(svg: str, width: int) -> str:
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>body{{margin:0;background:#fff;font-family:"Times New Roman"}}'
            f'#c{{width:{width}px;padding:10px}}</style></head><body><div id="c">{svg}</div></body></html>')


def render(html_by_name: dict[str, tuple[str, int]]):
    prof = tempfile.mkdtemp()
    proc = subprocess.Popen([EDGE, "--headless=new", "--remote-debugging-port=9335", f"--user-data-dir={prof}", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                ws_url = next(t["webSocketDebuggerUrl"] for t in httpx.get("http://127.0.0.1:9335/json", timeout=2).json()
                              if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.3)

        async def run():
            async with websockets.connect(ws_url, max_size=100_000_000) as ws:
                n = 0

                async def call(m, **pr):
                    nonlocal n
                    n += 1
                    await ws.send(json.dumps({"id": n, "method": m, "params": pr}))
                    while True:
                        r = json.loads(await ws.recv())
                        if r.get("id") == n:
                            return r.get("result", {})
                for name, (html, width) in html_by_name.items():
                    tmp = FIG / f"_{name}.html"
                    tmp.write_text(html, encoding="utf-8")
                    await call("Emulation.setDeviceMetricsOverride", width=width + 20, height=800, deviceScaleFactor=2, mobile=False)
                    await call("Page.navigate", url=tmp.as_uri())
                    await asyncio.sleep(1.0)
                    r = await call("Runtime.evaluate", returnByValue=True,
                                   expression="JSON.stringify(document.getElementById('c').getBoundingClientRect())")
                    b = json.loads(r["result"]["value"])
                    shot = await call("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                                      clip={"x": 0, "y": 0, "width": b["width"], "height": b["height"], "scale": 1})
                    (FIG / f"{name}.png").write_bytes(base64.b64decode(shot["data"]))
                    tmp.unlink()
                    print("PNG", name)
        asyncio.run(run())
    finally:
        proc.kill()
        shutil.rmtree(prof, ignore_errors=True)


def main():
    FIG.mkdir(exist_ok=True)
    c = httpx.Client(base_url=API, timeout=60)
    exps = {i: c.get(f"/api/experiments/{i}").json() for i in (1, 2, 3, 4, 5, 6)}
    m1 = exps[1]["summary"]["models"]["baseline:rule-based"]
    m2 = exps[2]["summary"]["models"]["baseline:rule-based"]
    e3 = exps[3]
    llm = next(k for k in e3["summary"]["models"] if not k.startswith("baseline"))
    l3, b3 = e3["summary"]["models"][llm], e3["summary"]["models"]["baseline:rule-based"]

    def sp(exp, key, model=None):
        return next((r["speedup"] for r in exp["results"] if r["key"] == key and (model is None or r["model"] == model)), None)

    neg = [("Выручка по статусам, MySQL", sp(exps[1], "year_aggregate-1")),
           ("Выручка по статусам, PostgreSQL", sp(exps[2], "year_aggregate-1")),
           ("Отчёт с JOIN, MySQL", sp(exps[1], "report-1")),
           ("Отчёт с JOIN, PostgreSQL", sp(exps[2], "report-1"))]
    per_q = [(r["title"], r["speedup"]) for r in e3["results"] if r["model"] == llm and r["equivalent"] and r["speedup"]]

    render({
        "fig_pipeline": (page(pipeline_svg(), 1000), 1000),
        "fig_baseline": (page(bars_big([("MySQL 8.4", m1), ("PostgreSQL 16", m2)]), 1000), 1000),
        "fig_llm": (page(bars_big([("Qwen2.5-Coder-7B", l3), ("Базовая линия", b3)]), 1000), 1000),
        "fig_speedup_llm": (page(speed_big(per_q), 1000), 1000),
        "fig_divergent": (page(speed_big(neg), 1000), 1000),
        "fig_full": (page(bars_big([("Qwen, MySQL", exps[5]["summary"]["models"][llm]),
                                    ("Базовая, MySQL", exps[5]["summary"]["models"]["baseline:rule-based"]),
                                    ("Qwen, PostgreSQL", exps[6]["summary"]["models"][llm]),
                                    ("Базовая, PostgreSQL", exps[6]["summary"]["models"]["baseline:rule-based"])]), 1000), 1000),
    })
    for name in ("screen_experiment.png", "screen_dashboard.png"):
        shutil.copy(HERE.parent / "konkurs" / "attachments" / name, FIG / name)

    caught = next(r for r in e3["results"] if r["model"] == llm and r["outcome"] == "invalid")
    caught_run = c.get(f"/api/runs/{caught['run_id']}").json()["result"]
    def run_of(exp_id, key):
        r = next(r for r in exps[exp_id]["results"] if r["key"] == key and r["model"] == llm)
        x = c.get(f"/api/runs/{r['run_id']}").json()
        return {"original": x["sql"], "optimized": x["result"].get("optimized_query"),
                "eq": (x["result"].get("comparison") or {}).get("equivalence"), "speedup": r["speedup"]}

    data = {
        "exp": {i: {"meta": exps[i]["meta"], "summary": exps[i]["summary"]["models"], "results": exps[i]["results"]}
                for i in exps},
        "llm": llm, "neg": neg, "per_q": per_q,
        "caught": {"title": caught["title"], "original": caught_run["comparison"]["original_sql"],
                   "optimized": caught_run["optimized_query"], "eq": caught_run["comparison"]["equivalence"],
                   "speedup": caught_run["comparison"]["speedup"], "summary": caught_run["ai"]["summary"]},
        "distinct": run_of(5, "distinct_join-2"),
        "reorder": run_of(5, "year_function-2"),
        "prompt": json.loads((HERE.parents[1] / "backend/app/services/ai/prompts/optimizer-v1.json").read_text(encoding="utf-8")),
    }
    (HERE / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("data.json")


if __name__ == "__main__":
    main()
