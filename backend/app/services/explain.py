"""Execution Plan Analyzer: нормализация планов MySQL (EXPLAIN FORMAT=JSON) и PostgreSQL (FORMAT JSON)
в единое дерево PlanNode и выявление проблем (full scan, filesort, temporary и т.д.)."""

from __future__ import annotations

from typing import Any

from app.models import Issue, PlanNode, PlanSummary

BIG_SCAN_ROWS = 1000
HUGE_SCAN_ROWS = 100_000


def _f(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ====================================================================== MySQL
_MYSQL_ACCESS = {
    "ALL": "Full table scan",
    "index": "Full index scan",
    "range": "Index range scan",
    "ref": "Index lookup",
    "eq_ref": "Unique index lookup",
    "const": "Const lookup",
    "system": "Const lookup",
    "ref_or_null": "Index lookup (or NULL)",
    "index_merge": "Index merge",
    "fulltext": "Fulltext index",
    "unique_subquery": "Unique subquery",
    "index_subquery": "Index subquery",
}
_MYSQL_OPS = {
    "ordering_operation": "Order",
    "grouping_operation": "Group",
    "duplicates_removal": "Distinct",
    "windowing": "Window",
    "buffer_result": "Buffer",
}


class _MySQLWalker:
    def __init__(self):
        self.full_scans: list[str] = []
        self.index_accesses: list[str] = []
        self.filesort = False
        self.temporary = False
        self.examined = 0.0
        self.issues: list[Issue] = []

    def block(self, qb: dict) -> PlanNode:
        node = PlanNode(type=f"SELECT #{qb.get('select_id', '?')}",
                        cost=_f((qb.get("cost_info") or {}).get("query_cost")))
        if qb.get("message"):
            node.extra.append(qb["message"])
        node.children = self.ops(qb)
        for key in ("select_list_subqueries", "optimized_away_subqueries"):
            for sq in qb.get(key) or []:
                if "query_block" in sq:
                    node.children.append(self.block(sq["query_block"]))
        return node

    def ops(self, d: dict) -> list[PlanNode]:
        out: list[PlanNode] = []
        if "table" in d:
            out.append(self.table(d["table"], loops=1.0))
        if "nested_loop" in d:
            loop = PlanNode(type="Nested loop")
            prefix = 1.0
            for item in d["nested_loop"]:
                t = item.get("table", {})
                loop.children.append(self.table(t, loops=prefix))
                produced = _f(t.get("rows_produced_per_join"))
                if produced:
                    prefix = produced
                if t.get("using_join_buffer") and "hash" in str(t.get("using_join_buffer")).lower():
                    loop.type = "Hash join"
            out.append(loop)
        for key, label in _MYSQL_OPS.items():
            if key in d:
                op = d[key]
                node = PlanNode(type=label)
                if op.get("using_filesort"):
                    node.type = "Sort (filesort)" if key == "ordering_operation" else f"{label} + filesort"
                    node.extra.append("Using filesort")
                    self.filesort = True
                if op.get("using_temporary_table"):
                    node.extra.append("Using temporary")
                    self.temporary = True
                node.children = self.ops(op)
                out.append(node)
        if "union_result" in d:
            u = d["union_result"]
            node = PlanNode(type="Union")
            if u.get("using_temporary_table"):
                node.extra.append("Using temporary")
                self.temporary = True
            for spec in u.get("query_specifications") or []:
                if "query_block" in spec:
                    node.children.append(self.block(spec["query_block"]))
            out.append(node)
        return out

    def table(self, t: dict, loops: float) -> PlanNode:
        name = t.get("table_name", "?")
        access = t.get("access_type")
        rows = _f(t.get("rows_examined_per_scan"))
        node = PlanNode(type=_MYSQL_ACCESS.get(access, access or "Table"), table=name, index=t.get("key"),
                        access=access, rows=rows, cost=_f((t.get("cost_info") or {}).get("prefix_cost")),
                        filter=t.get("attached_condition"))
        if t.get("using_index"):
            node.extra.append("Using index (covering)")
        if t.get("using_join_buffer"):
            node.extra.append(f"Join buffer: {t['using_join_buffer']}")
        if t.get("filtered") is not None:
            node.extra.append(f"filtered {t['filtered']}%")
        if rows is not None:
            self.examined += rows * max(loops, 1.0)
        if access in ("ALL",):
            self.full_scans.append(name)
            if rows and rows >= BIG_SCAN_ROWS and not name.startswith("<"):
                sev = "high" if rows >= HUGE_SCAN_ROWS else "medium"
                filt = _f(t.get("filtered"))
                extra = f" После фильтра остаётся ~{filt:g}% строк — низкая селективность полного перебора." if filt is not None and filt < 20 else ""
                self.issues.append(Issue(code="FULL_TABLE_SCAN", severity=sev, source="plan", table=name,
                                         title=f"Полное сканирование {name}",
                                         description=f"Таблица {name} читается целиком (~{rows:,.0f} строк за проход).{extra}".replace(",", " ")))
            if t.get("possible_keys") and not t.get("key"):
                self.issues.append(Issue(code="INDEX_NOT_USED", severity="medium", source="plan", table=name,
                                         title=f"Индекс не выбран для {name}",
                                         description=f"Возможные индексы {', '.join(t['possible_keys'])} есть, но "
                                                     "оптимизатор выбрал полный перебор (низкая селективность или "
                                                     "неподходящее условие)."))
        elif access == "index":
            self.full_scans.append(name)
            if rows and rows >= HUGE_SCAN_ROWS:
                self.issues.append(Issue(code="FULL_INDEX_SCAN", severity="medium", source="plan", table=name,
                                         title=f"Полный проход по индексу {t.get('key')}",
                                         description=f"Читается весь индекс {t.get('key')} таблицы {name} (~{rows:,.0f} записей).".replace(",", " ")))
        elif access:
            self.index_accesses.append(name)
        if loops > 1 and rows and access in ("ALL", "index") and loops * rows >= HUGE_SCAN_ROWS:
            self.issues.append(Issue(code="NESTED_LOOP_SCAN", severity="high", source="plan", table=name,
                                     title=f"Повторное сканирование {name} в цикле",
                                     description=f"Таблица {name} сканируется ~{loops:,.0f} раз по ~{rows:,.0f} строк.".replace(",", " ")))
        for key in ("materialized_from_subquery",):
            if key in t and "query_block" in t[key]:
                node.children.append(self.block(t[key]["query_block"]))
        for sq in t.get("attached_subqueries") or []:
            if "query_block" in sq:
                node.children.append(self.block(sq["query_block"]))
        return node


def analyze_mysql(raw: dict) -> PlanSummary:
    w = _MySQLWalker()
    qb = raw.get("query_block", raw)
    root = w.block(qb)
    s = PlanSummary(dbms="mysql", total_cost=root.cost, root=root, full_scans=w.full_scans,
                    index_accesses=w.index_accesses, uses_filesort=w.filesort, uses_temporary=w.temporary,
                    estimated_rows_examined=w.examined, raw=raw, analyzed="_analyze_text" in raw)
    s.issues = w.issues
    if w.filesort:
        s.issues.append(Issue(code="FILESORT", severity="medium", source="plan", title="Сортировка filesort",
                              description="Результат сортируется отдельной операцией, а не читается в порядке индекса."))
    if w.temporary:
        s.issues.append(Issue(code="TEMPORARY_TABLE", severity="medium", source="plan", title="Временная таблица",
                              description="Для GROUP BY / DISTINCT / UNION создаётся временная таблица."))
    return s


# ====================================================================== PostgreSQL
_PG_SCANS = {"Seq Scan", "Index Scan", "Index Only Scan", "Bitmap Heap Scan", "Parallel Seq Scan", "Tid Scan"}


class _PGWalker:
    def __init__(self, analyzed: bool):
        self.analyzed = analyzed
        self.full_scans: list[str] = []
        self.index_accesses: list[str] = []
        self.filesort = False
        self.temporary = False
        self.examined = 0.0
        self.issues: list[Issue] = []

    def node(self, p: dict) -> PlanNode:
        ntype = p.get("Node Type", "?")
        if p.get("Join Type") and ntype in ("Hash Join", "Nested Loop", "Merge Join"):
            ntype = f"{ntype} ({p['Join Type']})" if p["Join Type"] != "Inner" else ntype
        loops = _f(p.get("Actual Loops")) or 1.0
        actual = _f(p.get("Actual Rows"))
        node = PlanNode(type=ntype, table=p.get("Relation Name"), index=p.get("Index Name"),
                        rows=_f(p.get("Plan Rows")), actual_rows=actual * loops if actual is not None else None,
                        cost=_f(p.get("Total Cost")),
                        time_ms=(_f(p.get("Actual Total Time")) or 0) * loops if p.get("Actual Total Time") is not None else None,
                        filter=p.get("Filter") or p.get("Index Cond") or p.get("Hash Cond") or p.get("Join Filter"))
        if p.get("Sort Key"):
            node.extra.append("Sort key: " + ", ".join(p["Sort Key"]))
        if p.get("Sort Method"):
            node.extra.append(f"Sort method: {p['Sort Method']} ({p.get('Sort Space Type', '')})")
        if p.get("Rows Removed by Filter") is not None:
            node.extra.append(f"Rows removed by filter: {p['Rows Removed by Filter']}")
        if p.get("Hash Batches", 1) and (p.get("Hash Batches") or 1) > 1:
            node.extra.append(f"Hash batches: {p['Hash Batches']}")
            self.temporary = True

        base = p.get("Node Type", "")
        rel = p.get("Relation Name") or p.get("Alias")
        if base in _PG_SCANS:
            if self.analyzed and actual is not None:
                removed = (_f(p.get("Rows Removed by Filter")) or 0) + (_f(p.get("Rows Removed by Index Recheck")) or 0)
                self.examined += (actual + removed) * loops
            else:
                self.examined += node.rows or 0
        if base in ("Seq Scan", "Parallel Seq Scan"):
            self.full_scans.append(rel or "?")
            est = (actual + (_f(p.get("Rows Removed by Filter")) or 0)) if (self.analyzed and actual is not None) else (node.rows or 0)
            if est * loops >= BIG_SCAN_ROWS:
                self.issues.append(Issue(code="FULL_TABLE_SCAN", severity="high" if est * loops >= HUGE_SCAN_ROWS else "medium",
                                         source="plan", table=rel, title=f"Последовательное сканирование {rel}",
                                         description=f"Seq Scan по {rel}: ~{est * loops:,.0f} строк просмотрено."
                                         .replace(",", " ") + (f" Фильтр: {p['Filter']}" if p.get("Filter") else "")))
        elif base in _PG_SCANS or base == "Bitmap Index Scan":
            if rel:
                self.index_accesses.append(rel)
        if base == "Sort":
            self.filesort = True
            if p.get("Sort Space Type") == "Disk":
                self.issues.append(Issue(code="SORT_ON_DISK", severity="high", source="plan", title="Сортировка на диске",
                                         description="Sort не поместился в work_mem и выполняется на диске."))
        if base in ("Materialize", "HashAggregate") and p.get("Disk Usage"):
            self.temporary = True
        if self.analyzed and actual is not None and node.rows:
            ratio = max(actual, 1) / max(node.rows, 1)
            if ratio >= 10 or ratio <= 0.1:
                self.issues.append(Issue(code="ROW_ESTIMATE_MISMATCH", severity="low", source="plan", table=rel,
                                         title=f"Ошибка оценки числа строк ({base})",
                                         description=f"Оценка {node.rows:,.0f}, фактически {actual:,.0f} строк. "
                                                     "Возможно, устарела статистика (ANALYZE).".replace(",", " ")))
        node.children = [self.node(c) for c in p.get("Plans") or []]
        if base == "Nested Loop" and len(node.children) == 2:
            inner = node.children[1]
            if inner.type in ("Seq Scan",) and loops * (node.children[0].actual_rows or node.children[0].rows or 1) > 100:
                self.issues.append(Issue(code="NESTED_LOOP_SCAN", severity="high", source="plan", table=inner.table,
                                         title=f"Seq Scan внутри Nested Loop ({inner.table})",
                                         description="Внутренняя таблица сканируется целиком для каждой строки внешней."))
        return node


def analyze_postgres(raw: Any) -> PlanSummary:
    top = raw[0] if isinstance(raw, list) else raw
    plan = top["Plan"]
    analyzed = "Actual Rows" in plan
    w = _PGWalker(analyzed)
    root = w.node(plan)
    s = PlanSummary(dbms="postgres", total_cost=_f(plan.get("Total Cost")), root=root, full_scans=w.full_scans,
                    index_accesses=w.index_accesses, uses_filesort=w.filesort, uses_temporary=w.temporary,
                    estimated_rows_examined=w.examined, raw=raw, analyzed=analyzed)
    s.issues = w.issues
    return s


def analyze(dbms: str, raw: Any) -> PlanSummary:
    return analyze_mysql(raw) if dbms == "mysql" else analyze_postgres(raw)


def pg_buffers(raw: Any) -> tuple[float | None, float | None]:
    """(disk reads, buffer hits) для корня плана PostgreSQL (значения кумулятивны)."""
    try:
        p = (raw[0] if isinstance(raw, list) else raw)["Plan"]
        return _f(p.get("Shared Read Blocks")), _f(p.get("Shared Hit Blocks"))
    except (KeyError, IndexError, TypeError):
        return None, None


def index_usage_ratio(s: PlanSummary) -> float | None:
    total = len(s.full_scans) + len(s.index_accesses)
    return len(s.index_accesses) / total if total else None


def _accesses(node: PlanNode | None) -> dict[str, str]:
    out: dict[str, str] = {}

    def walk(n: PlanNode):
        if n.table and n.table not in out and not n.table.startswith("<"):
            out[n.table] = n.type + (f" ({n.index})" if n.index else "")
        for c in n.children:
            walk(c)
    if node:
        walk(node)
    return out


def compare_plans(before: PlanSummary | None, after: PlanSummary | None) -> list[str]:
    if before is None or after is None:
        return []
    changes = []
    a, b = _accesses(before.root), _accesses(after.root)
    for table, acc in a.items():
        if table in b and b[table] != acc:
            changes.append(f"{table}: {acc} → {b[table]}")
    if before.total_cost and after.total_cost:
        changes.append(f"Стоимость плана: {before.total_cost:,.1f} → {after.total_cost:,.1f}".replace(",", " "))
    if before.uses_filesort and not after.uses_filesort:
        changes.append("Отдельная сортировка устранена")
    if not before.uses_filesort and after.uses_filesort:
        changes.append("Появилась отдельная сортировка")
    if before.uses_temporary and not after.uses_temporary:
        changes.append("Временная таблица устранена")
    if before.estimated_rows_examined and after.estimated_rows_examined is not None:
        changes.append(f"Строк просматривается (оценка плана): {before.estimated_rows_examined:,.0f} → "
                       f"{after.estimated_rows_examined:,.0f}".replace(",", " "))
    return changes
