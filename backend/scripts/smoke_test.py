"""Интеграционная проверка против запущенного backend и тестовых БД из docker/.

    python scripts/smoke_test.py [http://127.0.0.1:8000]
"""

import sys

import httpx

B = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
c = httpx.Client(base_url=B, timeout=300)


def post(url, body):
    r = c.post(url, json=body)
    if r.status_code >= 400:
        print("  !!", r.status_code, r.text[:500])
        return None
    return r.json()


conns = {x["dbms"]: x["id"] for x in c.get("/api/database/connections").json() if x["username"] == "optimizer_ro"}
for dbms, port in (("mysql", 3307), ("postgres", 5434)):
    if dbms not in conns:
        r = post("/api/database/connect", {"name": f"Демо {dbms}", "dbms": dbms, "host": "127.0.0.1", "port": port,
                                           "database": "shop", "username": "optimizer_ro", "password": "optimizer_ro"})
        conns[dbms] = r["id"]
        print(f"connected {dbms}: v{r['server_version']} read_only={r['read_only_user']} {r['warnings']}")

schema = c.get(f"/api/database/{conns['mysql']}/schema").json()
print("mysql schema:", [(t["name"], t["row_count"], [i["name"] for i in t["indexes"]]) for t in schema["tables"]])

examples = c.get("/api/examples").json()["queries"]
for dbms in ("mysql", "postgres"):
    print(f"\n===== {dbms}")
    for ex in examples:
        a = post("/api/query/analyze", {"sql": ex[dbms], "dbms": dbms, "connection_id": conns[dbms]})
        if not a:
            continue
        plan = a["plan"] or {}
        print(f"- {ex['id']:15} issues={[i['code'] for i in a['issues']]} cost={plan.get('total_cost')} "
              f"scans={plan.get('full_scans')} rewrite={'yes' if a['rule_rewrite'] else 'no'}")
        if a["rule_rewrite"]:
            cmp = post("/api/query/compare", {"original_sql": ex[dbms], "optimized_sql": a["rule_rewrite"],
                                              "connection_id": conns[dbms], "runs": 3, "warmup": 1})
            if cmp:
                print(f"    rule rewrite: eq={cmp['equivalence']['status']} "
                      f"{cmp['benchmark_original']['median_ms']:.1f} → {cmp['benchmark_optimized']['median_ms']:.1f} ms "
                      f"speedup={cmp['speedup']} score={cmp['score']['score']} examined="
                      f"{cmp['benchmark_original']['rows_examined']}→{cmp['benchmark_optimized']['rows_examined']}")
                print("    plan:", cmp["plan_changes"])

# отрицательный сценарий: изменённый результат должен быть отклонён
cmp = post("/api/query/compare", {"original_sql": "SELECT id FROM orders WHERE user_id = 5",
                                  "optimized_sql": "SELECT id FROM orders WHERE user_id = 6",
                                  "connection_id": conns["mysql"], "runs": 2, "warmup": 0})
print("\nresult-changed check:", cmp["equivalence"]["status"], cmp["equivalence"]["details"], cmp["score"])
# опасный запрос не должен выполняться
print("dangerous:", c.post("/api/query/compare", json={"original_sql": "SELECT 1", "optimized_sql": "DELETE FROM orders",
                                                          "connection_id": conns["mysql"]}).json()["errors"])
print("stats:", c.get("/api/stats").json())
