from pathlib import Path
from copy import deepcopy
import json, hashlib, zipfile, collections, re
from lxml import etree as E

ROOT=Path('C:/Users/Артём/Documents/Science')
TMP=ROOT/'ai-db-optimizer/tmp/sitito'
OUT=ROOT/'Научные материалы/01 Статьи/МГУ — СИТИТО 2026'
OUT.mkdir(parents=True,exist_ok=True)
REF=Path('C:/Users/Артём/Downloads/sitito_template.docx')
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
def q(s): return '{'+NS['w']+'}'+s
z=zipfile.ZipFile(REF); root=E.fromstring(z.read('word/document.xml')); body=root.find(q('body')); ps=body.findall(q('p')); sect=deepcopy(body.find(q('sectPr')))
license_table=deepcopy(body.find(q('tbl')))
raw=(ROOT/'ai-db-optimizer/docs/nir/data.json').read_bytes(); D=json.loads(raw)
models=list(D['exp']['7']['summary']); names=['GigaChat-2','GigaChat-2-Pro','GigaChat-2-Max','Qwen2.5-Coder 7B','Правила']
outcomes=['improved','unchanged','worse','invalid','error']
rows={m:[r for k in ['7','8'] for r in D['exp'][k]['results'] if r['model']==m] for m in models}
sets={m:{(k,r['key']) for k in ['7','8'] for r in D['exp'][k]['results'] if r['model']==m and r['outcome']=='improved'} for m in models}; base=sets[models[-1]]
tables={
'TABLE1':('Распределение исходов на 80 задачах для каждого участника','Outcome distribution across 80 tasks per participant',['Участник','Ускорение','Без изменения','Замедление','Некорректный исход','Сбой'],[[names[i]]+[str(collections.Counter(r['outcome'] for r in rows[m])[o]) for o in outcomes] for i,m in enumerate(models)]),
'TABLE2':('Ускорения и некорректные исходы по СУБД','Improvements and invalid outcomes by DBMS',['Участник','MySQL: ускорение','MySQL: некорр.','PostgreSQL: ускорение','PostgreSQL: некорр.'],[[names[i]]+[str(collections.Counter(r['outcome'] for r in D['exp'][k]['results'] if r['model']==m)[o]) for k in ['7','8'] for o in ['improved','invalid']] for i,m in enumerate(models)]),
'TABLE3':('Пересечение ускорений языковых моделей и правил','Overlap between improvements obtained by language models and rules',['Модель','У обоих','Только модель','Только правила','Объединение'],[[names[i],str(len(sets[m]&base)),str(len(sets[m]-base)),str(len(base-sets[m])),str(len(sets[m]|base))] for i,m in enumerate(models[:-1])]),
}
st=[]
for i in [1,2]:
 m=models[i];maps=[{r['key']:r['outcome'] for r in D['exp'][k]['results'] if r['model']==m} for k in ['7','9','10']]
 st.append([names[i],str(sum(len({x[k] for x in maps})==1 for k in maps[0])),str(sum(all(x[k]=='improved' for x in maps) for k in maps[0])),str(sum(any(x[k]=='improved' for x in maps) for k in maps[0]))])
tables['TABLE4']=('Устойчивость исходов в трёх сериях на 40 запросах MySQL','Outcome stability across three runs on 40 MySQL queries',['Модель','Одинаковый исход','Ускорение во всех','Ускорение хотя бы в одной'],st)
tables['TABLE5']=(
 'Проверка эквивалентности переписываний на замороженном корпусе «Библиотека» (по 336 проверок «запрос × состояние» на модель)',
 'Equivalence checking of rewrites on the frozen Library corpus (336 query × state checks per model)',
 ['Модель','Параметр, млрд','Ответов','Предложено переписываний','Опровергнуто','Без контрпримера','Проверок'],
 [['Qwen2.5-Coder-7B','7,6','12 из 12','5','3','9','336'],
  ['Phi-3.5-mini 3.8B','3,8','12 из 12','2','1','11','336']])
(TMP/'analysis.json').write_text(json.dumps({'source_sha256':hashlib.sha256(raw).hexdigest(),'tables':tables},ensure_ascii=False,indent=2),encoding='utf8')

refs=[
 'Selinger P.G., Astrahan M.M., Chamberlin D.D., Lorie R.A., Price T.G. Access Path Selection in a Relational Database Management System. Proceedings of SIGMOD. 1979:23–34. doi:10.1145/582095.582099.',
 'Begoli E., Camacho-Rodríguez J., Hyde J., Mior M.J., Lemire D. Apache Calcite: A Foundational Framework for Optimized Query Processing Over Heterogeneous Data Sources. 2018. Available at: https://arxiv.org/abs/1802.10233 (accessed 14.10.2026).',
 'Liu J., Mozafari B. GenRewrite: Query Rewriting via Large Language Models. arXiv:2403.09060v3. 2025. Available at: https://arxiv.org/abs/2403.09060v3 (accessed 14.10.2026).',
 'Li Z., Yuan H., Wang H., Cong G., Bing L. LLM-R2: A Large Language Model Enhanced Rule-based Rewrite System for Boosting Query Efficiency. 2024. doi:10.48550/arXiv.2404.12872.',
 'Yu T., Zhang R., Yang K., et al. Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic Parsing and Text-to-SQL Task. Proceedings of EMNLP. 2018:3911–3921. doi:10.18653/v1/D18-1425.',
 'Gao D., Wang H., Li Y., Sun X., Qian Y., Ding B., et al. Text-to-SQL Empowered by Large Language Models: A Benchmark Evaluation // Proceedings of the VLDB Endowment. 2024. Vol. 17, № 5. P. 1132–1145. doi:10.14778/3641204.3641221.',
 'Deng C., Fan J., Luo Y., Xue Q., Fan M., Zhang Y., et al. TACO: A Benchmark for Open-Domain Text-to-SQL with Ambiguous and Cross-Database Queries // Proceedings of the VLDB Endowment. 2026. Vol. 19, № 6. P. 1386–1399. doi:10.14778/3797919.3797942.',
 'Zhan Z., Haihong E., Song M. Leveraging Large Language Model for Enhanced Text-to-SQL Parsing // IEEE Access. 2025. Vol. 13. P. 30497–30504. doi:10.1109/ACCESS.2025.3540072.',
 'Luo Y., Li G., Fan J., Chai C., Tang N. Natural Language to SQL: State of the Art and Open Problems // Proceedings of the VLDB Endowment. 2025. Vol. 18, № 12. P. 5466–5471. doi:10.14778/3750601.3750696.',
 'Li B., Luo Y., Chai C., Li G., Tang N. The Dawn of Natural Language to SQL: Are We Fully Ready? // Proceedings of the VLDB Endowment. 2024. Vol. 17, № 11. P. 3318–3331. doi:10.14778/3681954.3682003.',
 'Li J., Hui B., Qu G., et al. Can LLM Already Serve as A Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs. 2023. doi:10.48550/arXiv.2305.03111.',
 'Chang S., Wang J., Dong M., Pan L., Zhu H., Li A. H., et al. Dr.Spider: A Diagnostic Evaluation Benchmark towards Text-to-SQL Robustness. 2023. arXiv:2301.08881. URL: https://arxiv.org/abs/2301.08881 (дата обращения: 16.10.2026).',
 'Song M., Zheng M. A Survey of Query Optimization in Large Language Models. 2024. arXiv:2412.17558. URL: https://arxiv.org/abs/2412.17558 (дата обращения: 16.10.2026).',
 'Tan J., Zhao K., Li R., Yu J. X., Piao C., Cheng H., et al. Can Large Language Models Be Query Optimizer for Relational Databases? 2025. arXiv:2502.05562. URL: https://arxiv.org/abs/2502.05562 (дата обращения: 16.10.2026).',
 'Dharwada S., Devrani H., Haritsa J., Doraiswamy H. Query Rewriting via LLMs. 2025. arXiv:2502.12918. URL: https://arxiv.org/abs/2502.12918 (дата обращения: 16.10.2026).',
 'Fathollahzadeh S., Mansour E., Boehm M. ReSequel: Robust LLM-assisted Query Rewriting and Optimization using Templatization and Sampling // Proceedings of the VLDB Endowment. 2026. Vol. 19, № 10. P. 2880–2893. doi:10.14778/3828612.3828639.',
 'Kostov M., Kaloyanova K. Feedback-Driven SQL Optimization with Validated Query Rewrites // Electronics. 2026. Vol. 15, № 13. P. 2931. doi:10.3390/electronics15132931.',
 'Schmidt T., Reif M., Birler A., Neumann T. QueryBrew: System-Agnostic SQL-to-SQL Query Optimization // Proceedings of the VLDB Endowment. 2026. Vol. 19, № 12. P. 4494–4497. doi:10.14778/3827998.3828048.',
 'Hui B., Yang J., Cui Z., et al. Qwen2.5-Coder Technical Report. 2024. doi:10.48550/arXiv.2409.12186.',
 'Ji Z., Lee N., Frieske R., et al. Survey of Hallucination in Natural Language Generation. arXiv:2202.03629. Available at: https://arxiv.org/abs/2202.03629 (accessed 14.10.2026).',
 'Rahaman A., Zheng A., Milani M., Chiang F., Pottinger R. Evaluating SQL Understanding in Large Language Models // Proceedings of EDBT. 2025. P. 909–921. doi:10.48786/EDBT.2025.74.',
 'Wen H., Zhu Y., Liu C., Ren X., Du W., Yan M., et al. Analyzing and Fixing Code Generation Errors of Foundation Large Language Models // Empirical Software Engineering. 2026. Vol. 32, № 1. doi:10.1007/s10664-026-10958-5.',
 'Zhong R., Yu T., Klein D. Semantic Evaluation for Text-to-SQL with Distilled Test Suites. Proceedings of EMNLP. 2020:396–411. doi:10.18653/v1/2020.emnlp-main.29.',
 'Chu S., Wang C., Weitz K., Cheung A. Cosette: An Automated Prover for SQL. CIDR. 2017. Available at: https://www.cidrdb.org/cidr2017/papers/p51-chu-cidr17.pdf (accessed 14.10.2026).',
 'Chu S., Weitz K., Cheung A., Suciu D. HoTTSQL: Proving Query Rewrites with Univalent SQL Semantics. 2016. arXiv:1607.04822. URL: https://arxiv.org/abs/1607.04822 (дата обращения: 16.10.2026).',
 'Wang S., Pan S., Cheung A. QED: A Powerful Query Equivalence Decider for SQL // Proceedings of the VLDB Endowment. 2024. Vol. 17, № 11. P. 3602–3614. doi:10.14778/3681954.3682024.',
 'He Y., Zhao P., Wang X., Wang Y. VeriEQL: Bounded Equivalence Verification for Complex SQL Queries with Integrity Constraints // Proceedings of the ACM on Programming Languages. 2024. Vol. 8, № OOPSLA1. P. 1071–1099. doi:10.1145/3649849.',
 'Zhou Q., Arulraj J., Navathe S., Harris W., Wu J. A Symbolic Approach to Proving Query Equivalence Under Bag Semantics. 2020. arXiv:2004.00481. URL: https://arxiv.org/abs/2004.00481 (дата обращения: 16.10.2026).',
 'Rigger M., Su Z. Testing Database Engines via Pivoted Query Synthesis. Proceedings of OSDI. 2020:667–682. Available at: https://www.usenix.org/conference/osdi20/presentation/rigger (accessed 14.10.2026).',
 'Wei J., Chen P., Lu K., Dai J., Sun X. SQLaser: Detecting Database Management System (DBMS) Logic Bugs with Clause-Guided Fuzzing // Journal of Computer Security. 2025. Vol. 34, № 1. P. 3–28. doi:10.1177/0926227X251370258.',
 'Gao X., Liu Z., Cui J., Li H., Zhang H., Wei K., et al. A Comprehensive Survey on Database Management System Fuzzing: Techniques, Taxonomy and Evaluation // ACM Computing Surveys. 2026. Vol. 58, № 10. P. 1–36. doi:10.1145/3799227.',
 'Zhang C., Rigger M. Constant Optimization Driven Database System Testing // Proceedings of the ACM on Management of Data. 2025. Vol. 3, № 1. P. 1–24. doi:10.1145/3709674.',
 'Rigger M., Su Z. Detecting Optimization Bugs in Database Engines via Non-Optimizing Reference Engine Construction. 2020. doi:10.48550/arXiv.2007.08292.',
 'Rigger M., Su Z. Finding Bugs in Database Systems via Query Partitioning // Proceedings of the ACM on Programming Languages. 2020. Vol. 4, OOPSLA. Article 211. DOI: 10.1145/3428279.',
 'Oracle. MySQL 8.4 Reference Manual. EXPLAIN Output Format. Available at: https://dev.mysql.com/doc/refman/8.4/en/explain-output.html (accessed 14.10.2026).',
 'PostgreSQL Global Development Group. PostgreSQL 16 Documentation. Using EXPLAIN. Available at: https://www.postgresql.org/docs/16/using-explain.html (accessed 14.10.2026).',
 'Kalibera T., Jones R. Rigorous Benchmarking in Reasonable Time. Proceedings of ISMM. 2013:63–74. Available at: https://kar.kent.ac.uk/33611/ (accessed 14.10.2026).',
 'Hoefler T., Belli R. Scientific Benchmarking of Parallel Computing Systems: Twelve Ways to Tell the Masses When Reporting Performance Results. Proceedings of SC. 2015. Available at: https://htor.inf.ethz.ch/publications/index.php?pub=222 (accessed 14.10.2026).',
 'Ollama. Source Code and Documentation. Available at: https://github.com/ollama/ollama (accessed 14.10.2026).',
 'SQLGlot. Python SQL Parser and Transpiler. Available at: https://github.com/tobymao/sqlglot (accessed 14.10.2026).',
 'Oracle. MySQL 8.4 Reference Manual. Aggregate Function Descriptions. Available at: https://dev.mysql.com/doc/refman/8.4/en/aggregate-functions.html (accessed 14.10.2026).',
 'Ricciotti W., Cheney J. A Formalization of SQL with Nulls. 2020. arXiv:2003.11331. URL: https://arxiv.org/abs/2003.11331 (дата обращения: 16.10.2026).',
 'PostgreSQL Global Development Group. PostgreSQL 16 Documentation. Sorting Rows. Available at: https://www.postgresql.org/docs/16/queries-order.html (accessed 14.10.2026).',
 'Fu T., Martínez G., Conde J., Arriaga C., Reviriego P., Qi X., et al. Beyond Reproducibility: Token Probabilities Expose Large Language Model Nondeterminism // IEEE Transactions on Computers. 2026. P. 1–14. doi:10.1109/TC.2026.3732142.',
 'Ding H., Wang Z., Yang Y. et al. Proving Query Equivalence Using Linear Integer Arithmetic // Proceedings of the ACM on Management of Data. 2023. Vol. 1, № 4. Article 227. URL: https://github.com/SJTU-IPADS/SQLSolver.',
 'Yakovlev A.S. AI Database Optimizer. Source Code. Available at: https://github.com/ykvlev/ai-db-optimizer (accessed 14.10.2026).',
]
title='Сравнение языковых моделей и правил при оптимизации SQL на MySQL и PostgreSQL'
eng='Comparing Language Models and Rules for SQL Optimization on MySQL and PostgreSQL'
ru=[
('Введение.','Языковые модели предлагают изменения SQL, однако их полезность определяется сохранением результата и временем исполнения. Цель работы — сопоставить четыре модели и набор правил на общем корпусе и отдельно проверить сохранение результата на замороженном корпусе контролируемых состояний.'),
('Материалы и методы.','Проанализированы сохранённые журналы 40 шаблонов запросов в вариантах для MySQL и PostgreSQL; основное сравнение включает 400 записей — по 80 задач на участника. После проверки результатов на фиксированной синтетической базе выполнялись два прогрева и пять измерений каждой пары запросов; ускорение определялось отношением медиан не менее 1,05. Отдельно рассмотрены повторные серии MySQL и исключение плана из задания. На корпусе из 12 запросов и 28 состояний проверены переписывания Qwen2.5-Coder 7B и Phi-3.5-mini 3.8B.'),
('Результаты исследования.','GigaChat-2-Pro дал 29 ускорений из 80 задач, GigaChat-2 — 23, правила — 17, Qwen — 16, Max — 14; у Pro также 17 замедлений и 16 некорректных исходов, четыре обращения завершились инфраструктурным сбоем. На замороженном корпусе из семи предложенных переписываний четыре опровергнуты: обе модели независимо заменили UNION ALL на OR и потеряли кратности строк, чего не обнаружило ни одно из 20 случайных состояний. Скорость в этой серии не измерялась.'),
('Обсуждение и заключение.','Преимущество по числу ускорений не означает преимущества по всем критериям, а совпадение на проверенных состояниях не доказывает эквивалентность. Результаты ограничены синтетическими корпусами, одним стендом и описательным анализом. Для обобщения необходимы новые схемы, заранее зафиксированные запросы и оценка неопределённости измерений.')]
en=[
('Introduction.','Language models can propose SQL rewrites, but their practical value depends on preserving query results and reducing execution time. This study compares four models with deterministic rules and separately checks result preservation on a frozen corpus of controlled states.'),
('Materials and Methods.','Stored experimental logs cover 40 query templates adapted to MySQL and PostgreSQL; the primary comparison contains 400 records, with 80 tasks per participant. Result checking uses a fixed synthetic database, and timing consists of two warm-up and five measured executions per query, with an improvement threshold of 1.05 for the ratio of median times. Additional MySQL runs and a plan-exclusion variant were also examined. A corpus of 12 queries with 28 states each was used to check rewrites proposed by Qwen2.5-Coder 7B and Phi-3.5-mini 3.8B.'),
('Results.','GigaChat-2-Pro produced 29 improvements, compared with 23 for GigaChat-2, 17 for rules, 16 for Qwen, and 14 for Max; Pro also produced 17 slowdowns and 16 invalid outcomes, and four model requests failed at the infrastructure level. On the frozen corpus four of seven proposed rewrites were refuted: both models independently replaced UNION ALL with OR and lost row multiplicities, which none of 20 random states detected. Execution time was not measured in that series.'),
('Discussion and Conclusion.','More improvements do not establish superiority across all criteria, and agreement on the tested states does not prove equivalence. Findings are limited to synthetic workloads, one computing environment, and descriptive analysis. Additional schemas, prespecified tasks, and uncertainty assessment are needed.')]

def para(text,idx=114,bold=None,size=None,keep=False,page=False,after=None):
 p=deepcopy(ps[idx]);
 for c in list(p):
  if c.tag!=q('pPr'):p.remove(c)
 pp=p.find(q('pPr'))
 if pp is None:pp=E.SubElement(p,q('pPr'))
 for tag in ['pageBreakBefore','keepNext','sectPr','numPr']:
  for c in pp.findall(q(tag)):pp.remove(c)
 if keep:E.SubElement(pp,q('keepNext'))
 if page:E.SubElement(pp,q('pageBreakBefore'))
 if after is not None:
  sp=pp.find(q('spacing'))
  if sp is None:sp=E.SubElement(pp,q('spacing'))
  sp.set(q('after'),str(after));sp.set(q('before'),'0')
 r=E.SubElement(p,q('r'));source=ps[idx].find('.//'+q('rPr'))
 rp=deepcopy(source) if source is not None else E.Element(q('rPr'));r.append(rp)
 for tag in ['color','highlight','b','bCs']:
  for c in rp.findall(q(tag)):rp.remove(c)
 E.SubElement(rp,q('color')).set(q('val'),'000000')
 if bold:E.SubElement(rp,q('b'))
 if size:
  for tag in ['sz','szCs']:
   for c in rp.findall(q(tag)):rp.remove(c)
   E.SubElement(rp,q(tag)).set(q('val'),str(int(size*2)))
 t=E.SubElement(r,q('t'));t.set('{http://www.w3.org/XML/1998/namespace}space','preserve');t.text=text
 return p

def abstract_para(label,text,idx):
 p=para(label,idx,bold=True,after=80)
 r=E.SubElement(p,q('r'));rp=E.SubElement(r,q('rPr'));E.SubElement(rp,q('rFonts'),{q('ascii'):'Times New Roman',q('hAnsi'):'Times New Roman'});E.SubElement(rp,q('sz'),{q('val'):'20'})
 t=E.SubElement(r,q('t'));t.set('{http://www.w3.org/XML/1998/namespace}space','preserve');t.text=' '+text
 return p

def table(n):
 ru_t,en_t,headers,rr=tables[f'TABLE{n}']
 body.append(para(f'Таблица {n}. {ru_t}',bold=True,keep=True,after=40))
 body.append(para(f'Table {n}. {en_t}',keep=True,after=80))
 tab=E.Element(q('tbl'));pr=E.SubElement(tab,q('tblPr'))
 E.SubElement(pr,q('tblW'),{q('w'):'9560',q('type'):'dxa'})
 borders=E.SubElement(pr,q('tblBorders'))
 for k in ['top','left','bottom','right','insideH','insideV']:E.SubElement(borders,q(k),{q('val'):'single',q('sz'):'4',q('color'):'000000'})
 widths=[2400]+[int(7160/(len(headers)-1))]*(len(headers)-1)
 grid=E.SubElement(tab,q('tblGrid'))
 for w in widths:E.SubElement(grid,q('gridCol'),{q('w'):str(w)})
 for ri,row in enumerate([headers]+rr):
  tr=E.SubElement(tab,q('tr'));trpr=E.SubElement(tr,q('trPr'));E.SubElement(trpr,q('cantSplit'))
  if ri==0:E.SubElement(trpr,q('tblHeader'))
  for ci,t in enumerate(row):
   tc=E.SubElement(tr,q('tc'));tcpr=E.SubElement(tc,q('tcPr'));E.SubElement(tcpr,q('tcW'),{q('w'):str(widths[ci]),q('type'):'dxa'})
   mar=E.SubElement(tcpr,q('tcMar'))
   for k,v in [('top',70),('bottom',70),('left',70),('right',70)]:E.SubElement(mar,q(k),{q('w'):str(v),q('type'):'dxa'})
   if ri==0:E.SubElement(tcpr,q('shd'),{q('fill'):'EEEEEE'})
   p=para(t,bold=ri==0,size=10,keep=ri<len(rr),after=0);pp=p.find(q('pPr'))
   for c in pp.findall(q('ind'))+pp.findall(q('jc')):pp.remove(c)
   E.SubElement(pp,q('jc'),{q('val'):'left' if ci==0 else 'center'})
   tc.append(p)
 body.append(tab);body.append(para('',after=80))

# Only document.xml and core metadata are editable. The retained package owns styles and page geometry.
for c in list(body):body.remove(c)
body.append(para('УДК 004.65',0,bold=True,size=10,after=120))
body.append(para('Оригинальная статья',5,after=180))
body.append(para(title,10,bold=True,size=16,keep=True,after=200))
body.append(para('А. С. Яковлев',17,bold=True,size=12,after=60))
aff='Политехнический колледж Новгородского государственного университета имени Ярослава Мудрого, г. Великий Новгород, Российская Федерация'
address='Адрес: Российская Федерация, г. Великий Новгород, ул. Большая Санкт-Петербургская, д. 46'
body.append(para(aff,18,after=40));body.append(para(address,19,after=40));body.append(para('jackowleffa@yandex.ru',20,after=200))
body.append(para('Аннотация',25,bold=True,size=12,keep=True,after=80))
for label,t in ru:body.append(abstract_para(label,t,26))
body.append(para('Ключевые слова: SQL, языковые модели, оптимизация запросов, MySQL, PostgreSQL, проверка результатов, измерение производительности',44,size=10,after=140))
body.append(para('Конфликт интересов: автор заявляет об отсутствии конфликта интересов.',47,size=10,after=80))
body.append(para('© Яковлев А. С., 2026',53,size=10,after=80))
# Preserve the license component, including its drawing relationships, from the original template.
for i in range(54,59):
 if ps[i].find('.//'+q('drawing')) is not None or ''.join(ps[i].itertext()).find('Creative Commons')>=0:body.append(deepcopy(ps[i]))
for lp in license_table.findall('.//'+q('p')):
 ts=lp.findall('.//'+q('t'))
 if ''.join(x.text or '' for x in ts).startswith('Контент'):
  ts[0].text='Контент доступен под лицензией Creative Commons Attribution 4.0 License.'
  for x in ts[1:]:x.text=''
body.append(license_table)
body.append(para('Original article',59,page=True,after=180))
body.append(para(eng,66,bold=True,size=16,keep=True,after=200))
body.append(para('Artem S. Yakovlev',72,bold=True,size=12,after=60))
aff_en='Polytechnic College, Yaroslav-the-Wise Novgorod State University, Veliky Novgorod, Russian Federation'
body.append(para(aff_en,73,after=40));body.append(para('Address: 46 Bolshaya Sankt-Peterburgskaya St., Veliky Novgorod, Russian Federation',74,after=40));body.append(para('jackowleffa@yandex.ru',75,after=200))
body.append(para('Abstract',80,bold=True,size=12,keep=True,after=80))
for label,t in en:body.append(abstract_para(label,t,81))
body.append(para('Keywords: SQL, language models, query optimization, MySQL, PostgreSQL, result validation, performance measurement',100,size=10,after=140))
body.append(para('Conflict of interests: The author declares no conflict of interest.',103,size=10,after=80))
content=(TMP/'manuscript.md').read_text(encoding='utf8')
first=True
for block in content.split('\n\n'):
 block=block.strip()
 if not block:continue
 if block.startswith('{{TABLE'):
  table(int(re.search(r'\d+',block).group()));continue
 if block.startswith('#'):
  level=len(block)-len(block.lstrip('#'));p=para(block.lstrip('# ').strip(),113,bold=True,size=14 if level==1 else 12,keep=True,page=first,after=100);first=False
 else:p=para(block,114,after=100)
 body.append(p)
body.append(para('СПИСОК ЛИТЕРАТУРЫ / REFERENCES',124,bold=True,size=12,keep=True,after=120))
for i,t in enumerate(refs,1):body.append(para(f'{i}. {t}',125,size=10,after=70))
body.append(para('Об авторе',156,bold=True,size=14,keep=True,after=100))
body.append(para('Яковлев Артём Сергеевич, студент, '+aff+'. '+address+'. E-mail: jackowleffa@yandex.ru.',157,size=10,after=140))
body.append(para('About the author',165,bold=True,size=14,keep=True,after=100))
body.append(para('Artem S. Yakovlev, student, '+aff_en+'. E-mail: jackowleffa@yandex.ru.',166,size=10,after=100))
body.append(sect)
dest=OUT/'Яковлев — сравнение моделей SQL — СИТИТО.docx'
core=E.fromstring(z.read('docProps/core.xml'))
for el in core:
 if E.QName(el).localname in ['creator','lastModifiedBy']:el.text='Артём Яковлев'
with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as out:
 for item in z.infolist():
  b=z.read(item.filename)
  if item.filename=='word/document.xml':b=E.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
  if item.filename=='docProps/core.xml':b=E.tostring(core,xml_declaration=True,encoding='UTF-8',standalone=True)
  out.writestr(deepcopy(item),b)
with zipfile.ZipFile(dest) as result:
 altered=[n for n in z.namelist() if z.read(n)!=result.read(n)]
assert set(altered)=={'word/document.xml','docProps/core.xml'},altered
(TMP/'artifact.md').write_text(f'''# Template contract
Reference: {REF}; SHA256 {hashlib.sha256(REF.read_bytes()).hexdigest()}. Four rendered reference pages in reference-1.png through reference-4.png inspected.
One A4 section; margins top 1.2506 cm, bottom 1.0001 cm, left 2.5083 cm, right 1.6175 cm. Section properties retained byte structurally unchanged.
Typography cloned from source paragraphs: title 10/66 (TNR 16 bold), author 17/72 (12 bold), affiliation 18/73 (10), abstract 26/81 (10), body 114 (10), heading 113 (14), references 125 (10), author note 157/166 (10).
Slots: Russian and English front matter on separate pages; body starts third page. Blank filler paragraphs replaced by content and explicit spacing. Source licence component retained. Sample references, author, UDC, citation year/volume/issue and editorial dates removed. No ORCID invented. Author approval statement omitted pending review.
New components: five black/white native Word tables with bilingual captions and repeating headers; no figure required for these compact counts. Table 5 reports the frozen Library corpus equivalence check.
Data sources: tables 1-4 from docs/nir/data.json; table 5 from docs/articles/sql_rewrite_validation/library_summary.json, verified against runs/library_evaluation_20261015 and runs/library_evaluation_20261015_repro. Corpus SHA-256 ff7d02331e7c5a4b650eff35742bb7d466753e7a2ed51d59310a6e8c3581ca58; corpus frozen before model responses were collected; execution time not measured in that series.
Preserve-only parts: every ZIP entry except word/document.xml and docProps/core.xml, verified unchanged before Word export. Source untouched. Section count one. Additional pages arise only from new text.
Build modifies copied document XML using cloned source paragraphs; output {dest}.
Pagination from Word COM export to PDF; every page inspected as PNG rendered from that PDF.
''',encoding='utf8')
for lang,a in [('ru',ru),('en',en)]:
 text=' '.join(x+' '+y for x,y in a); print(lang,'words',len(text.split()),'chars',len(text))
print(dest)
print('source sha',hashlib.sha256(raw).hexdigest())



