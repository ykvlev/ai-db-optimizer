"""Коннекторы к анализируемым СУБД. Всё выполнение — только в READ ONLY транзакции с таймаутом.

Добавление новой СУБД = новый подкласс Connector (MariaDB, SQLite, MS SQL, Oracle — см. ТЗ, п. 4).
"""

from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Any, Iterator

from app.config import get_settings
from app.models import ColumnInfo, Dialect, ForeignKeyInfo, IndexInfo, SchemaInfo, TableInfo


class DBError(Exception):
    """Ошибка СУБД с кодом (MySQL errno / PostgreSQL SQLSTATE) для классификации ошибок ИИ."""

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


@dataclass
class ConnectionConfig:
    dbms: Dialect
    host: str
    port: int
    database: str
    username: str
    password: str
    ssl: bool = False


@dataclass
class ExecResult:
    columns: list[str]
    elapsed_ms: float
    rows_returned: int
    rows_examined: float | None = None


class Connector(ABC):
    dialect: Dialect

    def __init__(self, cfg: ConnectionConfig, timeout_ms: int = 30000):
        self.cfg = cfg
        self.timeout_ms = timeout_ms
        self._conn = None

    # ---------------------------------------------------------- lifecycle
    @abstractmethod
    def _connect(self): ...

    def __enter__(self) -> "Connector":
        try:
            self._conn = self._connect()
        except Exception as e:
            raise self._wrap(e) from e
        return self

    def __exit__(self, *exc):
        try:
            if self._conn is not None:
                self._conn.close()
        finally:
            self._conn = None

    @abstractmethod
    def _wrap(self, e: Exception) -> DBError: ...

    # ---------------------------------------------------------- API
    @abstractmethod
    def server_version(self) -> str: ...

    @abstractmethod
    def privilege_report(self) -> tuple[bool | None, list[str]]:
        """(пользователь только для чтения?, предупреждения)."""

    @abstractmethod
    def introspect(self) -> SchemaInfo: ...

    @abstractmethod
    def explain(self, sql: str, analyze: bool = False) -> Any: ...

    @abstractmethod
    def run(self, sql: str, row_consumer=None, measure_rows_examined: bool = False) -> ExecResult:
        """Выполняет SELECT, передавая каждую строку в row_consumer (потоково)."""

    def ping(self) -> None:
        self.server_version()


# ====================================================================== MySQL
class MySQLConnector(Connector):
    dialect: Dialect = "mysql"
    _HANDLER_KEYS = ("Handler_read_first", "Handler_read_key", "Handler_read_last", "Handler_read_next",
                     "Handler_read_prev", "Handler_read_rnd", "Handler_read_rnd_next")

    def _connect(self):
        import pymysql
        return pymysql.connect(
            host=self.cfg.host, port=self.cfg.port, user=self.cfg.username, password=self.cfg.password,
            database=self.cfg.database, charset="utf8mb4", connect_timeout=10,
            read_timeout=max(10, self.timeout_ms // 1000 + 5), autocommit=False,
            ssl={"check_hostname": False} if self.cfg.ssl else None)

    def _wrap(self, e: Exception) -> DBError:
        code = str(e.args[0]) if getattr(e, "args", None) and isinstance(e.args[0], int) else None
        msg = e.args[1] if code and len(e.args) > 1 else str(e)
        return DBError(f"MySQL: {msg}", code)

    @contextmanager
    def _session(self, streaming: bool = False) -> Iterator[Any]:
        import pymysql.cursors
        cur_cls = pymysql.cursors.SSCursor if streaming else pymysql.cursors.Cursor
        try:
            with self._conn.cursor() as c:
                c.execute(f"SET SESSION max_execution_time = {int(self.timeout_ms)}")
                c.execute("START TRANSACTION READ ONLY")
            cur = self._conn.cursor(cur_cls)
            try:
                yield cur
            finally:
                cur.close()
                self._conn.rollback()
        except DBError:
            raise
        except Exception as e:
            try:
                self._conn.rollback()
            except Exception:
                pass
            raise self._wrap(e) from e

    def _query(self, sql: str, args=None) -> list[tuple]:
        with self._session() as c:
            c.execute(sql, args)
            return list(c.fetchall())

    def server_version(self) -> str:
        return self._query("SELECT VERSION()")[0][0]

    def privilege_report(self) -> tuple[bool | None, list[str]]:
        grants = [g[0] for g in self._query("SHOW GRANTS")]
        write_privs = ("ALL PRIVILEGES", "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "GRANT OPTION",
                       "SUPER", "FILE")
        dangerous = [g for g in grants if any(p in g.upper() for p in write_privs)]
        if dangerous:
            return False, ["Пользователь БД имеет права на изменение данных. Рекомендуется отдельный пользователь "
                           "только с SELECT (все запросы всё равно выполняются в READ ONLY транзакции)."]
        return True, []

    def introspect(self) -> SchemaInfo:
        db = self.cfg.database
        tables: dict[str, TableInfo] = {}
        for name, rows, size in self._query(
                "SELECT TABLE_NAME, TABLE_ROWS, DATA_LENGTH + INDEX_LENGTH FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME", (db,)):
            tables[name] = TableInfo(name=name, row_count=int(rows) if rows is not None else None,
                                     size_bytes=int(size) if size is not None else None)
        for t, col, ctype, nullable in self._query(
                "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = %s ORDER BY TABLE_NAME, ORDINAL_POSITION", (db,)):
            if t in tables:
                tables[t].columns.append(ColumnInfo(name=col, type=ctype.upper(), nullable=nullable == "YES"))
        idx: dict[tuple[str, str], IndexInfo] = {}
        for t, iname, col, non_unique in self._query(
                "SELECT TABLE_NAME, INDEX_NAME, COLUMN_NAME, NON_UNIQUE FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = %s ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX", (db,)):
            if t not in tables:
                continue
            key = (t, iname)
            if key not in idx:
                idx[key] = IndexInfo(name=iname, columns=[], unique=not int(non_unique), primary=iname == "PRIMARY")
                tables[t].indexes.append(idx[key])
            idx[key].columns.append(col or "<expr>")
        fks: dict[tuple[str, str], ForeignKeyInfo] = {}
        for t, cname, col, rt, rc in self._query(
                "SELECT TABLE_NAME, CONSTRAINT_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME "
                "FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA = %s AND REFERENCED_TABLE_NAME IS NOT NULL "
                "ORDER BY TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION", (db,)):
            if t not in tables:
                continue
            key = (t, cname)
            if key not in fks:
                fks[key] = ForeignKeyInfo(name=cname, columns=[], ref_table=rt, ref_columns=[])
                tables[t].foreign_keys.append(fks[key])
            fks[key].columns.append(col)
            fks[key].ref_columns.append(rc)
        return SchemaInfo(tables=list(tables.values()), source="live")

    def explain(self, sql: str, analyze: bool = False) -> Any:
        rows = self._query(f"EXPLAIN FORMAT=JSON {sql}")
        plan = json.loads(rows[0][0])
        if analyze:
            try:
                plan["_analyze_text"] = self._query(f"EXPLAIN ANALYZE {sql}")[0][0]
            except DBError as e:  # EXPLAIN ANALYZE появился в 8.0.18
                plan["_analyze_error"] = str(e)
        return plan

    def _handler_reads(self, cur) -> float:
        cur.execute("SHOW SESSION STATUS LIKE 'Handler_read%%'")
        return float(sum(int(v) for k, v in cur.fetchall() if k in self._HANDLER_KEYS))

    def run(self, sql: str, row_consumer=None, measure_rows_examined: bool = False) -> ExecResult:
        with self._session(streaming=True) as cur:
            before = overhead = None
            if measure_rows_examined:
                # SHOW STATUS сам увеличивает счётчики — калибруем его вклад двумя вызовами подряд
                b0 = self._handler_reads(cur)
                before = self._handler_reads(cur)
                overhead = before - b0
            t0 = time.perf_counter()
            cur.execute(sql)
            columns = [d[0] for d in cur.description or []]
            n = 0
            for row in cur:
                n += 1
                if row_consumer:
                    row_consumer(row)
            elapsed = (time.perf_counter() - t0) * 1000
            examined = self._handler_reads(cur) - before - overhead if before is not None else None
            return ExecResult(columns=columns, elapsed_ms=elapsed, rows_returned=n,
                              rows_examined=max(examined, 0) if examined is not None else None)


# ====================================================================== PostgreSQL
class PostgresConnector(Connector):
    dialect: Dialect = "postgres"

    def _connect(self):
        import psycopg
        conn = psycopg.connect(host=self.cfg.host, port=self.cfg.port, dbname=self.cfg.database,
                               user=self.cfg.username, password=self.cfg.password, connect_timeout=10,
                               sslmode="require" if self.cfg.ssl else "prefer", autocommit=False)
        conn.read_only = True
        return conn

    def _wrap(self, e: Exception) -> DBError:
        code = getattr(getattr(e, "diag", None), "sqlstate", None) or getattr(e, "sqlstate", None)
        msg = str(e).strip()
        if "�" in msg:
            # локализованный сервер (Windows-1251) до согласования кодировки: текст не декодируется,
            # поэтому причину определяем по тому, чьё имя в кавычках осталось читаемым
            quoted = re.findall(r'"([^"]+)"', msg)
            m = re.search(r'server at "([^"]+)", port (\d+)', msg)
            where = f"сервер {m.group(1)}:{m.group(2)}" if m else "сервер"
            if self.cfg.username in quoted:
                return DBError(f"PostgreSQL: {where}: пользователь «{self.cfg.username}» не прошёл проверку пароля. "
                               "Проверьте логин и пароль (сервер не различает эти ошибки).", "28P01")
            if self.cfg.database in quoted:
                return DBError(f"PostgreSQL: {where}: база данных «{self.cfg.database}» не найдена или к ней нет доступа.",
                               "3D000")
            return DBError(f"PostgreSQL: {where}: сервер вернул ошибку в кодировке, которую не удалось прочитать "
                           "(локализованный PostgreSQL на Windows). Проверьте параметры подключения.", code)
        return DBError(f"PostgreSQL: {msg}", code)

    @contextmanager
    def _session(self, name: str | None = None) -> Iterator[Any]:
        try:
            with self._conn.cursor() as c:
                c.execute(f"SET LOCAL statement_timeout = {int(self.timeout_ms)}")
            cur = self._conn.cursor(name=name) if name else self._conn.cursor()
            try:
                yield cur
            finally:
                cur.close()
                self._conn.rollback()
        except DBError:
            raise
        except Exception as e:
            try:
                self._conn.rollback()
            except Exception:
                pass
            raise self._wrap(e) from e

    def _query(self, sql: str, args=None) -> list[tuple]:
        with self._session() as c:
            c.execute(sql, args)
            return list(c.fetchall())

    def server_version(self) -> str:
        return self._query("SHOW server_version")[0][0]

    def privilege_report(self) -> tuple[bool | None, list[str]]:
        (is_super,) = self._query("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")[0]
        (writable,) = self._query(
            "SELECT count(*) FROM information_schema.tables t WHERE t.table_schema NOT IN ('pg_catalog','information_schema') "
            "AND (has_table_privilege(quote_ident(t.table_schema)||'.'||quote_ident(t.table_name), 'INSERT') "
            "OR has_table_privilege(quote_ident(t.table_schema)||'.'||quote_ident(t.table_name), 'UPDATE') "
            "OR has_table_privilege(quote_ident(t.table_schema)||'.'||quote_ident(t.table_name), 'DELETE'))")[0]
        if is_super or writable:
            return False, ["Пользователь БД имеет права на изменение данных"
                           + (" (superuser)" if is_super else "")
                           + ". Рекомендуется отдельная роль только с SELECT (запросы всё равно выполняются в READ ONLY "
                             "транзакции)."]
        return True, []

    # все пользовательские схемы; таблицы схемы по умолчанию называются без префикса, остальные — schema.table
    _USER_SCHEMAS = ("n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname NOT LIKE 'pg_toast%' "
                     "AND n.nspname NOT LIKE 'pg_temp%'")
    _QNAME = "CASE WHEN n.nspname = current_schema() THEN {rel} ELSE n.nspname || '.' || {rel} END"

    def introspect(self) -> SchemaInfo:
        tables: dict[str, TableInfo] = {}
        q = self._QNAME
        for name, rows, size in self._query(
                f"SELECT {q.format(rel='c.relname')}, GREATEST(c.reltuples, 0)::bigint, pg_total_relation_size(c.oid) "
                f"FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                f"WHERE {self._USER_SCHEMAS} AND c.relkind IN ('r','p') ORDER BY 1"):
            tables[name] = TableInfo(name=name, row_count=int(rows), size_bytes=int(size))
        for t, col, ctype, nullable in self._query(
                "SELECT CASE WHEN table_schema = current_schema() THEN table_name ELSE table_schema || '.' || table_name END, "
                "column_name, "
                "CASE WHEN data_type IN ('character varying','character') AND character_maximum_length IS NOT NULL "
                "THEN data_type || '(' || character_maximum_length || ')' "
                "WHEN data_type = 'numeric' AND numeric_precision IS NOT NULL "
                "THEN 'numeric(' || numeric_precision || ',' || numeric_scale || ')' ELSE data_type END, is_nullable "
                "FROM information_schema.columns WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
                "ORDER BY 1, ordinal_position"):
            if t in tables:
                tables[t].columns.append(ColumnInfo(name=col, type=ctype.upper(), nullable=nullable == "YES"))
        for t, iname, uniq, prim, cols in self._query(
                f"SELECT {q.format(rel='t.relname')}, i.relname, ix.indisunique, ix.indisprimary, "
                "ARRAY(SELECT COALESCE(a.attname, '<expr>') FROM unnest(ix.indkey) WITH ORDINALITY k(attnum, ord) "
                "LEFT JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum ORDER BY k.ord) "
                "FROM pg_index ix JOIN pg_class t ON t.oid = ix.indrelid JOIN pg_class i ON i.oid = ix.indexrelid "
                f"JOIN pg_namespace n ON n.oid = t.relnamespace WHERE {self._USER_SCHEMAS} ORDER BY 1, 2"):
            if t in tables:
                tables[t].indexes.append(IndexInfo(name=iname, columns=list(cols), unique=uniq, primary=prim))
        for t, cname, cols, rt, rcols in self._query(
                f"SELECT {q.format(rel='cl.relname')}, con.conname, "
                "ARRAY(SELECT a.attname FROM unnest(con.conkey) WITH ORDINALITY k(n, o) JOIN pg_attribute a "
                "ON a.attrelid = con.conrelid AND a.attnum = k.n ORDER BY k.o), "
                "CASE WHEN rn.nspname = current_schema() THEN rc.relname ELSE rn.nspname || '.' || rc.relname END, "
                "ARRAY(SELECT a.attname FROM unnest(con.confkey) WITH ORDINALITY k(n, o) JOIN pg_attribute a "
                "ON a.attrelid = con.confrelid AND a.attnum = k.n ORDER BY k.o) "
                "FROM pg_constraint con JOIN pg_class cl ON cl.oid = con.conrelid JOIN pg_class rc ON rc.oid = con.confrelid "
                "JOIN pg_namespace n ON n.oid = cl.relnamespace JOIN pg_namespace rn ON rn.oid = rc.relnamespace "
                f"WHERE con.contype = 'f' AND {self._USER_SCHEMAS}"):
            if t in tables:
                tables[t].foreign_keys.append(ForeignKeyInfo(name=cname, columns=list(cols), ref_table=rt,
                                                             ref_columns=list(rcols)))
        return SchemaInfo(tables=list(tables.values()), source="live")

    def explain(self, sql: str, analyze: bool = False) -> Any:
        opts = "ANALYZE, BUFFERS, FORMAT JSON" if analyze else "FORMAT JSON"
        plan = self._query(f"EXPLAIN ({opts}) {sql}")[0][0]
        return json.loads(plan) if isinstance(plan, str) else plan

    def run(self, sql: str, row_consumer=None, measure_rows_examined: bool = False) -> ExecResult:
        with self._session(name="aidbo_cur") as cur:
            cur.itersize = 5000
            t0 = time.perf_counter()
            cur.execute(sql)
            n = 0
            columns: list[str] = []
            for row in cur:
                if not columns:
                    columns = [d.name for d in cur.description or []]
                n += 1
                if row_consumer:
                    row_consumer(row)
            elapsed = (time.perf_counter() - t0) * 1000
            if not columns and cur.description:
                columns = [d.name for d in cur.description]
            return ExecResult(columns=columns, elapsed_ms=elapsed, rows_returned=n)


def make_connector(cfg: ConnectionConfig, timeout_ms: int = 30000) -> Connector:
    # В Docker «localhost» — это сам контейнер: подключения к базам на компьютере пользователя
    # перенаправляются на адрес хоста (LOCALHOST_ALIAS=host.docker.internal).
    alias = get_settings().localhost_alias
    if alias and cfg.host in ("localhost", "127.0.0.1", "::1"):
        cfg = replace(cfg, host=alias)
    if cfg.dbms == "mysql":
        return MySQLConnector(cfg, timeout_ms)
    if cfg.dbms == "postgres":
        return PostgresConnector(cfg, timeout_ms)
    raise ValueError(f"Неподдерживаемая СУБД: {cfg.dbms}")


DEFAULT_PORTS = {"mysql": 3306, "postgres": 5432}
