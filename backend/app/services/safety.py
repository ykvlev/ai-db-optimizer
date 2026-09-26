"""SQL Safety Engine: пропускает к выполнению только одиночные read-only SELECT.

Это первая линия защиты. Вторая — выполнение в READ ONLY транзакции с таймаутом,
третья — отдельный пользователь БД только с правом SELECT (см. docker/*/init).
"""

from __future__ import annotations

import re

from sqlglot import exp

from app.models import Dialect, SafetyVerdict
from app.services.sql_parser import SQLParseError, func_name, parse_statements, statement_type

_WRITE_NODES: tuple[type[exp.Expression], ...] = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.TruncateTable,
    exp.Merge, exp.Command, exp.Grant, exp.Set, exp.Use, exp.Transaction, exp.Commit, exp.Rollback,
)
for _name in ("Revoke", "Copy", "LoadData", "Pragma", "Analyze", "Kill", "Refresh", "Cache", "Uncache"):
    if hasattr(exp, _name):
        _WRITE_NODES += (getattr(exp, _name),)

BLOCKED_FUNCTIONS = {
    # задержки / DoS
    "SLEEP", "BENCHMARK", "PG_SLEEP", "PG_SLEEP_FOR", "PG_SLEEP_UNTIL",
    # чтение файлов и сети
    "LOAD_FILE", "PG_READ_FILE", "PG_READ_BINARY_FILE", "PG_LS_DIR", "PG_STAT_FILE", "LO_IMPORT", "LO_EXPORT",
    "DBLINK", "DBLINK_EXEC",
    # управление сервером и сессией
    "PG_TERMINATE_BACKEND", "PG_CANCEL_BACKEND", "PG_RELOAD_CONF", "SET_CONFIG", "PG_ADVISORY_LOCK",
    "GET_LOCK", "RELEASE_LOCK", "RELEASE_ALL_LOCKS",
    # функции с побочными эффектами
    "NEXTVAL", "SETVAL", "TXID_CURRENT", "PG_NOTIFY",
}
BLOCKED_TABLES = {"mysql.user", "mysql.global_priv", "pg_authid", "pg_shadow", "pg_catalog.pg_authid",
                  "pg_catalog.pg_shadow", "pg_user_mapping"}

_STRING_LITERAL = re.compile(r"'(?:[^'\\]|\\.|'')*'|\"(?:[^\"\\]|\\.)*\"", re.DOTALL)
_SQL_KEYWORDS = re.compile(r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|GRANT|TRUNCATE|UNION|SELECT|CREATE|EXEC)\b", re.IGNORECASE)


def _comments(sql: str, dialect: Dialect) -> list[str]:
    """Тела комментариев вне строковых литералов."""
    text = _STRING_LITERAL.sub("''", sql)
    pattern = r"/\*.*?(?:\*/|$)|--[^\n]*" + (r"|#[^\n]*" if dialect == "mysql" else "")
    return re.findall(pattern, text, re.DOTALL)


def check(sql: str, dialect: Dialect) -> SafetyVerdict:
    reasons: list[str] = []
    warnings: list[str] = []
    text = sql.strip()
    if not text:
        return SafetyVerdict(allowed=False, reasons=["Пустой запрос"])

    comments = _comments(text, dialect)
    if any(c.startswith("/*!") for c in comments):
        reasons.append("MySQL executable comment /*! ... */ запрещён: его содержимое выполняется сервером")
    if any(_SQL_KEYWORDS.search(c) for c in comments):
        reasons.append("Комментарий содержит SQL-ключевые слова — возможна попытка скрыть команду")
    elif comments:
        warnings.append("Запрос содержит комментарии")

    try:
        statements = parse_statements(text, dialect)
    except SQLParseError as e:
        return SafetyVerdict(allowed=False, reasons=reasons + [f"Запрос не удалось разобрать: {e}"], warnings=warnings)

    if len(statements) != 1:
        reasons.append(f"Разрешён ровно один SQL-оператор, получено: {len(statements)}")
    if not statements:
        return SafetyVerdict(allowed=False, reasons=reasons, warnings=warnings)

    st = statements[0]
    st_type = statement_type(st)
    if not isinstance(st, (exp.Select, exp.SetOperation)):
        reasons.append(f"Разрешены только SELECT / WITH ... SELECT, получено: {st_type}")

    for s in statements:
        for node in s.walk():
            if isinstance(node, _WRITE_NODES) and node is not s:
                reasons.append(f"Вложенная модифицирующая конструкция: {node.key.upper()}")
            elif isinstance(node, exp.Into):
                reasons.append("SELECT ... INTO запрещён (запись в файл, переменную или новую таблицу)")
            elif isinstance(node, exp.Lock):
                reasons.append("Блокирующие чтения (FOR UPDATE / FOR SHARE) запрещены")
            elif isinstance(node, exp.Func) and func_name(node) in BLOCKED_FUNCTIONS:
                reasons.append(f"Запрещённая функция: {func_name(node)}")
            elif isinstance(node, exp.Table):
                full = ".".join(p for p in (node.db, node.name) if p).lower()
                if full in BLOCKED_TABLES or node.name.lower() in BLOCKED_TABLES:
                    reasons.append(f"Доступ к системной таблице {full} запрещён")

    return SafetyVerdict(allowed=not reasons, statement_type=st_type, reasons=list(dict.fromkeys(reasons)),
                         warnings=warnings)
