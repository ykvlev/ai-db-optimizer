"""Консоль, аудит структуры и словарь данных — без подключения к СУБД (схема из DDL, заглушка коннектора)."""

import datetime as dt
import decimal
import io

import pytest

from app.services import workbench
from app.services.connectors import ExecResult
from app.services.schema_ddl import parse_ddl

BAD_DDL = """
CREATE TABLE dept (id INT PRIMARY KEY, name VARCHAR(100));
CREATE TABLE emp (
  id INT,
  dept_id INT,
  hire_date VARCHAR(20),
  salary FLOAT,
  name VARCHAR(100),
  FOREIGN KEY (dept_id) REFERENCES dept(id)
);
CREATE TABLE pays (id INT PRIMARY KEY, emp_id INT, amount DECIMAL(10,2), created_at DATETIME);
CREATE INDEX i_emp ON pays (emp_id);
CREATE INDEX i_emp_date ON pays (emp_id, created_at);
"""


class FakeConn:
    """Коннектор-заглушка: возвращает заранее заданные строки и статистику."""

    def __init__(self, rows=(), unused=None):
        self.rows, self.unused, self.last_sql = list(rows), unused, None

    def run(self, sql, row_consumer=None, measure_rows_examined=False):
        self.last_sql = sql
        for r in self.rows:
            row_consumer(r)
        return ExecResult(columns=["a", "b"], elapsed_ms=1.5, rows_returned=len(self.rows))

    def index_usage(self):
        return self.unused

    def never_analyzed(self):
        return []


def test_console_adds_limit_and_serializes_values():
    conn = FakeConn([(decimal.Decimal("1.50"), dt.date(2025, 3, 15)), (b"\x00\x01", None)])
    r = workbench.run_console(conn, "mysql", "SELECT a, b FROM t;", limit=10)
    assert conn.last_sql.endswith("LIMIT 11")
    assert r["rows"] == [[1.5, "2025-03-15"], ["0x0001", None]]
    assert not r["truncated"]


def test_console_keeps_user_limit_and_truncates():
    conn = FakeConn([(i, i) for i in range(5)])
    r = workbench.run_console(conn, "postgres", "SELECT a, b FROM t LIMIT 100", limit=3)
    assert "LIMIT 100" in conn.last_sql and conn.last_sql.count("LIMIT") == 1
    assert r["truncated"] and len(r["rows"]) == 3


def test_console_blocks_writes():
    with pytest.raises(workbench.WorkbenchError):
        workbench.run_console(FakeConn(), "mysql", "DELETE FROM t")


def test_audit_finds_design_problems():
    schema, _ = parse_ddl(BAD_DDL, "mysql")
    a = workbench.audit(FakeConn(unused=[]), "mysql", schema)
    got = {(f["code"], f["table"]) for f in a["findings"]}
    assert ("NO_PRIMARY_KEY", "emp") in got
    assert ("FK_WITHOUT_INDEX", "emp") not in got  # MySQL сам создаёт индекс под внешний ключ
    assert ("DATE_AS_TEXT", "emp") in got
    assert ("MONEY_AS_FLOAT", "emp") in got
    assert ("REDUNDANT_INDEX", "pays") in got
    assert ("MONEY_AS_FLOAT", "pays") not in got  # DECIMAL — правильно
    fix = next(f["fix_sql"] for f in a["findings"] if f["code"] == "REDUNDANT_INDEX")
    assert fix == "DROP INDEX `i_emp` ON `pays`;"
    assert 0 <= a["score"] < 100


def test_audit_fk_without_index_postgres():
    schema, _ = parse_ddl(BAD_DDL.replace("DATETIME", "TIMESTAMP"), "postgres")
    a = workbench.audit(FakeConn(unused=None), "postgres", schema)
    fix = next(f["fix_sql"] for f in a["findings"] if f["code"] == "FK_WITHOUT_INDEX")
    assert fix == 'CREATE INDEX "idx_emp_dept_id" ON "emp" ("dept_id");'


def test_data_dictionary_docx():
    from docx import Document
    schema, _ = parse_ddl(BAD_DDL, "mysql")
    data = workbench.data_dictionary_docx("hr", "mysql", "8.4", schema,
                                          {"emp": {"description": "Сотрудники", "columns": {"salary": "Оклад"}}})
    doc = Document(io.BytesIO(data))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Таблица 2 – Структура таблицы dept" in text
    cells = [c.text for t in doc.tables for row in t.rows for c in row.cells]
    assert "Оклад" in cells and "FK → dept" in cells
