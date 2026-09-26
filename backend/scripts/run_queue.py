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
GIGA = ["gigachat:GigaChat-2", "gigachat:GigaChat-2-Pro", "gigachat:GigaChat-2-Max"]

QUEUE = [
    ("Абляция: план выполнения в контексте (с планом / без плана), MySQL", "shop-bench-mini-v1", "mysql",
     [QWEN, f"{QWEN}@optimizer-v1-noplan"]),
    ("Полный прогон shop-bench-v1: qwen2.5-coder:7b vs базовая линия, MySQL", "shop-bench-v1", "mysql",
     [QWEN, "baseline:rule-based"]),
    ("Полный прогон shop-bench-v1: qwen2.5-coder:7b vs базовая линия, PostgreSQL", "shop-bench-v1", "postgres",
     [QWEN, "baseline:rule-based"]),
    ("Сравнение моделей shop-bench-v1: GigaChat-2 / Pro / Max, Qwen, базовая линия, MySQL", "shop-bench-v1", "mysql",
     [*GIGA, QWEN, "baseline:rule-based"]),
    ("Сравнение моделей shop-bench-v1: GigaChat-2 / Pro / Max, Qwen, базовая линия, PostgreSQL", "shop-bench-v1",
     "postgres", [*GIGA, QWEN, "baseline:rule-based"]),
]


def keep_awake(on: bool):
    if sys.platform == "win32":
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))


CONTAINERS = {"mysql": "aidbo-mysql", "postgres": "aidbo-postgres"}


def only_dbms(dbms: str):
    """Оставляет запущенной только нужную СУБД: освобождает память для локальной модели."""
    import subprocess
    for name, container in CONTAINERS.items():
        subprocess.run(["docker", "start" if name == dbms else "stop", container], capture_output=True)
    for _ in range(120):
        r = subprocess.run(["docker", "inspect", "-f", "{{.State.Health.Status}}", CONTAINERS[dbms]],
                           capture_output=True, text=True)
        if r.stdout.strip() == "healthy":
            return
        time.sleep(2)
    raise RuntimeError(f"{CONTAINERS[dbms]} не стал healthy")


def main():
    c = httpx.Client(base_url=API, timeout=60)
    ds = {(d["version"], d["dbms"]): d["id"] for d in c.get("/api/datasets").json()}
    conns = {x["dbms"]: x["id"] for x in c.get("/api/database/connections").json() if x["username"] == "optimizer_ro"}
    keep_awake(True)
    try:
        for name, version, dbms, models in QUEUE:
            existing = next((e for e in c.get("/api/experiments").json() if e["name"] == name), None)
            if existing and existing["status"] == "done":
                print(f"#{existing['id']} уже завершён: {name}", flush=True)
                continue
            only_dbms(dbms)
            if existing:  # продолжить прерванный: выполненные пары не повторяются
                c.post(f"/api/experiments/{existing['id']}/resume").raise_for_status()
                eid = existing["id"]
            else:
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
        import subprocess
        for container in CONTAINERS.values():  # после очереди обе СУБД снова доступны
            subprocess.run(["docker", "start", container], capture_output=True)
    print("очередь завершена", flush=True)


if __name__ == "__main__":
    main()
