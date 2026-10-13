"""Synthetic comparator controls, not LLM benchmark results.

Temporary tables belong to this connection only. No application tables are changed.
Database unavailability is a failure: these controls must actually run in CI.
"""
from collections import Counter

import psycopg
import pymysql
import pytest


@pytest.fixture(params=['mysql', 'postgres'])
def cursor(request):
    if request.param == 'mysql':
        conn = pymysql.connect(host='127.0.0.1', port=3307, user='root',
                               password='rootpass', database='shop', autocommit=True)
    else:
        conn = psycopg.connect(host='127.0.0.1', port=5434, user='postgres',
                              password='rootpass', dbname='shop', autocommit=True)
    try:
        with conn.cursor() as c:
            c.execute('CREATE TEMPORARY TABLE research_control_rows '
                      '(id INTEGER PRIMARY KEY, bucket INTEGER NOT NULL, '
                      'amount DECIMAL(12,2) NOT NULL, phone VARCHAR(32))')
            c.executemany('INSERT INTO research_control_rows VALUES (%s,%s,%s,%s)', [
                (1, 1, '100.00', None), (2, 1, '200.00', 'x'),
                (3, 2, '99.99', 'y'), (4, 2, '200.01', 'x'),
                (5, 3, '0.00', None), (6, 3, '-10.00', 'y'),
            ])
            yield c
    finally:
        conn.close()  # Temporary tables disappear with this connection.


def execute(c, sql):
    c.execute(sql)
    rows = c.fetchall()
    description = tuple(tuple(column) for column in c.description)
    return rows, description


@pytest.mark.parametrize('reference,candidate', [
    ('SELECT id,amount FROM research_control_rows WHERE amount BETWEEN 100.00 AND 200.00 ORDER BY id',
     'SELECT id,amount FROM research_control_rows WHERE amount>=100.00 AND amount<=200.00 ORDER BY id'),
    ("SELECT id,phone FROM research_control_rows WHERE phone<>'x' ORDER BY id",
     "SELECT id,phone FROM research_control_rows WHERE NOT(phone='x') ORDER BY id"),
    ('SELECT bucket,COUNT(id) AS n FROM research_control_rows GROUP BY bucket ORDER BY bucket',
     'SELECT bucket,COUNT(CASE WHEN id IS NOT NULL THEN id END) AS n FROM research_control_rows GROUP BY bucket ORDER BY bucket'),
    ('SELECT bucket,COUNT(CASE WHEN amount>0 THEN 1 END) AS n FROM research_control_rows GROUP BY bucket ORDER BY bucket',
     'SELECT bucket,COUNT(CASE WHEN amount>0 THEN id END) AS n FROM research_control_rows GROUP BY bucket ORDER BY bucket'),
])
def test_positive_values_order_and_interface(cursor, reference, candidate):
    a, da = execute(cursor, reference)
    b, db = execute(cursor, candidate)
    assert a, 'A positive control must exercise a nonempty result'
    assert Counter(a) == Counter(b)
    assert a == b
    assert da == db


@pytest.mark.parametrize('candidate', [
    'SELECT bucket FROM research_control_rows',  # Lost DISTINCT changes multiplicity.
    'SELECT DISTINCT bucket FROM research_control_rows WHERE amount>0',  # Lost zero group.
])
def test_negative_control_detects_changed_bag(cursor, candidate):
    a, _ = execute(cursor, 'SELECT DISTINCT bucket FROM research_control_rows')
    b, _ = execute(cursor, candidate)
    assert Counter(a) != Counter(b)


def test_negative_control_detects_type_change(cursor):
    a, da = execute(cursor, 'SELECT id FROM research_control_rows ORDER BY id')
    b, db = execute(cursor, 'SELECT CAST(id AS DECIMAL(12,2)) AS id FROM research_control_rows ORDER BY id')
    assert a == b  # Numeric values alone would accept this change.
    assert da != db
