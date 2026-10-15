"""Execute frozen-intent references on native databases, before any model output.

Uses a fresh private schema and drops only that schema on completion. Never
modifies application tables. Failure is fatal; no skipped-database success.
"""
import argparse
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def connect(db):
    if db=='mysql':
        import pymysql
        return pymysql.connect(host=os.getenv('RESEARCH_DB_HOST','127.0.0.1'),port=int(os.getenv('RESEARCH_MYSQL_PORT','3307')),user=os.getenv('RESEARCH_MYSQL_USER','root'),password=os.getenv('RESEARCH_DB_PASSWORD','rootpass'),autocommit=True,connect_timeout=10)
    import psycopg
    return psycopg.connect(host=os.getenv('RESEARCH_DB_HOST','127.0.0.1'),port=int(os.getenv('RESEARCH_PG_PORT','5434')),user=os.getenv('RESEARCH_PG_USER','postgres'),password=os.getenv('RESEARCH_DB_PASSWORD','rootpass'),dbname=os.getenv('RESEARCH_PG_DATABASE','shop'),autocommit=True,connect_timeout=10)

def execute_read(c,db,sql):
    c.execute('START TRANSACTION READ ONLY' if db=='mysql' else 'BEGIN READ ONLY')
    try:
        c.execute(sql)
        values=[list(r) for r in c.fetchall()]
        interface=[list(x) for x in c.description]
        return values,interface
    finally:c.execute('ROLLBACK')

def run(db,data):
    schema='libpre_'+uuid.uuid4().hex
    conn=connect(db);created=False;checks=[]
    try:
        with conn.cursor() as c:
            c.execute('SELECT VERSION()');version=c.fetchone()[0]
            if db=='mysql':
                c.execute(f'CREATE DATABASE {schema}');created=True;c.execute(f'USE {schema}')
                c.execute('SET SESSION max_execution_time=5000')
            else:
                c.execute(f'CREATE SCHEMA {schema}');created=True;c.execute(f'SET search_path TO {schema}')
                c.execute('SET statement_timeout=5000')
            for ddl in data['schema_ddl']:c.execute(ddl)
            for state in data['states']:
                for table in ['lib_loans','lib_books','lib_readers']:c.execute('DELETE FROM '+table)
                for table,rows in state['tables'].items():
                    if rows:c.executemany('INSERT INTO '+table+' VALUES ('+','.join(['%s']*len(rows[0]))+')',rows)
                interfaces={}
                for case in data['cases']:
                    rows,desc=execute_read(c,db,case['sql'])
                    expected=data['expected_values'][case['id']][state['id']]
                    if rows!=expected:raise ValueError(f"{db}/{state['id']}/{case['id']}: reference differs from independent intent oracle: {rows!r} != {expected!r}")
                    interfaces[case['id']]=desc
                    checks.append({'state':state['id'],'case':case['id'],'kind':'reference','rows':rows,'interface':desc})
                for control in data['positive_controls']:
                    rows,desc=execute_read(c,db,control['sql'])
                    if rows!=data['expected_values'][control['case']][state['id']]:raise ValueError('Positive control values differ')
                    if desc!=interfaces[control['case']]:raise ValueError(f"{db}/{state['id']}/{control['case']}: positive control interface differs")
                    checks.append({'state':state['id'],'case':control['case'],'kind':'positive_control','rows':rows,'interface':desc})
            return {'dbms':db,'version':version,'schema':schema,'checks':checks,'native_constraints_enforced':True}
    finally:
        if created:
            with conn.cursor() as c:
                if db=='mysql':c.execute(f'DROP DATABASE {schema}')
                else:
                    c.execute('SET search_path TO public')
                    c.execute(f'DROP SCHEMA {schema} CASCADE')
        conn.close()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    corpus=ROOT/'corpus.json';data=json.loads(corpus.read_text('utf-8'))
    if data['candidate_outputs_seen']:raise ValueError('Preflight must precede candidates')
    result={'corpus_sha256':hashlib.sha256(corpus.read_bytes()).hexdigest(),'utc':datetime.now(timezone.utc).isoformat(),'candidate_generations':0,'status':'running','databases':[]}
    args.output.mkdir(parents=True,exist_ok=True)
    dest=args.output/'preflight.json'
    try:
        for db in ['mysql','postgres']:
            result['databases'].append(run(db,data));print(db,'completed',flush=True)
        result['status']='passed'
    except Exception as exc:
        result['status']='failed';result['error']=str(exc);raise
    finally:dest.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')

if __name__=='__main__':main()
