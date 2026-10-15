"""Evaluate frozen MySQL candidates with a schema-scoped SELECT-only account."""
import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import uuid

import pymysql
import sqlglot
from sqlglot import exp
from preflight import connect, execute_read

ROOT = Path(__file__).resolve().parent
MODELS = ['qwen2.5-coder:7b', 'phi3.5:3.8b']


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


def describe(path):
    """Record a repository-relative path so run records never embed a host path."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT.parent.parent).as_posix()
    except ValueError:
        return resolved.name


def validate(sql):
    trees = sqlglot.parse(sql, read='mysql')
    if len(trees) != 1 or not isinstance(trees[0], exp.Query):
        raise ValueError('Exactly one SELECT query required')
    tree = trees[0]
    banned = {'Into', 'Insert', 'Update', 'Delete', 'Create', 'Drop', 'Command',
              'Lock', 'Merge', 'Copy', 'Parameter', 'SessionParameter', 'Placeholder',
              'PropertyEQ', 'Assignment', 'Dot'}
    if any(type(n).__name__ in banned for n in tree.walk()):
        raise ValueError('Unsupported operation')
    if any(n.comments for n in tree.walk()):
        raise ValueError('Comments and optimizer hints are unsupported')
    ctes = {n.alias_or_name.lower() for n in tree.find_all(exp.CTE)}
    if any(n.args.get('recursive') for n in tree.find_all(exp.With)):
        raise ValueError('Recursive CTE unsupported')
    for table in tree.find_all(exp.Table):
        if table.db or table.catalog or table.name.lower() not in {'lib_readers', 'lib_books', 'lib_loans'} | ctes:
            raise ValueError('External or unknown table')
    functions = {'Count', 'Sum', 'Min', 'Max', 'Avg', 'Coalesce', 'If', 'Case',
                 'Nullif', 'RowNumber', 'Rank', 'DenseRank', 'Cast', 'Exists', 'And', 'Or'}
    for node in tree.find_all(exp.Func):
        if type(node).__name__ not in functions:
            raise ValueError('Unsupported function: ' + type(node).__name__)
    return tree


@contextmanager
def database(corpus):
    name = 'libeval_' + uuid.uuid4().hex
    user = 'lv_' + uuid.uuid4().hex[:20]
    password = secrets.token_hex(24)
    admin = connect('mysql')
    reader = None
    created = account = False
    try:
        with admin.cursor() as c:
            c.execute('CREATE DATABASE ' + name)
            created = True
            c.execute('USE ' + name)
            for ddl in corpus['schema_ddl']:
                c.execute(ddl)
            c.execute('CREATE USER %s@%s IDENTIFIED BY %s', (user, '%', password))
            account = True
            c.execute('GRANT SELECT ON ' + name + '.* TO %s@%s', (user, '%'))
        reader = pymysql.connect(host=os.getenv('RESEARCH_DB_HOST', '127.0.0.1'),
                                 port=int(os.getenv('RESEARCH_MYSQL_PORT', '3307')),
                                 user=user, password=password, database=name,
                                 autocommit=True, connect_timeout=10, read_timeout=15)
        with reader.cursor() as c:
            c.execute('SET SESSION max_execution_time=5000')
        yield admin, reader, name
    finally:
        if reader:
            reader.close()
        with admin.cursor() as c:
            if account:
                c.execute('DROP USER %s@%s', (user, '%'))
            if created:
                c.execute('DROP DATABASE ' + name)
        admin.close()


def populate(admin, state):
    with admin.cursor() as c:
        for table in ['lib_loans', 'lib_books', 'lib_readers']:
            c.execute('DELETE FROM ' + table)
        for table, rows in state['tables'].items():
            if rows:
                c.executemany('INSERT INTO ' + table + ' VALUES (' + ','.join(['%s'] * len(rows[0])) + ')', rows)


def check(reader, case, sql, expected):
    with reader.cursor() as c:
        original, interface = execute_read(c, 'mysql', case['sql'])
        if original != expected:
            raise RuntimeError('Reference differs from frozen oracle')
        try:
            candidate, candidate_interface = execute_read(c, 'mysql', sql)
            return {'status': 'matched' if original == candidate else 'counterexample',
                    'reference_rows': original, 'candidate_rows': candidate,
                    'reference_interface': interface, 'candidate_interface': candidate_interface,
                    'interface_equal': interface == candidate_interface}
        except pymysql.MySQLError as exc:
            return {'status': 'execution_error', 'error': str(exc)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--collection', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    raw = (ROOT / 'corpus.json').read_bytes()
    corpus = json.loads(raw)
    protocol = json.loads((a.collection / 'protocol.json').read_text('utf-8'))
    assert protocol['corpus_sha256'] == hashlib.sha256(raw).hexdigest()
    a.output.mkdir(parents=True, exist_ok=False)
    results = []
    with database(corpus) as (admin, reader, schema):
        with reader.cursor() as c:
            c.execute('SELECT VERSION()')
            version = c.fetchone()[0]
        for model in MODELS:
            for case in corpus['cases']:
                record = {'model': model, 'case': case['id'], 'checks': []}
                results.append(record)
                source = a.collection / (model.split(':')[0] + '_' + case['id'] + '.json')
                if not source.exists():
                    record['status'] = 'missing_response'
                    continue
                response = json.loads(source.read_text('utf-8'))['response']
                text = response.get('response', '').strip()
                if not response.get('done') or response.get('done_reason') == 'length':
                    record['status'] = 'incomplete_response'
                    continue
                fence = re.fullmatch(r'```(?:sql|mysql)?\s*\n(.*?)\n```', text, flags=re.I | re.S)
                sql = fence.group(1).strip() if fence else text
                record.update(candidate_sql=sql, markdown_removed=bool(fence))
                try:
                    tree = validate(sql)
                except Exception as exc:
                    record.update(status='unsupported_or_unparsed', reason=str(exc))
                    continue
                record['unchanged'] = tree.sql(dialect='mysql') == sqlglot.parse_one(case['sql'], read='mysql').sql(dialect='mysql')
                for state in corpus['states']:
                    populate(admin, state)
                    result = check(reader, case, sql, corpus['expected_values'][case['id']][state['id']])
                    record['checks'].append(dict(state=state['id'], **result))
                statuses = {r['status'] for r in record['checks']}
                record['status'] = 'counterexample' if 'counterexample' in statuses else 'execution_error' if 'execution_error' in statuses else 'not_refuted'
                witness = next((s for s in record['checks'] if s['status'] == 'counterexample'), None)
                if witness:
                    state = next(s for s in corpus['states'] if s['id'] == witness['state'])
                    with database(corpus) as (wa, wr, ws):
                        populate(wa, state)
                        replay = check(wr, case, sql, corpus['expected_values'][case['id']][state['id']])
                        if replay['status'] != 'counterexample':
                            raise RuntimeError('Counterexample failed independent-schema replay')
                        record['witness'] = {'state': state, 'replay': replay, 'schema': ws}
                save(a.output / 'results.json', results)
                print(model, case['id'], record['status'], flush=True)
    save(a.output / 'results.json', results)
    save(a.output / 'summary.json', {'utc': datetime.now(timezone.utc).isoformat(),
         'corpus_sha256': protocol['corpus_sha256'], 'mysql_version': version,
         'counts': {m: dict(Counter(r['status'] for r in results if r['model'] == m)) for m in MODELS},
         'checked_pairs': sum(len(r['checks']) for r in results),
         'universal_equivalence_claim': False, 'collection': describe(a.collection)})


if __name__ == '__main__':
    main()
