"""Prepare a synthetic corpus BEFORE model collection; not a freeze certificate."""
import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DDL = [
    'CREATE TEMPORARY TABLE lib_readers(id INTEGER PRIMARY KEY, name VARCHAR(40) NOT NULL UNIQUE)',
    'CREATE TEMPORARY TABLE lib_books(id INTEGER PRIMARY KEY, title VARCHAR(40) NOT NULL UNIQUE, price INTEGER NOT NULL)',
    'CREATE TEMPORARY TABLE lib_loans(id INTEGER PRIMARY KEY, reader_id INTEGER NOT NULL, book_id INTEGER NOT NULL, day_no INTEGER NOT NULL, fee INTEGER NOT NULL, returned INTEGER, FOREIGN KEY(reader_id) REFERENCES lib_readers(id), FOREIGN KEY(book_id) REFERENCES lib_books(id))',
]
# Persistent tables in a dedicated schema are required: MySQL temporary tables do
# not enforce foreign keys. The preflight runner creates and drops its own schema.
DDL = [s.replace('CREATE TEMPORARY TABLE', 'CREATE TABLE') for s in DDL]
QUERIES = [
 ('no_loans', 'Читатели без выдач', 'SELECT r.id FROM lib_readers r WHERE NOT EXISTS (SELECT 1 FROM lib_loans l WHERE l.reader_id=r.id) ORDER BY r.id'),
 ('loan_count', 'Число выдач, включая ноль', 'SELECT r.id,COUNT(l.id) AS n FROM lib_readers r LEFT JOIN lib_loans l ON l.reader_id=r.id GROUP BY r.id ORDER BY r.id'),
 ('zero_fee', 'Читатели с нулевой суммой сборов', 'SELECT r.id FROM lib_readers r LEFT JOIN lib_loans l ON l.reader_id=r.id GROUP BY r.id HAVING COALESCE(SUM(l.fee),0)=0 ORDER BY r.id'),
 ('returned_count', 'Число возвратов среди имеющих выдачи', 'SELECT reader_id,COUNT(CASE WHEN returned=1 THEN 1 END) AS n FROM lib_loans GROUP BY reader_id ORDER BY reader_id'),
 ('borrowers', 'Читатели, бравшие недорогие книги', 'SELECT DISTINCT r.id FROM lib_readers r JOIN lib_loans l ON l.reader_id=r.id JOIN lib_books b ON b.id=l.book_id WHERE b.price<=20 ORDER BY r.id'),
 ('latest_ties', 'Все выдачи в последний день читателя', 'SELECT l.id,l.reader_id,l.day_no FROM lib_loans l WHERE l.day_no=(SELECT MAX(x.day_no) FROM lib_loans x WHERE x.reader_id=l.reader_id) ORDER BY l.id'),
 ('price_range', 'Книги в замкнутом диапазоне цены', 'SELECT id,price FROM lib_books WHERE price BETWEEN 10 AND 20 ORDER BY id'),
 ('not_returned', 'Выдачи с известным отсутствием возврата', 'SELECT id FROM lib_loans WHERE returned<>1 ORDER BY id'),
 ('active_outer', 'Все читатели и невозвращённые выдачи', 'SELECT r.id,l.id AS loan_id FROM lib_readers r LEFT JOIN lib_loans l ON l.reader_id=r.id AND l.returned=0 ORDER BY r.id,l.id'),
 ('union_bag', 'Объединение выдач с сохранением повторов', 'SELECT reader_id FROM lib_loans WHERE returned=0 UNION ALL SELECT reader_id FROM lib_loans WHERE fee=0 ORDER BY reader_id'),
 ('all_returned', 'Читатели, у которых все выдачи возвращены', 'SELECT r.id FROM lib_readers r WHERE EXISTS (SELECT 1 FROM lib_loans l WHERE l.reader_id=r.id) AND NOT EXISTS (SELECT 1 FROM lib_loans l WHERE l.reader_id=r.id AND (l.returned<>1 OR l.returned IS NULL)) ORDER BY r.id'),
 ('top_books', 'Две самые дорогие книги с разрешением равенств', 'SELECT id,price FROM lib_books ORDER BY price DESC,id ASC LIMIT 2'),
]

def state(profile, seed=0):
    readers = [[1,'Reader_A'],[2,'Reader_B'],[3,'Reader_C']]
    books = [[1,'Book_A',10],[2,'Book_B',20],[3,'Book_C',30]]
    loans = [[1,1,1,1,2,1],[2,2,2,2,3,0]]
    if profile == 'empty': readers, books, loans = [], [], []
    elif profile == 'no_loans': loans=[]
    elif profile == 'multiplicity': loans=[[1,1,1,1,1,0],[2,1,2,2,0,0],[3,1,1,3,0,1],[4,2,3,3,1,1]]
    elif profile == 'zero_fee': loans=[[1,1,1,1,0,1],[2,2,2,1,4,0],[3,2,3,2,-4,1]]
    elif profile == 'nullable': loans=[[1,1,1,1,0,None],[2,2,2,2,0,0],[3,3,3,3,0,1]]
    elif profile == 'boundary': books=[[i,f'Book_{i}',v] for i,v in enumerate([9,10,11,19,20,21],1)]
    elif profile == 'ties':
        books=[[1,'Book_A',20],[2,'Book_B',20],[3,'Book_C',20]]
        loans=[[1,1,1,5,0,0],[2,1,2,5,0,1],[3,1,3,4,1,1],[4,2,1,5,0,None]]
    elif profile == 'random_uniform':
        rng=random.Random(41000+seed)
        books=[[i,f'Book_{i}',rng.randint(0,40)] for i in range(1,5)]
        loans=[[i,rng.randint(1,3),rng.randint(1,4),rng.randint(1,8),rng.randint(-5,10),rng.choice([None,0,1])] for i in range(1,rng.randint(0,12)+1)]
    return {'id':f'{profile}_{seed}','profile':profile,'seed':seed,'tables':{'lib_readers':readers,'lib_books':books,'lib_loans':loans}}

def oracle(key,s):
    """Relational intent evaluated without executing SQL, for value checks only."""
    r,b,l=(s['tables'][x] for x in ['lib_readers','lib_books','lib_loans'])
    by_reader={row[0]:[x for x in l if x[1]==row[0]] for row in r}
    if key=='no_loans':return [[i] for i,v in by_reader.items() if not v]
    if key=='loan_count':return [[i,len(v)] for i,v in by_reader.items()]
    if key=='zero_fee':return [[i] for i,v in by_reader.items() if sum(x[4] for x in v)==0]
    if key=='returned_count':return [[i,sum(x[5]==1 for x in v)] for i,v in by_reader.items() if v]
    if key=='borrowers':return [[i] for i,v in by_reader.items() if any(next(z[2] for z in b if z[0]==x[2])<=20 for x in v)]
    if key=='latest_ties':return [[x[0],x[1],x[3]] for x in l if x[3]==max(z[3] for z in by_reader[x[1]])]
    if key=='price_range':return [[x[0],x[2]] for x in b if 10<=x[2]<=20]
    if key=='not_returned':return [[x[0]] for x in l if x[5] is not None and x[5]!=1]
    if key=='active_outer':return [[i,x[0] if x else None] for i,v in by_reader.items() for x in ([z for z in v if z[5]==0] or [None])]
    if key=='union_bag':return sorted([[x[1]] for x in l if x[5]==0]+[[x[1]] for x in l if x[4]==0])
    if key=='all_returned':return [[i] for i,v in by_reader.items() if v and all(x[5]==1 for x in v)]
    if key=='top_books':return [[x[0],x[2]] for x in sorted(b,key=lambda x:(-x[2],x[0]))[:2]]
    raise ValueError(key)

def main():
    states=[state(p) for p in ['fixed','empty','no_loans','multiplicity','zero_fee','nullable','boundary','ties']]
    states += [state('random_uniform',s) for s in range(20)]
    controls=[
        {'case':'price_range','sql':'SELECT id,price FROM lib_books WHERE price>=10 AND price<=20 ORDER BY id','reason':'BETWEEN includes both boundaries; non-null integer price.'},
        {'case':'not_returned','sql':'SELECT id FROM lib_loans WHERE NOT(returned=1) ORDER BY id','reason':'Both expressions preserve UNKNOWN for NULL.'},
        {'case':'returned_count','sql':'SELECT reader_id,COUNT(CASE WHEN returned=1 THEN id END) AS n FROM lib_loans GROUP BY reader_id ORDER BY reader_id','reason':'Loan primary key is non-null, preserving conditional count.'},
        {'case':'loan_count','sql':'SELECT r.id,COUNT(CASE WHEN l.id IS NOT NULL THEN l.id END) AS n FROM lib_readers r LEFT JOIN lib_loans l ON l.reader_id=r.id GROUP BY r.id ORDER BY r.id','reason':'Non-null child key counted exactly once per joined child.'},
    ]
    data={'version':'library_v1_draft','status':'awaiting_native_preflight_and_CI_freeze','source':'manually authored synthetic library workload; not independent real-world sampling','candidate_outputs_seen':False,'schema_ddl':DDL,'cases':[{'id':k,'intent':t,'sql':q,'ordered':True} for k,t,q in QUERIES],'states':states,'expected_values':{k:{s['id']:oracle(k,s) for s in states} for k,_,_ in QUERIES},'positive_controls':controls,'comparison':'Values including multiplicity and deterministic row order; interfaces separately within each DBMS. NULL only in returned column.','budget':'12 cases x 28 states x 2 DBMS = 672 reference executions; model collection planned only for MySQL (24 responses); no claim of model portability.'}
    path=ROOT/'corpus.json'
    if path.exists():raise SystemExit('Refusing to replace an existing corpus; use a new version directory.')
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(hashlib.sha256(path.read_bytes()).hexdigest())

if __name__=='__main__':main()
