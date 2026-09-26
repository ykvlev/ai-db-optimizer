from app.services import rewriter, rules, safety
from app.services.schema_ddl import parse_ddl
from app.services.sql_parser import parse

DDL = """
CREATE TABLE users (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  phone VARCHAR(32),
  name VARCHAR(100),
  created_at DATETIME NOT NULL,
  UNIQUE KEY uq_email (email)
);
CREATE TABLE orders (
  id BIGINT NOT NULL AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  status VARCHAR(16) NOT NULL,
  total DECIMAL(10,2),
  created_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX idx_orders_created ON orders (created_at);
"""


def schema():
    s, warnings = parse_ddl(DDL, "mysql")
    assert not warnings
    return s


def codes(sql, dialect="mysql", sch=None):
    p = parse(sql, dialect)
    return {i.code for i in rules.run_rules(p, sch if sch is not None else schema(), dialect)}


# ---------------------------------------------------------------- parser
def test_parser_extracts_structure():
    p = parse("""WITH t AS (SELECT user_id, COUNT(*) c FROM orders GROUP BY user_id)
                 SELECT u.name, t.c FROM users u LEFT JOIN t ON t.user_id = u.id
                 WHERE u.created_at > '2026-01-01' AND u.name LIKE 'a%'
                 ORDER BY t.c DESC LIMIT 10 OFFSET 20""", "mysql").info
    assert p.query_type == "SELECT"
    assert p.tables == ["orders", "users"]
    assert p.cte == ["t"]
    assert p.joins[0].kind == "LEFT" and p.joins[0].condition == "t.user_id = u.id"
    assert len(p.where_conditions) == 2
    assert p.limit == "10" and p.offset == "20"
    assert p.order_by == ["t.c DESC"]
    assert p.aggregations == ["COUNT(*)"]


def test_parser_counts_correlated_subqueries():
    p = parse("SELECT u.id, (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id) FROM users u", "mysql").info
    assert p.subqueries == 1 and p.correlated_subqueries == 1


def test_ddl_schema():
    s = schema()
    orders = s.table("orders")
    assert [c.name for c in orders.columns][:2] == ["id", "user_id"]
    names = {i.name: i.columns for i in orders.indexes}
    assert names["PRIMARY"] == ["id"]
    assert names["idx_orders_created"] == ["created_at"]
    assert names["fk_orders_user"] == ["user_id"]  # InnoDB создаёт индекс под FK
    assert s.table("users").column("phone").nullable
    assert not s.table("users").column("email").nullable


# ---------------------------------------------------------------- rules
def test_select_star():
    assert "SELECT_STAR" in codes("SELECT * FROM users")


def test_function_on_indexed_column_is_high():
    p = parse("SELECT id FROM orders WHERE YEAR(created_at) = 2026", "mysql")
    issues = [i for i in rules.run_rules(p, schema(), "mysql") if i.code == "FUNCTION_ON_COLUMN"]
    assert issues and issues[0].severity == "high"


def test_leading_wildcard():
    assert "LEADING_WILDCARD" in codes("SELECT id FROM users WHERE name LIKE '%test%'")
    assert "LEADING_WILDCARD" not in codes("SELECT id FROM users WHERE name LIKE 'test%'")


def test_or_different_columns():
    assert "OR_DIFFERENT_COLUMNS" in codes("SELECT id FROM users WHERE email = 'a' OR phone = 'b'")


def test_not_in():
    assert "NOT_IN_SUBQUERY" in codes("SELECT id FROM users WHERE id NOT IN (SELECT user_id FROM orders)")


def test_correlated_in_select_list():
    c = codes("SELECT u.id, (SELECT MAX(o.total) FROM orders o WHERE o.user_id = u.id) FROM users u")
    assert "CORRELATED_SUBQUERY" in c


def test_uncorrelated_subquery_not_flagged():
    c = codes("SELECT id FROM users WHERE id NOT IN (SELECT user_id FROM orders WHERE status = 'x')")
    assert "CORRELATED_SUBQUERY" not in c
    assert parse("SELECT id FROM users WHERE id IN (SELECT user_id FROM orders WHERE status = 'x')", "mysql").info.correlated_subqueries == 0


def test_type_mismatch_resolves_column_by_scope():
    assert "TYPE_MISMATCH" in codes("SELECT id FROM users WHERE id IN (SELECT user_id FROM orders WHERE id = '777')")


def test_type_mismatch():
    assert "TYPE_MISMATCH" in codes("SELECT id FROM users WHERE phone = 79001234567")
    assert "TYPE_MISMATCH" in codes("SELECT id FROM users WHERE id = '123'")
    assert "TYPE_MISMATCH" not in codes("SELECT id FROM users WHERE id = 123")


def test_missing_index():
    c = codes("SELECT id FROM orders WHERE status = 'paid'")
    assert "MISSING_INDEX" in c
    assert "MISSING_INDEX" not in codes("SELECT id FROM orders WHERE user_id = 5")


def test_missing_index_on_join():
    c = codes("SELECT u.id FROM orders o JOIN users u ON u.phone = o.status")
    assert "MISSING_INDEX" in c


def test_order_by_without_index():
    assert "ORDER_BY_NO_INDEX" in codes("SELECT id FROM orders WHERE status = 'x' ORDER BY total LIMIT 5")
    assert "ORDER_BY_NO_INDEX" not in codes("SELECT id FROM orders ORDER BY created_at LIMIT 5")


def test_null_comparison_and_cartesian():
    assert "NULL_COMPARISON" in codes("SELECT id FROM users WHERE phone = NULL")
    assert "CARTESIAN_JOIN" in codes("SELECT u.id FROM users u, orders o")
    assert "CARTESIAN_JOIN" not in codes("SELECT u.id FROM users u, orders o WHERE o.user_id = u.id")


def test_rules_without_schema_do_not_crash():
    from app.models import SchemaInfo
    c = codes("SELECT * FROM a JOIN b ON a.x = b.y WHERE YEAR(a.d) = 2020 ORDER BY RAND()", sch=SchemaInfo())
    assert {"SELECT_STAR", "FUNCTION_ON_COLUMN", "ORDER_BY_RAND"} <= c
    assert "RULE_ERROR" not in c


def test_postgres_extract():
    c = codes("SELECT id FROM orders WHERE EXTRACT(YEAR FROM created_at) = 2026", "postgres")
    assert "FUNCTION_ON_COLUMN" in c


# ---------------------------------------------------------------- rewriter
def test_rewrite_year():
    sql, notes = rewriter.rewrite(parse("SELECT id FROM orders WHERE YEAR(created_at) = 2026 AND status = 'x'", "mysql"))
    assert notes
    flat = " ".join(sql.split())
    assert "created_at >= '2026-01-01' AND created_at < '2027-01-01'" in flat
    assert "YEAR" not in flat


def test_rewrite_date_and_extract():
    sql, _ = rewriter.rewrite(parse("SELECT id FROM orders WHERE DATE(created_at) = '2026-02-28'", "mysql"))
    assert "'2026-03-01'" in sql
    sql, _ = rewriter.rewrite(parse("SELECT id FROM orders WHERE EXTRACT(YEAR FROM created_at) = 2025", "postgres"))
    assert "'2026-01-01'" in sql


def test_rewrite_nothing():
    assert rewriter.rewrite(parse("SELECT id FROM orders", "mysql")) == (None, [])


# ---------------------------------------------------------------- safety
def test_safety_allows_select_and_cte():
    assert safety.check("SELECT * FROM users WHERE name = '#1 -- x'", "mysql").allowed
    assert safety.check("WITH a AS (SELECT 1 AS x) SELECT x FROM a", "postgres").allowed
    assert safety.check("SELECT 1 UNION ALL SELECT 2", "mysql").allowed


def test_safety_blocks():
    blocked = [
        "DELETE FROM users",
        "UPDATE users SET name = 'x'",
        "DROP TABLE users",
        "TRUNCATE TABLE users",
        "INSERT INTO users (id) VALUES (1)",
        "ALTER TABLE users ADD COLUMN x INT",
        "GRANT ALL ON *.* TO 'x'@'%'",
        "CREATE USER x IDENTIFIED BY 'y'",
        "SELECT 1; DROP TABLE users",
        "SELECT SLEEP(10)",
        "SELECT * FROM users FOR UPDATE",
        "SELECT * INTO OUTFILE '/tmp/x' FROM users",
        "SELECT /*!50000 1; DROP TABLE users */ 1",
        "SELECT 1 /* DROP TABLE users */",
        "SET GLOBAL max_connections = 1",
    ]
    for sql in blocked:
        v = safety.check(sql, "mysql")
        assert not v.allowed, sql


def test_safety_blocks_pg_writable_cte():
    v = safety.check("WITH d AS (DELETE FROM users RETURNING id) SELECT * FROM d", "postgres")
    assert not v.allowed
    assert not safety.check("SELECT pg_sleep(5)", "postgres").allowed
