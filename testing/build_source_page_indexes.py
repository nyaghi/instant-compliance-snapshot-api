"""Offline preparation from retained files. No registry requests or app changes."""
from pathlib import Path
import hashlib,json,re,sys,time
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from deployment.state_snapshots import key,source_name_present
manifest=json.loads((ROOT/'downloadable-state-data.json').read_text())
output={}
for state in ['NH','KY']:
    info=manifest['states'][state]
    pdf=next(a for a in info['assets'] if a['path'].endswith('.pdf'))
    data=next(a for a in info['assets'] if a['path'].endswith('.json'))
    records=json.loads((ROOT/data['path']).read_text());records=records.get('records',[]) if isinstance(records,dict) else records
    known={str(r[0]):str(r[1]) for r in records}
    index={};reader=PdfReader(ROOT/pdf['path']);start=time.perf_counter()
    for n,page in enumerate(reader.pages):
        text=page.extract_text() or '';normalized=key(text)
        candidates=set(re.findall(r'(?<!\d)\d{1,6}(?!\d)',text))&known.keys()
        if '' in known:candidates.add('')
        for ident in candidates:
            if source_name_present(known[ident],text,state):index.setdefault(ident,[]).append(n)
    output[state]={'asset':pdf['path'],'source_sha256':pdf['sha256'],'pages':index,'record_names':known}
    print(json.dumps({'state':state,'pages':len(reader.pages),'indexed_records':len(index),'records':len(known),'seconds':round(time.perf_counter()-start,3)}),flush=True)
(ROOT/'deployment/source-page-indexes.json').write_text(json.dumps(output,separators=(',',':')),encoding='utf-8')
