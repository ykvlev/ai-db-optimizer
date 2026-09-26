"""SQL Parser: разбор запроса в AST (sqlglot) и извлечение структурных признаков."""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError
from sqlglot.optimizer.scope import traverse_scope

from app.models import Dialect, JoinInfo, ParsedQuery

# Узлы, которые sqlglot вставляет сам при нормализации и которые не являются «функциями пользователя».
_IMPLICIT_FUNCS = (exp.Connector, exp.TsOrDsToDate, exp.Paren)


class SQLParseError(Exception):
    pass


@dataclass
class ParsedSQL:
    ast: exp.Expression
    info: ParsedQuery
    dialect: Dialect


def sqlglot_dialect(dialect: Dialect) -> str:
    return "postgres" if dialect == "postgres" else "mysql"


def parse_statements(sql: str, dialect: Dialect) -> list[exp.Expression]:
    try:
        return [s for s in sqlglot.parse(sql, read=sqlglot_dialect(dialect)) if s is not None]
    except ParseError as e:
        raise SQLParseError(str(e)) from e


def statement_type(node: exp.Expression) -> str:
    if isinstance(node, (exp.Select, exp.SetOperation)):
        return "SELECT"
    if isinstance(node, exp.Command):
        return str(node.this).upper()
    return node.key.upper()


def unwrap_column(node: exp.Expression) -> exp.Column | None:
    """Возвращает колонку, если выражение — это колонка, обёрнутая в неявные преобразования."""
    while isinstance(node, (exp.TsOrDsToDate, exp.Cast, exp.Paren)) and not isinstance(node, exp.Column):
        node = node.this
    return node if isinstance(node, exp.Column) else None


def func_name(node: exp.Func) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.this).upper()
    if isinstance(node, exp.TsOrDsToDate):
        return "DATE"
    if isinstance(node, exp.Extract):
        return f"EXTRACT({node.this.name.upper()})"
    return node.sql_name().upper()


def split_and(cond: exp.Expression | None) -> list[exp.Expression]:
    if cond is None:
        return []
    if isinstance(cond, exp.And):
        return split_and(cond.left) + split_and(cond.right)
    if isinstance(cond, exp.Paren) and isinstance(cond.this, exp.And):
        return split_and(cond.this)
    return [cond]


def cte_names(ast: exp.Expression) -> set[str]:
    return {c.alias_or_name.lower() for c in ast.find_all(exp.CTE)}


def real_tables(ast: exp.Expression) -> list[exp.Table]:
    ctes = cte_names(ast)
    return [t for t in ast.find_all(exp.Table) if t.name and t.name.lower() not in ctes]


def root_select(ast: exp.Expression) -> exp.Select | None:
    if isinstance(ast, exp.Select):
        return ast
    if isinstance(ast, exp.SetOperation):
        return root_select(ast.left)
    return None


def is_correlated(scope) -> bool:
    """Подзапрос коррелирован, если ссылается на внешний источник по явному квалификатору.

    sqlglot без схемы считает внешними и неквалифицированные колонки подзапроса — это даёт ложные срабатывания.
    """
    if not (scope.is_subquery or scope.is_derived_table):
        return False
    local = {name.lower() for name in scope.sources}
    return any(c.table and c.table.lower() not in local for c in scope.external_columns)


def select_tables(node: exp.Expression) -> list[exp.Table]:
    """Таблицы из FROM/JOIN ближайшего SELECT, внутри которого находится узел."""
    select = node if isinstance(node, exp.Select) else node.find_ancestor(exp.Select)
    if select is None:
        return []
    out = []
    from_ = select.args.get("from_") or select.args.get("from")
    for src in ([from_.this] if from_ is not None else []) + [j.this for j in select.args.get("joins") or []]:
        if isinstance(src, exp.Table):
            out.append(src)
    return out


def parse(sql: str, dialect: Dialect) -> ParsedSQL:
    statements = parse_statements(sql, dialect)
    if not statements:
        raise SQLParseError("Пустой запрос")
    ast = statements[0]
    d = sqlglot_dialect(dialect)
    info = ParsedQuery(query_type=statement_type(ast), node_count=sum(1 for _ in ast.walk()))
    info.normalized_sql = ast.sql(dialect=d, pretty=True)

    tables = real_tables(ast)
    info.tables = sorted({t.name for t in tables})
    info.table_aliases = {(t.alias or t.name): t.name for t in tables}
    info.cte = [c.alias_or_name for c in ast.find_all(exp.CTE)]
    info.union = any(isinstance(n, exp.Union) for n in ast.walk())

    cols: list[str] = []
    for c in ast.find_all(exp.Column):
        s = c.sql(dialect=d)
        if s not in cols:
            cols.append(s)
    info.columns = cols
    info.select_star = any(isinstance(n, exp.Star) and isinstance(n.parent, (exp.Select, exp.Column)) for n in ast.walk())

    for j in ast.find_all(exp.Join):
        kind = (j.args.get("side") or j.args.get("kind") or "INNER").upper()
        on = j.args.get("on")
        using = j.args.get("using")
        cond = on.sql(dialect=d) if on else (f"USING ({', '.join(u.sql(dialect=d) for u in using)})" if using else None)
        target = j.this
        info.joins.append(JoinInfo(kind=kind, table=target.sql(dialect=d) if not isinstance(target, exp.Table) else target.name,
                                   alias=target.alias or None, condition=cond))

    root = root_select(ast)
    if root is not None:
        where = root.args.get("where")
        info.where_conditions = [c.sql(dialect=d) for c in split_and(where.this if where else None)]
        group = root.args.get("group")
        info.group_by = [g.sql(dialect=d) for g in group.expressions] if group else []
        having = root.args.get("having")
        info.having = having.this.sql(dialect=d) if having else None
        info.distinct = bool(root.args.get("distinct"))
    order = ast.args.get("order") or (root.args.get("order") if root is not None else None)
    info.order_by = [o.sql(dialect=d) for o in order.expressions] if order else []
    limit = ast.args.get("limit") or (root.args.get("limit") if root is not None else None)
    info.limit = limit.expression.sql(dialect=d) if limit is not None and limit.expression is not None else None
    offset = ast.args.get("offset") or (root.args.get("offset") if root is not None else None)
    info.offset = offset.expression.sql(dialect=d) if offset is not None and offset.expression is not None else None

    info.aggregations = [a.sql(dialect=d) for a in ast.find_all(exp.AggFunc)]
    funcs: list[str] = []
    for f in ast.find_all(exp.Func):
        if isinstance(f, (exp.AggFunc, *_IMPLICIT_FUNCS)) or isinstance(f, exp.Predicate):
            continue
        name = func_name(f)
        if name not in funcs:
            funcs.append(name)
    info.functions = funcs

    try:
        scopes = traverse_scope(ast)
        info.subqueries = sum(1 for s in scopes if s.is_subquery or s.is_derived_table)
        info.correlated_subqueries = sum(1 for s in scopes if is_correlated(s))
    except Exception:  # scope-анализ не поддерживает некоторые конструкции — не критично
        info.subqueries = max(0, sum(1 for _ in ast.find_all(exp.Select)) - 1 - len(info.cte))
    return ParsedSQL(ast=ast, info=info, dialect=dialect)
