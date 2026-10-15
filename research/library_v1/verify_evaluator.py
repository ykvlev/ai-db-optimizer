"""CI controls, not model outputs or additional scientific observations."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from evaluate import ROOT, MODELS, validate

out = Path('evaluator-controls')
collection = out / 'artificial-input'
collection.mkdir(parents=True, exist_ok=False)
raw = (ROOT / 'corpus.json').read_bytes()
data = json.loads(raw)
(collection / 'protocol.json').write_text(json.dumps({'corpus_sha256': hashlib.sha256(raw).hexdigest(), 'artificial_controls': True}))
for model in MODELS:
    for case in data['cases']:
        sql = case['sql']
        if model == MODELS[1] and case['id'] == 'loan_count':
            sql = sql.replace('COUNT(l.id)', 'COUNT(*)')
        validate(sql)
        (collection / (model.split(':')[0] + '_' + case['id'] + '.json')).write_text(json.dumps({'response': {'done': True, 'response': sql}}))
for sql in ['DELETE FROM lib_books', 'SELECT SLEEP(10)', "SELECT LOAD_FILE('/etc/passwd')", 'SELECT * FROM mysql.user', 'SELECT 1; SELECT 2']:
    try:
        validate(sql)
    except Exception:
        pass
    else:
        raise AssertionError('Guard accepted forbidden control')
subprocess.run([sys.executable, str(ROOT / 'evaluate.py'), '--collection', str(collection), '--output', str(out / 'results')], check=True)
results = json.loads((out / 'results/results.json').read_text('utf-8'))
assert len(results) == 24
for result in results:
    expected = 'counterexample' if result['model'] == MODELS[1] and result['case'] == 'loan_count' else 'not_refuted'
    assert result['status'] == expected, result
assert sum(len(r['checks']) for r in results) == 672
print('23 identity controls and 1 deliberate mutation classified correctly; 672 pairs.')
