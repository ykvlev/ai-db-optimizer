"""Benchmark Engine и проверка эквивалентности результатов.

Эквивалентность проверяется эмпирически — на текущих данных БД: сравниваются мультимножества строк
(порядконезависимая контрольная сумма), количество колонок и, если в исходном запросе есть ORDER BY, порядок.
Это не формальное доказательство эквивалентности, а проверка «не изменился ли результат на этих данных».
"""

from __future__ import annotations

import datetime as dt
import hashlib
import statistics
import uuid
from collections import Counter
from decimal import Decimal
from typing import Any

from app.models import BenchmarkStats, EquivalenceResult
from app.services.connectors import Connector

SAMPLE_LIMIT_ROWS = 200_000  # до этого объёма храним хэши строк для показа различий
MAX_SAMPLES = 5
_MOD = 1 << 128


def canonical(v: Any) -> str:
    if v is None:
        return "\x00NULL"
    if isinstance(v, bool):
        return str(int(v))
    if isinstance(v, (int, Decimal)):
        d = Decimal(v).normalize() if not isinstance(v, int) else Decimal(v)
        return format(d, "f")
    if isinstance(v, float):
        return format(Decimal(repr(round(v, 9))).normalize(), "f")
    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return v.isoformat()
    if isinstance(v, dt.timedelta):
        return f"{v.total_seconds():.6f}s"
    if isinstance(v, (bytes, bytearray, memoryview)):
        return bytes(v).hex()
    if isinstance(v, uuid.UUID):
        return str(v)
    return str(v)


def _display(v: Any) -> Any:
    if v is None or isinstance(v, (int, float, str, bool)):
        return v
    return canonical(v)


class _ResultHasher:
    def __init__(self):
        self.count = 0
        self.multiset = 0
        self.ordered = hashlib.sha256()
        self.rows: Counter[bytes] | None = Counter()
        self.examples: dict[bytes, tuple] = {}

    def __call__(self, row: tuple):
        digest = hashlib.sha256("\x1f".join(canonical(v) for v in row).encode("utf-8")).digest()
        self.count += 1
        self.multiset = (self.multiset + int.from_bytes(digest[:16], "big")) % _MOD
        self.ordered.update(digest)
        if self.rows is not None:
            if self.count > SAMPLE_LIMIT_ROWS:
                self.rows = None
                self.examples.clear()
            else:
                self.rows[digest] += 1
                if digest not in self.examples and len(self.examples) < SAMPLE_LIMIT_ROWS:
                    self.examples[digest] = row

    @property
    def checksum(self) -> str:
        return f"{self.count}:{self.multiset:032x}"


def check_equivalence(conn: Connector, original: str, optimized: str, order_sensitive: bool) -> EquivalenceResult:
    h1, h2 = _ResultHasher(), _ResultHasher()
    r1 = conn.run(original, row_consumer=h1)
    r2 = conn.run(optimized, row_consumer=h2)
    res = EquivalenceResult(status="equivalent", rows_original=h1.count, rows_optimized=h2.count,
                            columns_match=len(r1.columns) == len(r2.columns),
                            checksum_original=h1.checksum, checksum_optimized=h2.checksum,
                            order_sensitive=order_sensitive)
    if not res.columns_match:
        res.status = "different"
        res.details.append(f"Число колонок отличается: {len(r1.columns)} → {len(r2.columns)}")
    elif [c.lower() for c in r1.columns] != [c.lower() for c in r2.columns]:
        res.details.append(f"Имена колонок отличаются: {r1.columns} → {r2.columns} (на значения не влияет)")
    if h1.checksum != h2.checksum:
        res.status = "different"
        res.details.append(f"Строк: {h1.count} → {h2.count}; контрольные суммы наборов строк не совпадают")
        if h1.rows is not None and h2.rows is not None:
            only1 = list((h1.rows - h2.rows).elements())[:MAX_SAMPLES]
            only2 = list((h2.rows - h1.rows).elements())[:MAX_SAMPLES]
            res.sample_only_in_original = [[_display(v) for v in h1.examples[d]] for d in only1]
            res.sample_only_in_optimized = [[_display(v) for v in h2.examples[d]] for d in only2]
    elif order_sensitive:
        res.order_match = h1.ordered.digest() == h2.ordered.digest()
        if not res.order_match:
            res.details.append("Набор строк совпадает, но порядок отличается. Если ключ ORDER BY не уникален, это "
                               "допустимо; иначе — результат изменён.")
    if res.status == "equivalent" and h1.count == 0:
        res.details.append("Оба запроса вернули 0 строк — проверка эквивалентности на этих данных неинформативна")
    return res


def _stats(times: list[float], warmup: int, rows: int, examined: list[float]) -> BenchmarkStats:
    return BenchmarkStats(
        runs=len(times), warmup=warmup, times_ms=[round(t, 3) for t in times],
        mean_ms=statistics.fmean(times), median_ms=statistics.median(times), min_ms=min(times), max_ms=max(times),
        stdev_ms=statistics.stdev(times) if len(times) > 1 else 0.0, rows_returned=rows,
        rows_examined=statistics.median(examined) if examined else None)


def benchmark(conn: Connector, sql: str, runs: int, warmup: int) -> BenchmarkStats:
    for _ in range(warmup):
        conn.run(sql)
    times, examined, rows = [], [], 0
    for _ in range(runs):
        r = conn.run(sql, measure_rows_examined=conn.dialect == "mysql")
        times.append(r.elapsed_ms)
        rows = r.rows_returned
        if r.rows_examined is not None:
            examined.append(r.rows_examined)
    return _stats(times, warmup, rows, examined)


def benchmark_pair(conn: Connector, a: str, b: str, runs: int, warmup: int) -> tuple[BenchmarkStats, BenchmarkStats]:
    """Чередует запуски A и B, чтобы фоновые колебания нагрузки влияли на оба запроса одинаково."""
    for _ in range(warmup):
        conn.run(a)
        conn.run(b)
    ta, tb, ea, eb = [], [], [], []
    rows_a = rows_b = 0
    mysql = conn.dialect == "mysql"
    for _ in range(runs):
        ra = conn.run(a, measure_rows_examined=mysql)
        rb = conn.run(b, measure_rows_examined=mysql)
        ta.append(ra.elapsed_ms)
        tb.append(rb.elapsed_ms)
        rows_a, rows_b = ra.rows_returned, rb.rows_returned
        if ra.rows_examined is not None:
            ea.append(ra.rows_examined)
        if rb.rows_examined is not None:
            eb.append(rb.rows_examined)
    return _stats(ta, warmup, rows_a, ea), _stats(tb, warmup, rows_b, eb)
