"""Schema Analyzer (офлайн): построение SchemaInfo из текста DDL (CREATE TABLE / CREATE INDEX)."""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from app.models import ColumnInfo, Dialect, ForeignKeyInfo, IndexInfo, SchemaInfo, TableInfo
from app.services.sql_parser import sqlglot_dialect


def _names(nodes) -> list[str]:
    out = []
    for n in nodes or []:
        if isinstance(n, exp.Ordered):
            n = n.this
        out.append(n.name if hasattr(n, "name") and n.name else n.sql())
    return out


def _fk(node: exp.ForeignKey, name: str | None) -> ForeignKeyInfo | None:
    ref = node.args.get("reference")
    if ref is None or not isinstance(ref.this, exp.Schema):
        return None
    return ForeignKeyInfo(name=name, columns=_names(node.expressions),
                          ref_table=ref.this.this.name, ref_columns=_names(ref.this.expressions))


def parse_ddl(ddl: str, dialect: Dialect) -> tuple[SchemaInfo, list[str]]:
    """Возвращает схему и список предупреждений (неразобранные фрагменты)."""
    warnings: list[str] = []
    tables: dict[str, TableInfo] = {}
    try:
        statements = sqlglot.parse(ddl, read=sqlglot_dialect(dialect))
    except ParseError as e:
        return SchemaInfo(source="ddl"), [f"DDL не разобран: {e}"]

    for st in statements:
        if not isinstance(st, exp.Create):
            continue
        kind = (st.args.get("kind") or "").upper()
        if kind == "TABLE" and isinstance(st.this, exp.Schema):
            t = TableInfo(name=st.this.this.name)
            for e in st.this.expressions:
                if isinstance(e, exp.ColumnDef):
                    constraints = [c.args.get("kind") for c in e.args.get("constraints") or []]
                    nullable = not any(isinstance(c, (exp.NotNullColumnConstraint, exp.PrimaryKeyColumnConstraint)) for c in constraints)
                    ctype = e.args["kind"].sql(dialect=sqlglot_dialect(dialect)) if e.args.get("kind") else "UNKNOWN"
                    t.columns.append(ColumnInfo(name=e.name, type=ctype, nullable=nullable))
                    if any(isinstance(c, exp.PrimaryKeyColumnConstraint) for c in constraints):
                        t.indexes.append(IndexInfo(name="PRIMARY", columns=[e.name], unique=True, primary=True))
                    elif any(isinstance(c, exp.UniqueColumnConstraint) for c in constraints):
                        t.indexes.append(IndexInfo(name=f"{e.name}_unique", columns=[e.name], unique=True))
                elif isinstance(e, exp.PrimaryKey):
                    t.indexes = [i for i in t.indexes if not i.primary]
                    t.indexes.append(IndexInfo(name="PRIMARY", columns=_names(e.expressions), unique=True, primary=True))
                elif isinstance(e, exp.IndexColumnConstraint):
                    t.indexes.append(IndexInfo(name=e.this.name if e.this else "idx", columns=_names(e.expressions)))
                elif isinstance(e, exp.UniqueColumnConstraint):
                    target = e.this
                    if isinstance(target, exp.Schema):
                        t.indexes.append(IndexInfo(name=target.this.name if target.this else "unique",
                                                   columns=_names(target.expressions), unique=True))
                elif isinstance(e, exp.Constraint):
                    for sub in e.expressions:
                        if isinstance(sub, exp.ForeignKey) and (fk := _fk(sub, e.this.name if e.this else None)):
                            t.foreign_keys.append(fk)
                        elif isinstance(sub, exp.PrimaryKey):
                            t.indexes.append(IndexInfo(name="PRIMARY", columns=_names(sub.expressions), unique=True, primary=True))
                elif isinstance(e, exp.ForeignKey) and (fk := _fk(e, None)):
                    t.foreign_keys.append(fk)
            tables[t.name.lower()] = t
        elif kind == "INDEX":
            idx = st.this
            table = idx.args.get("table")
            params = idx.args.get("params")
            cols = _names(params.args.get("columns")) if params else []
            if table is None or table.name.lower() not in tables:
                warnings.append(f"Индекс {idx.name} относится к неизвестной таблице")
                continue
            tables[table.name.lower()].indexes.append(
                IndexInfo(name=idx.name, columns=cols, unique=bool(st.args.get("unique"))))
    # MySQL/InnoDB создаёт индекс под внешний ключ автоматически, если подходящего нет.
    if dialect == "mysql":
        for t in tables.values():
            for fk in t.foreign_keys:
                if not any([c.lower() for c in i.columns[: len(fk.columns)]] == [c.lower() for c in fk.columns] for i in t.indexes):
                    t.indexes.append(IndexInfo(name=fk.name or f"fk_{'_'.join(fk.columns)}", columns=fk.columns))
    return SchemaInfo(tables=list(tables.values()), source="ddl"), warnings
