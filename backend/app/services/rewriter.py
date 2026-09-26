"""Детерминированный rule-based rewriter: безопасные преобразования, сохраняющие результат.

Используется как базовая линия (baseline) для сравнения с AI-оптимизацией.
"""

from __future__ import annotations

import datetime as dt

from sqlglot import exp

from app.services.sql_parser import ParsedSQL, func_name, sqlglot_dialect, unwrap_column


def _year_arg(node: exp.Expression) -> exp.Column | None:
    if isinstance(node, exp.Year):
        return unwrap_column(node.this)
    if isinstance(node, exp.Extract) and node.this.name.upper() == "YEAR":
        return unwrap_column(node.expression)
    return None


def _date_arg(node: exp.Expression) -> exp.Column | None:
    if isinstance(node, (exp.TsOrDsToDate, exp.Date)) or (isinstance(node, exp.Func) and func_name(node) == "DATE"):
        return unwrap_column(node.this)
    if isinstance(node, exp.Cast) and node.to.this == exp.DataType.Type.DATE:
        return unwrap_column(node.this)
    return None


def _int(lit: exp.Expression) -> int | None:
    if isinstance(lit, exp.Literal) and lit.this.strip("'").isdigit():
        return int(lit.this)
    return None


def _date(lit: exp.Expression) -> dt.date | None:
    if isinstance(lit, exp.Literal) and lit.is_string:
        try:
            return dt.date.fromisoformat(lit.this)
        except ValueError:
            return None
    return None


def _range(col: exp.Column, lo: str, hi: str) -> exp.Expression:
    return exp.Paren(this=exp.and_(
        exp.GTE(this=col.copy(), expression=exp.Literal.string(lo)),
        exp.LT(this=col.copy(), expression=exp.Literal.string(hi))))


def rewrite(parsed: ParsedSQL) -> tuple[str | None, list[str]]:
    """Возвращает (переписанный SQL или None, список применённых преобразований)."""
    notes: list[str] = []
    d = sqlglot_dialect(parsed.dialect)

    def transform(node: exp.Expression) -> exp.Expression:
        if isinstance(node, exp.EQ):
            left, right = node.this, node.args.get("expression")
            col, year = _year_arg(left), _int(right)
            if col is not None and year is not None:
                notes.append(f"{left.sql(dialect=d)} = {year} → диапазон по {col.sql(dialect=d)} (sargable)")
                return _range(col, f"{year}-01-01", f"{year + 1}-01-01")
            col, day = _date_arg(left), _date(right)
            if col is not None and day is not None:
                notes.append(f"DATE({col.sql(dialect=d)}) = '{day}' → диапазон [{day}, {day + dt.timedelta(days=1)})")
                return _range(col, day.isoformat(), (day + dt.timedelta(days=1)).isoformat())
        if isinstance(node, exp.Between):
            col = _year_arg(node.this)
            lo, hi = _int(node.args.get("low")), _int(node.args.get("high"))
            if col is not None and lo is not None and hi is not None and lo <= hi:
                notes.append(f"YEAR({col.sql(dialect=d)}) BETWEEN {lo} AND {hi} → диапазон")
                return _range(col, f"{lo}-01-01", f"{hi + 1}-01-01")
        return node

    new_ast = parsed.ast.copy().transform(transform)
    if not notes:
        return None, []
    return new_ast.sql(dialect=d, pretty=True), notes
