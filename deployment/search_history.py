"""CharityClarity's search account, kept separate from original state pixels.

No browser/network work occurs here or when either PDF/bundle is downloaded.
Inputs come only from query-ID-validated, cleaner-accepted continuations.
"""
import hashlib,io,json,re,secrets,time,zipfile
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

SCHEMA='cc-search-history-v1'
STATES={'GA','NC'}  # First focused integration; other states are not claimed.
FIELDS={'state','operation','orgName','name','ein','search_mode','identifier','orgID','url'}

def public_query(query,state):
    if not isinstance(query,dict) or query.get('state')!=state:raise ValueError('Wrong query state')
    out={k:v for k,v in query.items() if k in FIELDS}
    if any(not isinstance(v,str) or len(v)>1000 for v in out.values()):raise ValueError('Invalid public query')
    if state=='NC' and out.get('operation')=='search' and out.get('search_mode') not in {None,'STARTS_WITH','ALL_WORDS','EXACT_MATCH'}:raise ValueError('Unknown NC search mode')
    if 'url' in out:
        from deployment.state_snapshots import public_url
        out['url']=public_url(out['url'],state)
    if not any(out.get(k) for k in ('name','orgName','ein','identifier','orgID','url')):raise ValueError('No query identity')
    return out

def complete_receipt(record,pending,evidence,now):
    """Call after the existing schema cleaner; no influence on lookup evidence."""
    if record.get('state') not in STATES or record.get('purpose')!='registration':return {}
    query=public_query(pending['query'],record['state'])
    operation=query.get('operation','detail' if 'identifier' in query else 'search')
    rows=evidence.get('rows') if isinstance(evidence,dict) else None
    total=len(rows) if isinstance(rows,list) else None
    digest=hashlib.sha256(json.dumps(query,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    receipt={'query_id':str(pending['query_id']),'query_sha256':digest,'operation':operation,
             'completed_at':now,'outcome':'Completed source response','returned_rows':total}
    issued=pending.get('history_issued_at')
    if isinstance(issued,(int,float)) and issued<=now:receipt['issued_at']=issued
    return {'search_receipt':receipt}

def safe_complete_receipt(record,pending,evidence,now):
    try:return complete_receipt(record,pending,evidence,now)
    except (ValueError,KeyError,TypeError):return {}

def discard_optional(record):
    """Original source evidence and token capacity always take priority."""
    present=record.pop('search_failed_receipts',None) is not None
    for item in record.get('completed',[]):present=item.pop('search_receipt',None) is not None or present
    if record.get('pending'):present=record['pending'].pop('history_issued_at',None) is not None or present
    if present:record['search_history_overflow']=True
    return present

def mark_issued(record,response,now):
    if record.get('state') in STATES and record.get('purpose')=='registration' and response.get('phase')=='search':
        record['pending']['history_issued_at']=now

def failed_receipt(record,payload,now):
    pending=record.get('pending')
    if record.get('state') not in STATES or record.get('purpose')!='registration' or not pending or payload.get('query_id')!=pending.get('query_id'):return
    try:
        q=public_query(pending['query'],record['state']);reason=payload.get('reason','')
        reason=reason if isinstance(reason,str) and re.fullmatch(r'[A-Z][A-Z0-9_]{1,100}',reason) else 'SOURCE_RETRIEVAL_INCOMPLETE'
        receipt={'query_id':pending['query_id'],'query':q,'operation':q.get('operation','detail' if 'identifier' in q else 'search'),
                 'issued_at':pending.get('history_issued_at'),'reported_at':now,'completed_at':None,
                 'outcome':'Completion not confirmed','reason':reason,'returned_rows':None}
        entries=record.setdefault('search_failed_receipts',[])
        if not any(r['query_id']==receipt['query_id'] for r in entries):
            if len(entries)<10:entries.append(receipt)
            else:record['search_history_overflow']=True
    except (ValueError,KeyError,TypeError):pass

def manifest(record,result,snapshot,now):
    from deployment.state_snapshots import digits
    state=record.get('state');ein=digits(record.get('ein',''))
    if record.get('search_history_overflow'):raise ValueError('Optional history exceeded continuation bound')
    if state not in STATES or result.get('state')!=state or digits(result.get('ein',''))!=ein:raise ValueError('Wrong result binding')
    if result.get('status')!='Not Registered' or result.get('success') is not True:raise ValueError('Not a completed negative result')
    if snapshot and (snapshot.get('ein')!=ein or snapshot.get('state')!=state or snapshot.get('identifier')!='@completed-search'
        or not re.fullmatch(r'/state-snapshots/[a-f0-9]{64}\.pdf',snapshot.get('url',''))):raise ValueError('No bound negative source snapshot')
    entries=[]
    for item in record.get('completed',[]):
        receipt=item.get('search_receipt')
        if not receipt:raise ValueError('This older run has no recorded search receipt')
        receipt=dict(receipt);query=public_query(item['query'],state)
        digest=hashlib.sha256(json.dumps(query,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if receipt.pop('query_sha256',None)!=digest or receipt.get('operation') not in {'search','detail'}:raise ValueError('Receipt query changed')
        receipt['query']=query
        stamp=receipt.get('completed_at');issued=receipt.get('issued_at')
        if type(stamp) not in (float,int) or not record['issued']-1<=stamp<=now+1:raise ValueError('Receipt clock changed')
        if issued is not None and (type(issued) not in (float,int) or not record['issued']-1<=issued<=stamp):raise ValueError('Invalid issue time')
        count=receipt.get('returned_rows')
        if count is not None and (type(count) is not int or not 0<=count<=1000):raise ValueError('Invalid source row count')
        entries.append({**receipt,'sequence':len(entries)+1})
    failed=record.get('search_failed_receipts',[])
    if not isinstance(failed,list) or len(failed)>10:raise ValueError('Invalid incomplete attempts')
    for e in failed:
        e=dict(e)
        if (e.get('outcome')!='Completion not confirmed' or e.get('completed_at') is not None
            or e.get('returned_rows') is not None or public_query(e['query'],state)!=e['query']
            or type(e.get('reported_at')) not in (int,float)
            or not record['issued']-1<=e['reported_at']<=now+1):raise ValueError('Invalid failure receipt')
        entries.append(e)
    if not entries or len(entries)>150 or len({e['query_id'] for e in entries})!=len(entries):raise ValueError('Missing or duplicate receipts')
    entries.sort(key=lambda e:e.get('completed_at') or e['reported_at'])
    for i,e in enumerate(entries):e['sequence']=i+1
    name=record.get('organization_name','')
    if not isinstance(name,str) or not 1<=len(name)<=500:raise ValueError('Invalid organization')
    reviewed=record.get('alternate_names',[])
    if not isinstance(reviewed,list) or len(reviewed)>30 or any(not isinstance(n,str) or len(n)>500 for n in reviewed):raise ValueError('Invalid input names')
    return {'schema':SCHEMA,'organization_name':name,'ein':ein,'state':state,
            'run_id':record.setdefault('source_archive_run_id',secrets.token_hex(16)),'started_at':record['issued'],'completed_at':now,
            'result_at_completion':result['status'],'snapshot_url':snapshot.get('url',''),
            'reviewed_names':list(dict.fromkeys([name]+reviewed)),
            'queries':entries,'source_limitations':'When available, the state image contains original source pixels. This separate document is CharityClarity\'s search history, not a state-issued certificate. A completed negative search does not prove that an organization was never registered.'}

def attach(record,result,store=None,now=None):
    """Optional paired output; preserve every original status/identity field."""
    from deployment import state_snapshots as ss
    data=dict(result)
    if record.get('state') not in STATES or record.get('purpose')!='registration' or result.get('status')!='Not Registered' or result.get('success') is not True:return data
    store=store or ss.STORE
    if store is None:return data
    try:
        snapshot=ss.matching_reference(result,record.get('source_snapshots',[]))
        doc=manifest(record,result,snapshot or {},time.time() if now is None else now)
        raw=json.dumps(doc,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        if len(raw)>150000:raise ValueError('History exceeds bound')
        meta={'kind':'search_history','state':doc['state'],'ein':doc['ein'],'run_id':doc['run_id'],
              'source_sha256':hashlib.sha256(raw).hexdigest(),'captured_at':doc['completed_at']}
        ident=store.save(meta,raw)
        data['search_history_url']='/state-evidence/'+ident+'/search-history.pdf'
        if doc['snapshot_url']:data['evidence_bundle_url']='/state-evidence/'+ident+'/evidence.zip'
        else:data['search_history_capture']='saved_without_state_snapshot'
    except Exception:
        data['search_history_capture']='unavailable'
    return data

def loaded(ident,store):
    if not re.fullmatch(r'[a-f0-9]{64}',ident):return None
    item=store.load(ident)
    if item is None:return None
    meta,raw,cached=item
    if meta.get('kind')!='search_history' or hashlib.sha256(raw).hexdigest()!=meta.get('source_sha256'):raise ValueError('History integrity failed')
    doc=json.loads(raw)
    if doc.get('schema')!=SCHEMA or any(doc.get(k)!=meta.get(k) for k in ('ein','state','run_id')):raise ValueError('History binding failed')
    return meta,doc,cached

def stamp(value):
    return datetime.fromtimestamp(value,timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC') if value is not None else 'Not recorded'

def query_label(q):
    if q.get('operation')=='detail' or 'identifier' in q:return 'Selected detail: '+(q.get('identifier') or q.get('url',''))
    if q.get('ein'):return 'EIN: '+q['ein']
    name=q.get('orgName') or q.get('name','')
    mode='Prefix wildcard (*)' if q['state']=='GA' else {'STARTS_WITH':'Starting With','ALL_WORDS':'All Words','EXACT_MATCH':'Exact'}.get(q.get('search_mode'),'Starting With')
    return name+' | '+mode

def render_pdf(doc,asset_root=None):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,KeepTogether
    out=io.BytesIO();styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='CCSmall',fontName='Helvetica',fontSize=8,leading=11,textColor=colors.HexColor('#334155'),spaceAfter=5))
    styles.add(ParagraphStyle(name='CCBody',fontName='Helvetica',fontSize=9,leading=13,spaceAfter=7))
    root=Path(asset_root) if asset_root else Path(__file__).resolve().parents[1]
    story=[];logo=root/'report-assets/compliance-express.png'
    if logo.exists():
        from PIL import Image as PixelImage
        with PixelImage.open(logo) as pixels:width,height=pixels.size
        im=Image(str(logo),width=140,height=140*height/width);im.hAlign='LEFT';story += [im,Spacer(1,12)]
    story += [Paragraph('CharityClarity Search History',styles['Title']),Paragraph('Generated by CharityClarity - separate from the original state-page snapshot.',styles['CCSmall'])]
    p=lambda s:Paragraph(escape(str(s)),styles['CCBody'])
    story += [p(doc['organization_name']),p('EIN '+doc['ein'][:2]+'-'+doc['ein'][2:]+' | State '+doc['state']+' | Result at completion: '+doc['result_at_completion']),p('Run '+doc['run_id']),p('Started '+stamp(doc['started_at'])+' | Completed '+stamp(doc['completed_at'])),Spacer(1,7)]
    story += [Paragraph('Recorded source requests',styles['Heading2']),p('Completed responses and attempts without confirmed completion are labeled separately. Row counts are the rows returned to CharityClarity before identity evaluation. An unrelated record does not establish a match.')]
    for e in doc['queries']:
        cells=[[p(str(e['sequence'])+'. '+query_label(e['query'])),p(e['outcome'])],[p('Issued: '+stamp(e.get('issued_at'))),p('Completed: '+stamp(e['completed_at']))]]
        if e.get('returned_rows') is not None:cells.append([p('Rows returned: '+str(e['returned_rows'])),p('Query receipt: '+e['query_id'])])
        if e.get('reason'):cells.append([p('Incomplete: '+e['reason']),p('Reported: '+stamp(e['reported_at']))])
        table=Table(cells,colWidths=[280,230],hAlign='LEFT');table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf3f7')),('BOX',(0,0),(-1,-1),.4,colors.HexColor('#ccd6df')),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8)]))
        story += [KeepTogether([table,Spacer(1,10)])]
    story += [Paragraph('Reviewed input names',styles['Heading2']),p('These were inputs to the search plan. This list does not claim that each name was searched literally; the actual requests are listed above.')]
    for n in doc['reviewed_names']:story.append(p(n))
    story += [Spacer(1,8),Paragraph('Evidence limits',styles['Heading2'])]
    if not doc.get('snapshot_url'):story.append(p('Original state-page snapshot unavailable for this run. This search history does not replace the missing original image.'))
    story.append(p(doc['source_limitations']))
    def footer(c,d):
        c.saveState();c.setFont('Helvetica',8);c.setFillColor(colors.HexColor('#475569'))
        c.drawString(42,25,'Compliance Express | www.compliance-express.com | info@compliance-express.com');c.drawRightString(570,25,str(d.page));c.restoreState()
    SimpleDocTemplate(out,pagesize=(612,792),leftMargin=42,rightMargin=42,topMargin=35,bottomMargin=45,title='CharityClarity Search History',author='Compliance Express').build(story,onFirstPage=footer,onLaterPages=footer)
    return out.getvalue()

def bundle(ident,store):
    from deployment import state_snapshots as ss
    item=loaded(ident,store)
    if item is None:return None
    meta,doc,pdf=item
    if not doc.get('snapshot_url'):raise ValueError('Original state-page snapshot unavailable')
    sid=doc['snapshot_url'].split('/')[-1][:-4];snapshot=store.load(sid)
    if snapshot is None:raise ValueError('Original snapshot unavailable')
    source_meta,raw,_=snapshot
    if any(source_meta.get(k)!=doc[k] for k in ('ein','state','run_id')):raise ValueError('Paired evidence belongs to another run')
    _,source_pdf=ss.saved_pdf(sid,store)
    if pdf is None:pdf=render_pdf(doc);store.cache_pdf(ident,pdf)
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(doc['state']+'-State-Snapshot.pdf',source_pdf)
        z.writestr(doc['state']+'-CharityClarity-Search-History.pdf',pdf)
    return output.getvalue()

def serve(handler,include_body=True,store=None):
    from deployment import state_snapshots as ss
    match=re.fullmatch(r'/state-evidence/([a-f0-9]{64})/(search-history\.pdf|evidence\.zip)',urlsplit(handler.path).path)
    if not match:handler._send_json(404,{'error':'Saved evidence not found.'});return
    store=store or ss.STORE
    try:
        if store is None:raise ValueError('Archive unavailable')
        item=loaded(match[1],store)
        if item is None:handler._send_json(404,{'error':'Saved evidence not found.'});return
        meta,doc,pdf=item
        if match[2]=='evidence.zip':body=bundle(match[1],store);mime='application/zip'
        else:
            body=pdf or render_pdf(doc);mime='application/pdf'
            if pdf is None:store.cache_pdf(match[1],body)
    except Exception:handler._send_json(503,{'error':'Saved evidence is unavailable. No registry search was run.'});return
    handler.send_response(200)
    for k,v in [('Content-Type',mime),('Content-Length',str(len(body))),('Content-Disposition','attachment; filename="'+doc['state']+'-'+match[2]+'"'),('Cache-Control','private, max-age=86400'),('X-Content-Type-Options','nosniff')]:handler.send_header(k,v)
    handler.end_headers()
    if include_body:handler.wfile.write(body)
