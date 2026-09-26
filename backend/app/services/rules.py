"""Rule-based анализатор: детерминированные правила, работающие до вызова ИИ.

Каждое правило — функция (ctx) -> list[Issue]. Правила не зависят от LLM, поэтому результат
воспроизводим и служит базовой линией (baseline) в экспериментах.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from sqlglot import exp

from app.models import Dialect, Issue, SchemaInfo, TableInfo
from app.services.sql_parser import (ParsedSQL, func_name, is_correlated, select_tables, split_and, sqlglot_dialect,
                                     unwrap_column)

LARGE_TABLE_ROWS = 100_000
LARGE_OFFSET = 10_000

_NUMERIC_TYPES = ("INT", "DECIMAL", "NUMERIC", "FLOAT", "DOUBLE", "REAL", "BIT", "SERIAL", "MONEY")
_STRING_TYPES = ("CHAR", "TEXT", "ENUM", "SET", "UUID", "CITEXT")
_COMPARISONS = (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)


@dataclass
class RuleContext:
    parsed: ParsedSQL
    schema: SchemaInfo
    dialect: Dialect

    @property
    def ast(self) -> exp.Expression:
        return self.parsed.ast

    def sql(self, node: exp.Expression) -> str:
        return node.sql(dialect=sqlglot_dialect(self.dialect))

    def table_for(self, col: exp.Column) -> TableInfo | None:
        """Определяет таблицу колонки по алиасу, а при отсутствии квалификатора — по схеме."""
        if col.table:
            real = self.parsed.info.table_aliases.get(col.table) or col.table
            return self.schema.table(real)
        # неквалифицированная колонка: сначала таблицы своего SELECT, затем всего запроса
        for names in ([t.name for t in select_tables(col)], self.parsed.info.tables):
            candidates = [self.schema.table(t) for t in names]
            matches = [t for t in candidates if t and t.column(col.name)]
            if len(matches) == 1:
                return matches[0]
            if matches:
                return None
        return None


def _type_class(col_type: str) -> str | None:
    t = col_type.upper()
    if any(k in t for k in _NUMERIC_TYPES):
        return "number"
    if any(k in t for k in _STRING_TYPES):
        return "string"
    if any(k in t for k in ("DATE", "TIME")):
        return "datetime"
    return None


def _is_indexed_prefix(table: TableInfo | None, column: str) -> bool | None:
    if table is None or not table.indexes and not table.columns:
        return None
    return any(i.columns and i.columns[0].lower() == column.lower() for i in table.indexes)


def _in_filter_context(node: exp.Expression) -> bool:
    """Узел находится в WHERE / ON / HAVING."""
    p = node.parent
    while p is not None:
        if isinstance(p, (exp.Where, exp.Having)):
            return True
        if isinstance(p, exp.Join) and node in (p.args.get("on").walk() if p.args.get("on") else []):
            return True
        if isinstance(p, exp.Select):
            return False
        p = p.parent
    return False


# ------------------------------------------------------------------ правила
def rule_select_star(ctx: RuleContext) -> list[Issue]:
    if not ctx.parsed.info.select_star:
        return []
    wide = [t.name for t in (ctx.schema.table(n) for n in ctx.parsed.info.tables) if t and len(t.columns) > 8]
    return [Issue(
        code="SELECT_STAR", severity="medium" if wide else "low", title="Используется SELECT *",
        description="Запрос выбирает все колонки. Это увеличивает объём передаваемых данных, мешает покрывающим "
                    "индексам (index-only scan) и делает запрос хрупким к изменению схемы."
                    + (f" Широкие таблицы: {', '.join(wide)}." if wide else ""),
        suggestion="Перечислите только нужные колонки.")]


def rule_function_on_column(ctx: RuleContext) -> list[Issue]:
    issues = []
    for cmp in ctx.ast.find_all(*_COMPARISONS, exp.Between, exp.In, exp.Like):
        if not _in_filter_context(cmp):
            continue
        for side in (cmp.this, cmp.args.get("expression")):
            if not isinstance(side, exp.Func) or isinstance(side, (exp.AggFunc, exp.Column)):
                continue
            if isinstance(side, (exp.Cast, exp.TsOrDsToDate)) and unwrap_column(side) is None:
                continue
            cols = list(side.find_all(exp.Column))
            if len(cols) != 1 or side.find(exp.Select):
                continue
            col = cols[0]
            table = ctx.table_for(col)
            indexed = _is_indexed_prefix(table, col.name)
            name = func_name(side)
            suggestion = None
            if name in ("YEAR", "EXTRACT(YEAR)", "DATE"):
                suggestion = "Замените на диапазон по самой колонке: col >= начало AND col < конец."
            elif name in ("LOWER", "UPPER"):
                suggestion = ("Используйте регистронезависимую collation (MySQL) либо функциональный индекс "
                              f"по {name}({col.name}).")
            else:
                suggestion = "Перенесите вычисление на сторону константы или создайте функциональный индекс."
            issues.append(Issue(
                code="FUNCTION_ON_COLUMN", severity="high" if indexed else "medium",
                title=f"Функция {name}() над колонкой в условии",
                description=f"Условие «{ctx.sql(cmp)}» применяет функцию к колонке {col.sql()}. "
                            "B-tree индекс по колонке в таком случае не используется для поиска"
                            + (" (а индекс по этой колонке есть)." if indexed else "."),
                fragment=ctx.sql(cmp), suggestion=suggestion, table=table.name if table else None))
    return issues


def rule_leading_wildcard(ctx: RuleContext) -> list[Issue]:
    issues = []
    for like in ctx.ast.find_all(exp.Like, exp.ILike):
        pattern = like.args.get("expression")
        if isinstance(pattern, exp.Literal) and pattern.is_string and pattern.this[:1] in ("%", "_"):
            fts = "FULLTEXT-индекс (MATCH ... AGAINST)" if ctx.dialect == "mysql" else "GIN-индекс pg_trgm"
            issues.append(Issue(
                code="LEADING_WILDCARD", severity="medium", title="LIKE с ведущим шаблоном",
                description=f"«{ctx.sql(like)}» начинается с wildcard — обычный B-tree индекс не может быть "
                            "использован для поиска, СУБД просматривает все строки.",
                fragment=ctx.sql(like), suggestion=f"Для поиска подстроки используйте {fts}."))
    return issues


def rule_or_conditions(ctx: RuleContext) -> list[Issue]:
    issues = []
    for where in ctx.ast.find_all(exp.Where):
        for cond in split_and(where.this):
            node = cond.this if isinstance(cond, exp.Paren) else cond
            if not isinstance(node, exp.Or):
                continue
            cols = {c.sql() for c in node.find_all(exp.Column)}
            if len(cols) > 1:
                issues.append(Issue(
                    code="OR_DIFFERENT_COLUMNS", severity="medium", title="OR по разным колонкам",
                    description=f"Условие «{ctx.sql(node)}» объединяет через OR разные колонки ({', '.join(sorted(cols))}). "
                                "Оптимизатору сложно использовать один индекс; часто это приводит к полному сканированию.",
                    fragment=ctx.sql(node),
                    suggestion="Проверьте план: при необходимости разбейте на UNION ALL с индексом под каждую ветку "
                               "(MySQL может применить index_merge, PostgreSQL — BitmapOr)."))
    return issues


def rule_not_in_subquery(ctx: RuleContext) -> list[Issue]:
    issues = []
    for n in ctx.ast.find_all(exp.Not):
        inner = n.this
        if isinstance(inner, exp.In) and inner.args.get("query") is not None:
            issues.append(Issue(
                code="NOT_IN_SUBQUERY", severity="medium", title="NOT IN с подзапросом",
                description=f"«{ctx.sql(n)}»: если подзапрос вернёт хотя бы один NULL, результат будет пустым. "
                            "Кроме того, NOT IN хуже оптимизируется, чем anti-join.",
                fragment=ctx.sql(n),
                suggestion="Используйте NOT EXISTS (коррелированный anti-join). Замена эквивалентна, только если "
                           "колонка подзапроса NOT NULL — проверьте это."))
    return issues


def rule_correlated_subquery(ctx: RuleContext) -> list[Issue]:
    from sqlglot.optimizer.scope import traverse_scope
    issues = []
    try:
        scopes = traverse_scope(ctx.ast)
    except Exception:
        return []
    for s in scopes:
        if not is_correlated(s):
            continue
        node = s.expression
        in_select_list = False
        p = node.parent
        while p is not None and not isinstance(p, exp.Select):
            p = p.parent
        if p is not None:
            in_select_list = any(node in e.walk() for e in p.expressions)
        exists = isinstance(node.parent, exp.Exists) or (node.parent and isinstance(node.parent.parent, exp.Exists))
        issues.append(Issue(
            code="CORRELATED_SUBQUERY", severity="high" if in_select_list else ("low" if exists else "medium"),
            title="Коррелированный подзапрос" + (" в списке SELECT" if in_select_list else ""),
            description="Подзапрос ссылается на колонки внешнего запроса и логически выполняется для каждой строки. "
                        + ("В списке SELECT это часто означает N отдельных выборок." if in_select_list else
                           "Для EXISTS современные оптимизаторы обычно строят semi-join, но стоит проверить план."
                           if exists else ""),
            fragment=ctx.sql(node)[:300],
            suggestion="Перепишите через JOIN с предварительной агрегацией (GROUP BY) или убедитесь, "
                       "что по колонке корреляции есть индекс."))
    return issues


def rule_type_mismatch(ctx: RuleContext) -> list[Issue]:
    if not ctx.schema.tables:
        return []
    issues = []
    for cmp in ctx.ast.find_all(exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.In):
        left = cmp.this
        rights = cmp.expressions if isinstance(cmp, exp.In) else [cmp.args.get("expression")]
        col = left if isinstance(left, exp.Column) else None
        if col is None:
            continue
        table = ctx.table_for(col)
        cinfo = table.column(col.name) if table else None
        if cinfo is None:
            continue
        ctype = _type_class(cinfo.type)
        for r in rights:
            if isinstance(r, exp.Literal):
                if ctype == "number" and r.is_string and re.fullmatch(r"-?\d+(\.\d+)?", r.this):
                    issues.append(Issue(
                        code="TYPE_MISMATCH", severity="low", title="Сравнение числовой колонки со строкой",
                        description=f"«{ctx.sql(cmp)}»: колонка {col.name} имеет тип {cinfo.type}, а литерал — строка. "
                                    "Выполняется неявное приведение типов.",
                        fragment=ctx.sql(cmp), suggestion="Передавайте числовой литерал без кавычек.", table=table.name))
                elif ctype == "string" and r.is_number:
                    issues.append(Issue(
                        code="TYPE_MISMATCH", severity="high", title="Сравнение строковой колонки с числом",
                        description=f"«{ctx.sql(cmp)}»: колонка {col.name} имеет тип {cinfo.type}. "
                                    "При сравнении с числом каждое значение колонки приводится к числу, "
                                    "поэтому индекс по колонке не используется (и возможны ложные совпадения).",
                        fragment=ctx.sql(cmp), suggestion="Заключите литерал в кавычки.", table=table.name))
            elif isinstance(r, exp.Column) and isinstance(cmp, exp.EQ):
                rtable = ctx.table_for(r)
                rinfo = rtable.column(r.name) if rtable else None
                if rinfo and _type_class(rinfo.type) and ctype and _type_class(rinfo.type) != ctype:
                    issues.append(Issue(
                        code="JOIN_TYPE_MISMATCH", severity="high", title="Соединение колонок разных типов",
                        description=f"«{ctx.sql(cmp)}»: {col.name} ({cinfo.type}) и {r.name} ({rinfo.type}). "
                                    "Неявное приведение мешает использовать индекс при соединении.",
                        fragment=ctx.sql(cmp), suggestion="Приведите колонки к одному типу в схеме."))
    return issues


def rule_null_comparison(ctx: RuleContext) -> list[Issue]:
    issues = []
    for cmp in ctx.ast.find_all(exp.EQ, exp.NEQ):
        if isinstance(cmp.args.get("expression"), exp.Null) or isinstance(cmp.this, exp.Null):
            issues.append(Issue(
                code="NULL_COMPARISON", severity="high", title="Сравнение с NULL через = / <>",
                description=f"«{ctx.sql(cmp)}» всегда даёт UNKNOWN — условие никогда не выполняется.",
                fragment=ctx.sql(cmp), suggestion="Используйте IS NULL / IS NOT NULL."))
    return issues


def rule_order_by_rand(ctx: RuleContext) -> list[Issue]:
    for o in ctx.ast.find_all(exp.Ordered):
        if isinstance(o.this, exp.Rand):
            return [Issue(code="ORDER_BY_RAND", severity="high", title="ORDER BY RAND()",
                          description="Для случайной сортировки СУБД генерирует значение для каждой строки и сортирует "
                                      "всю выборку.",
                          fragment=ctx.sql(o), suggestion="Выбирайте случайные id в приложении или используйте "
                                                         "TABLESAMPLE (PostgreSQL).")]
    return []


def rule_large_offset(ctx: RuleContext) -> list[Issue]:
    off = ctx.parsed.info.offset
    if off and off.isdigit() and int(off) >= LARGE_OFFSET:
        return [Issue(code="LARGE_OFFSET", severity="medium", title=f"Большой OFFSET ({off})",
                      description="СУБД читает и отбрасывает все строки до смещения; время растёт линейно с номером страницы.",
                      suggestion="Используйте keyset-пагинацию: WHERE id > :last_id ORDER BY id LIMIT n.")]
    return []


def rule_cartesian_join(ctx: RuleContext) -> list[Issue]:
    issues = []
    for j in ctx.ast.find_all(exp.Join):
        kind = (j.args.get("kind") or "").upper()
        if kind == "CROSS" or j.args.get("on") or j.args.get("using"):
            continue
        # FROM a, b WHERE a.x = b.y — условие соединения в WHERE; проверяем, связаны ли таблицы вообще
        select = j.find_ancestor(exp.Select)
        where = select.args.get("where") if select else None
        alias = j.this.alias_or_name
        linked = False
        if where:
            for cmp in where.find_all(exp.EQ):
                l, r = cmp.this, cmp.args.get("expression")
                if isinstance(l, exp.Column) and isinstance(r, exp.Column) and alias in (l.table, r.table) and l.table != r.table:
                    linked = True
        if not linked:
            issues.append(Issue(code="CARTESIAN_JOIN", severity="critical", title="Соединение без условия",
                                description=f"Таблица {alias} присоединяется без условия — декартово произведение.",
                                fragment=ctx.sql(j), suggestion="Добавьте условие ON или используйте явный CROSS JOIN, "
                                                                "если произведение действительно нужно."))
        else:
            issues.append(Issue(code="IMPLICIT_JOIN", severity="info", title="Неявное соединение через запятую",
                                description=f"Таблица {alias} соединяется через FROM a, b с условием в WHERE.",
                                suggestion="Используйте явный JOIN ... ON — это читабельнее и защищает от случайного "
                                           "декартова произведения."))
    return issues


def rule_union_distinct(ctx: RuleContext) -> list[Issue]:
    for u in ctx.ast.find_all(exp.Union):
        if u.args.get("distinct", True):
            return [Issue(code="UNION_DISTINCT", severity="low", title="UNION вместо UNION ALL",
                          description="UNION удаляет дубликаты — это требует сортировки или хеширования всего результата.",
                          suggestion="Если дубликаты невозможны или допустимы, используйте UNION ALL.")]
    return []


def rule_having_without_aggregate(ctx: RuleContext) -> list[Issue]:
    issues = []
    for h in ctx.ast.find_all(exp.Having):
        for cond in split_and(h.this):
            if not cond.find(exp.AggFunc):
                issues.append(Issue(code="HAVING_WITHOUT_AGGREGATE", severity="low",
                                    title="Условие без агрегата в HAVING",
                                    description=f"«{ctx.sql(cond)}» не использует агрегатные функции, но фильтрует уже "
                                                "после группировки.",
                                    fragment=ctx.sql(cond), suggestion="Перенесите условие в WHERE."))
    return issues


def rule_missing_where_on_large_table(ctx: RuleContext) -> list[Issue]:
    info = ctx.parsed.info
    if info.query_type != "SELECT" or info.where_conditions or info.limit or info.aggregations or info.joins:
        return []
    big = [t for t in (ctx.schema.table(n) for n in info.tables) if t and (t.row_count or 0) >= LARGE_TABLE_ROWS]
    return [Issue(code="UNBOUNDED_SELECT", severity="medium", title="Выборка без фильтра и LIMIT",
                  description=f"Таблица {t.name} (~{t.row_count:,} строк) читается целиком.".replace(",", " "),
                  table=t.name, suggestion="Добавьте условие WHERE или LIMIT.") for t in big]


def _filter_columns(ctx: RuleContext) -> list[tuple[exp.Column, str]]:
    """Колонки, по которым идёт фильтрация (col = const, col > const, col IN (...), col BETWEEN)."""
    out = []
    for where in ctx.ast.find_all(exp.Where):
        for cond in split_and(where.this):
            node = cond
            if isinstance(node, (exp.EQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Between, exp.In)):
                col = node.this
                other = node.args.get("expression")
                if isinstance(col, exp.Column) and not isinstance(other, exp.Column):
                    out.append((col, "eq" if isinstance(node, (exp.EQ, exp.In)) else "range"))
    return out


def rule_missing_index(ctx: RuleContext) -> list[Issue]:
    """Фильтр или условие соединения по колонке, для которой нет индекса с этой колонкой в начале."""
    if not ctx.schema.tables or not any(t.indexes for t in ctx.schema.tables):
        return []
    issues: list[Issue] = []
    seen: set[tuple[str, str]] = set()

    def check(col: exp.Column, why: str):
        table = ctx.table_for(col)
        if table is None or not table.column(col.name):
            return
        key = (table.name.lower(), col.name.lower())
        if key in seen or _is_indexed_prefix(table, col.name):
            return
        seen.add(key)
        big = (table.row_count or 0) >= LARGE_TABLE_ROWS
        rows = f" (~{table.row_count:,} строк)".replace(",", " ") if table.row_count else ""
        issues.append(Issue(
            code="MISSING_INDEX", severity="high" if big else "medium",
            title=f"Нет индекса по {table.name}.{col.name}",
            description=f"Колонка используется {why}, но ни один индекс таблицы {table.name}{rows} не начинается с неё. "
                        "Вероятно полное сканирование таблицы.",
            table=table.name,
            suggestion=f"CREATE INDEX idx_{table.name}_{col.name} ON {table.name} ({col.name});"))

    for col, kind in _filter_columns(ctx):
        check(col, "в фильтре WHERE" if kind == "eq" else "в диапазонном условии WHERE")
    for j in ctx.ast.find_all(exp.Join):
        on = j.args.get("on")
        if on is None:
            continue
        joined_alias = j.this.alias_or_name
        for cmp in on.find_all(exp.EQ):
            for side in (cmp.this, cmp.args.get("expression")):
                if isinstance(side, exp.Column) and side.table == joined_alias:
                    check(side, "в условии соединения (JOIN)")
    return issues


def rule_order_by_filesort(ctx: RuleContext) -> list[Issue]:
    info = ctx.parsed.info
    if not info.order_by or len(info.tables) != 1 or not ctx.schema.tables:
        return []
    table = ctx.schema.table(info.tables[0])
    if table is None or not table.indexes:
        return []
    ast = ctx.ast
    order = ast.args.get("order")
    if order is None:
        return []
    cols = []
    for o in order.expressions:
        c = o.this
        if not isinstance(c, exp.Column):
            return [Issue(code="ORDER_BY_EXPRESSION", severity="low", title="Сортировка по выражению",
                          description=f"ORDER BY {ctx.sql(o)} — сортировку по выражению нельзя выполнить по индексу.")]
        cols.append(c.name.lower())
    eq_cols = [c.name.lower() for c, kind in _filter_columns(ctx) if kind == "eq"]
    for idx in table.indexes:
        icols = [c.lower() for c in idx.columns]
        rest = icols
        while rest and rest[0] in eq_cols and rest[: len(cols)] != cols:
            rest = rest[1:]
        if rest[: len(cols)] == cols:
            return []
    return [Issue(code="ORDER_BY_NO_INDEX", severity="medium" if info.limit else "low",
                  title="Сортировка без подходящего индекса",
                  description=f"Нет индекса, который отдаёт строки {table.name} в порядке ORDER BY {', '.join(info.order_by)}. "
                              "Ожидается отдельная сортировка (filesort / Sort)."
                              + (" С LIMIT индекс позволил бы прочитать только первые строки." if info.limit else ""),
                  table=table.name,
                  suggestion=f"Составной индекс ({', '.join(eq_cols + cols)}) по фильтру и сортировке.")]


RULES: list[Callable[[RuleContext], list[Issue]]] = [
    rule_cartesian_join,
    rule_null_comparison,
    rule_function_on_column,
    rule_type_mismatch,
    rule_missing_index,
    rule_correlated_subquery,
    rule_not_in_subquery,
    rule_leading_wildcard,
    rule_or_conditions,
    rule_order_by_rand,
    rule_order_by_filesort,
    rule_large_offset,
    rule_missing_where_on_large_table,
    rule_select_star,
    rule_union_distinct,
    rule_having_without_aggregate,
]

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def run_rules(parsed: ParsedSQL, schema: SchemaInfo, dialect: Dialect) -> list[Issue]:
    ctx = RuleContext(parsed=parsed, schema=schema, dialect=dialect)
    issues: list[Issue] = []
    for rule in RULES:
        try:
            issues.extend(rule(ctx))
        except Exception as e:  # одно сломанное правило не должно ронять анализ
            issues.append(Issue(code="RULE_ERROR", severity="info", title=f"Правило {rule.__name__} не выполнено",
                                description=str(e)))
    issues.sort(key=lambda i: _SEVERITY_ORDER[i.severity])
    return issues
