"""Collect raw model responses after CI and deployment gates; never executes SQL."""
import argparse
import hashlib
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
MODELS=['qwen2.5-coder:7b','phi3.5:3.8b']
OPTIONS={'temperature':0,'num_ctx':4096,'num_predict':1200}

def write(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')

def request(endpoint,body=None,timeout=30):
    payload=None if body is None else json.dumps(body).encode()
    req=urllib.request.Request('http://127.0.0.1:11434/api/'+endpoint,data=payload,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as response:return json.load(response)

def prompt(case,ddl):
    return ('Rewrite the following MySQL 8.4 SELECT query for efficiency. Preserve output column names, '
            'values, duplicates, NULL behavior and the specified row order for EVERY state allowed by '
            'the schema. Do not add indexes or change the schema. Return only one SELECT statement, '
            'without markdown or explanation. If no safe improvement is available, return the original query.\n'
            +'\n'.join(ddl)+'\nQUERY:\n'+case['sql'])

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--preflight',type=Path,required=True)
    p.add_argument('--freeze',type=Path,required=True)
    p.add_argument('--deployment-receipt',type=Path,required=True)
    p.add_argument('--prior-budget-ledger',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    raw=(ROOT/'corpus.json').read_bytes();sha=hashlib.sha256(raw).hexdigest();corpus=json.loads(raw)
    pre=json.loads(a.preflight.read_text('utf-8'));freeze=json.loads(a.freeze.read_text('utf-8-sig'))
    receipt=json.loads(a.deployment_receipt.read_text('utf-8-sig'))
    previous=json.loads(a.prior_budget_ledger.read_text('utf-8-sig'))
    if pre.get('status')!='passed' or pre.get('corpus_sha256')!=sha:raise ValueError('Missing successful native preflight for this corpus')
    if {d['dbms'] for d in pre['databases']}!={'mysql','postgres'}:raise ValueError('Both database preflights are required')
    if freeze.get('corpus_sha256')!=sha or freeze.get('ci_conclusion')!='success':raise ValueError('Missing CI freeze')
    if not freeze.get('image_digest') or receipt.get('image')!=freeze['image_digest']:raise ValueError('Deployment receipt does not match frozen image')
    if not receipt.get('checkedAt'):raise ValueError('Deployment health check is missing')
    used=previous['generation_requests_used'];limit=previous['generation_request_limit_this_overnight_cycle']
    if used+26>limit:raise ValueError('Insufficient remaining budget for 24 candidates and 2 probes')
    prompts={c['id']:prompt(c,corpus['schema_ddl']) for c in corpus['cases']}
    # Conservative byte bound reserves 512 tokens for the model chat wrapper
    # and 1200 for output. No prompt is silently truncated to fit the context.
    if any(len(s.encode('utf-8'))>2300 for s in prompts.values()):raise ValueError('Prompt exceeds conservative context bound')
    tags=request('tags');version=request('version');available={x['name']:x for x in tags['models']}
    if any(m not in available for m in MODELS):raise ValueError('A required installed model is missing')
    lock=a.prior_budget_ledger.with_suffix('.collection.lock')
    with lock.open('x',encoding='utf-8') as handle:
        handle.write(str(a.output.resolve()))
    # A crash intentionally leaves this lock. Reconcile the ledger before
    # removing it; never silently repeat a partially completed collection.
    a.output.mkdir(parents=True,exist_ok=False)
    write(a.output/'protocol.json',{'utc':datetime.now(timezone.utc).isoformat(),'corpus_sha256':sha,'freeze':freeze,'ollama':version,'models':{m:available[m] for m in MODELS},'options':OPTIONS,'prompts':prompts,'budget_before':used,'budget_limit':limit,'scope':'24 MySQL generation attempts; no equivalence classification in collector'})
    ledger={'generation_requests_used':used,'generation_request_limit_this_overnight_cycle':limit,'attempts':[]}
    def call(model,key,text,probe=False):
        ledger['generation_requests_used']+=1
        item={'model':model,'case':key,'probe':probe,'status':'started','utc':datetime.now(timezone.utc).isoformat()}
        ledger['attempts'].append(item);write(a.output/'budget.json',ledger)
        previous['generation_requests_used']=ledger['generation_requests_used']
        write(a.prior_budget_ledger,previous)
        start=time.monotonic()
        try:
            answer=request('generate',{'model':model,'prompt':text,'stream':False,'options':dict(OPTIONS,num_predict=16) if probe else OPTIONS},240)
            item['status']='received' if answer.get('done') else 'incomplete'
            write(a.output/(model.split(':')[0]+'_'+key+'.json'),{'request':text,'response':answer,'elapsed_seconds':time.monotonic()-start})
            return True
        except Exception as exc:
            item['status']='service_error';item['error']=str(exc);return False
        finally:
            item['elapsed_seconds']=time.monotonic()-start;write(a.output/'budget.json',ledger)
    for model in MODELS:
        failures=0
        try:
            if not call(model,'availability','Reply READY.',True):failures=1
            for case in corpus['cases']:
                ok=call(model,case['id'],prompts[case['id']]);failures=0 if ok else failures+1
                print(model,case['id'],ledger['attempts'][-1]['status'],flush=True)
                if failures>=2:break
        finally:
            try:request('generate',{'model':model,'keep_alive':0},30)
            except Exception as exc:write(a.output/(model.split(':')[0]+'_unload_error.json'),{'error':str(exc)})
    write(a.output/'summary.json',{'generation_requests_used':ledger['generation_requests_used'],'candidate_attempts':sum(not x['probe'] for x in ledger['attempts']),'received_candidates':sum(not x['probe'] and x['status']=='received' for x in ledger['attempts']),'status':'collection_finished_not_evaluated','no_sql_executed':True})
    lock.unlink()

if __name__=='__main__':main()
