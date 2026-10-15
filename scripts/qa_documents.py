"""Render every updated PDF and write text/layout checks and contact sheets."""
from pathlib import Path
import json
import sys
import pymupdf as fitz
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'tmp/document_qa'
OUT.mkdir(parents=True, exist_ok=True)
files = list((ROOT/'docs/articles').glob('*.pdf'))
files += [ROOT/'docs/nir/Отчет_о_НИР.pdf', ROOT/'docs/techreport/Технический_отчет.pdf',
          ROOT/'docs/human_study/Задания_для_участников.pdf', ROOT/'docs/talk/Доклад_AI_Database_Optimizer.pdf',
          ROOT/'docs/gigachat/GigaChat_SQL_report.pdf']
files += list((ROOT/'docs/rospatent/out').glob('*.pdf'))
if len(sys.argv) > 1:
    files = [p for p in files if p.stem in sys.argv[1:]]
manifest = []
for path in files:
    doc = fitz.open(path)
    folder = OUT / path.stem
    folder.mkdir(exist_ok=True)
    errors = []
    texts = []
    thumbnails = []
    for i, page in enumerate(doc):
        text = page.get_text()
        texts.append(text)
        if not text.strip(): errors.append(f'page {i+1}: empty text')
        pix = page.get_pixmap(matrix=fitz.Matrix(1.2, 1.2), alpha=False)
        pix.save(str(folder/f'page-{i+1}.png'))
        thumb = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
        thumb.thumbnail((270,360))
        thumbnails.append(thumb)
        for block in page.get_text('blocks'):
            if block[0] < -1 or block[1] < -1 or block[2] > page.rect.width+1 or block[3] > page.rect.height+1:
                errors.append(f'page {i+1}: text outside page')
    for start in range(0,len(thumbnails),12):
        sheet=Image.new('RGB',(1160,1200),'#dddddd')
        draw=ImageDraw.Draw(sheet)
        for j,thumb in enumerate(thumbnails[start:start+12]):
            x=(j%4)*290+10; y=(j//4)*400+25
            sheet.paste(thumb,(x,y)); draw.text((x,y-18),f'Page {start+j+1}',fill='black')
        sheet.save(folder/f'contact-{start//12+1}.jpg')
    (folder/'text.txt').write_text('\n\f\n'.join(texts),encoding='utf-8')
    manifest.append({'file':str(path),'pages':len(doc),'errors':errors,'bytes':path.stat().st_size})
    print(path.stem,len(doc),'pages',len(errors),'flags',flush=True)
if len(sys.argv) > 1 and (OUT/'manifest.json').exists():
    prior = json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    updated = {r['file'] for r in manifest}
    manifest = [r for r in prior if r['file'] not in updated] + manifest
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
