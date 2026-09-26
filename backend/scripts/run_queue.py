"""Ночная очередь экспериментов: запускает эксперименты строго последовательно (замеры не мешают друг другу)
и не даёт Windows уснуть, пока очередь выполняется.

    python scripts/run_queue.py
"""

import ctypes
import sys
import time

import httpx

API = "http://127.0.0.1:8000"
QWEN = "ollama:qwen2.5-coder:7b"

QUEUE = [
    ("Абляция: план выполнения в контексте (с планом / без плана), MySQL", "shop-bench-mini-v1", "mysql",
     [QWEN, f"{QWEN}@optimizer-v1-noplan"]),
    ("Полный прогон shop-bench-v1: qwen2.5-coder:7b vs базовая линия, MySQL", "shop-bench-v1", "mysql",
     [QWEN, "baseline:rule-based"]),
    ("Полный прогон shop-bench-v1: qwen2.5-coder:7b vs базовая линия, PostgreSQL", "shop-bench-v1", "postgres",
     [QWEN, "baseline:rule-based"]),
]


def keep_awake(on: bool):
    if sys.platform == "win32":
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))


def main():
    c = httpx.Client(base_url=API, timeout=60)
    ds = {(d["version"], d["dbms"]): d["id"] for d in c.get("/api/datasets").json()}
    conns = {x["dbms"]: x["id"] for x in c.get("/api/database/connections").json() if x["username"] == "optimizer_ro"}
    keep_awake(True)
    try:
        for name, version, dbms, models in QUEUE:
            r = c.post("/api/experiments", json={"name": name, "dataset_id": ds[(version, dbms)],
                                                 "connection_id": conns[dbms], "models": models, "runs": 5, "warmup": 2})
            r.raise_for_status()
            eid = r.json()["id"]
            t0 = time.time()
            print(f"[{time.strftime('%H:%M')}] старт #{eid}: {name}", flush=True)
            while True:
                m = c.get(f"/api/experiments/{eid}").json()["meta"]
                if not m["running"] and m["status"] != "pending":
                    break
                time.sleep(30)
            print(f"[{time.strftime('%H:%M')}] #{eid} {m['status']} {m['progress_done']}/{m['progress_total']} "
                  f"за {(time.time() - t0) / 60:.0f} мин {m['error'] or ''}", flush=True)
    finally:
        keep_awake(False)
    print("очередь завершена", flush=True)


if __name__ == "__main__":
    main()
