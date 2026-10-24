"""CharityClarity's search account, kept separate from original state pixels.

No browser/network work occurs here or when either PDF/bundle is downloaded.
Inputs come only from query-ID-validated, cleaner-accepted continuations.
"""
import hashlib,io,json,re,secrets,time,zipfile
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

from deployment.history_returned_rows import returned_record_details,validate_returned_details,drop_returned_details,public_field_column

SCHEMA='cc-search-history-v1'
# Capability boundary, not a claim that every route is instrumented.
from deployment.state_snapshots import OFFICIAL_HOSTS,completed_negative_result
STATES=frozenset(OFFICIAL_HOSTS)
FIELDS={'state','operation','orgName','name','ein','search_mode','identifier','orgID','url','exact_above','source_kind','filter_label'}

def public_query(query,state):
    if not isinstance(query,dict) or query.get('state')!=state:raise ValueError('Wrong query state')
    out={k:v for k,v in query.items() if k in FIELDS}
    if 'exact_above' in out and (state!='NV' or type(out['exact_above']) is not int or out['exact_above']!=20):raise ValueError('Invalid narrowing policy')
    if any(not isinstance(v,str) or len(v)>1000 for k,v in out.items() if k!='exact_above'):raise ValueError('Invalid public query')
    if out.get('source_kind') not in {None,'state_portal','official_dataset'}:raise ValueError('Invalid source kind')
    if state=='NC' and out.get('operation')=='search' and out.get('search_mode') not in {None,'STARTS_WITH','ALL_WORDS','EXACT_MATCH'}:raise ValueError('Unknown NC search mode')
    if 'url' in out:
        from deployment.state_snapshots import public_url
        source=urlsplit(out['url'])
        # This is the public API used by WA's own portal, not an additional
        # screenshot origin. History stores its path only, never credentials.
        if state=='WA' and source.scheme=='https' and source.hostname=='ccfs-api.prod.sos.wa.gov' and not source.username and not source.password and source.port in (None,443) and not source.query and not source.fragment:
            out['url']=source.geturl()
        else:out['url']=public_url(out['url'],state)
    if not any(out.get(k) for k in ('name','orgName','ein','identifier','orgID','url')):raise ValueError('No query identity')
    return out

def complete_receipt(record,pending,evidence,now):
    """Call after the existing schema cleaner; no influence on lookup evidence."""
    if record.get('state') not in STATES or record.get('purpose')!='registration':return {}
    query=public_query(pending['query'],record['state'])
    operation=query.get('operation','detail' if 'identifier' in query or query.get('orgID') else 'search')
    rows=evidence.get('rows') if isinstance(evidence,dict) else None
    total=len(rows) if isinstance(rows,list) else None
    digest=hashlib.sha256(json.dumps(query,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    receipt={'query_id':str(pending['query_id']),'query_sha256':digest,'operation':operation,
             'completed_at':now,'outcome':'Completed source response','returned_rows':total}
    if record['state']=='NV' and operation=='search':
        mode=evidence.get('search_mode')
        broad=evidence.get('broad_total')
        if mode not in {'STARTS_WITH','EXACT_MATCH'}:raise ValueError('NV observed filter not recorded')
        if mode=='EXACT_MATCH' and (query.get('exact_above')!=20 or type(broad) is not int or not 20<broad<=10000):raise ValueError('NV narrowing not recorded')
        if mode=='STARTS_WITH' and broad is not None:raise ValueError('NV contradictory filters')
        receipt['observed_search_mode']=mode
        if broad is not None:receipt['broad_result_count']=broad
    if operation=='search' and total is not None:receipt.update(returned_record_details(evidence))
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
        receipt={'query_id':pending['query_id'],'query':q,'operation':q.get('operation','detail' if 'identifier' in q or q.get('orgID') else 'search'),
                 'issued_at':pending.get('history_issued_at'),'reported_at':now,'completed_at':None,
                 'outcome':'Completion not confirmed','reason':reason,'returned_rows':None}
        entries=record.setdefault('search_failed_receipts',[])
        if not any(r['query_id']==receipt['query_id'] for r in entries):
            if len(entries)<10:entries.append(receipt)
            else:record['search_history_overflow']=True
    except (ValueError,KeyError,TypeError):pass

def reportable_result(result):
    """Report the existing outcome, including an explicitly incomplete check."""
    return (isinstance(result,dict) and isinstance(result.get('status'),str)
            and 1<=len(result['status'])<=100 and type(result.get('success')) is bool)


def needs_search_history(result):
    """User-facing search account is required only for completed negatives."""
    return reportable_result(result) and completed_negative_result(result)


def manifest(record,result,snapshot,now):
    from deployment.state_snapshots import digits
    state=record.get('state');ein=digits(record.get('ein',''))
    if record.get('search_history_overflow'):raise ValueError('Optional history exceeded continuation bound')
    if state not in STATES or result.get('state')!=state or digits(result.get('ein',''))!=ein:raise ValueError('Wrong result binding')
    if not reportable_result(result):raise ValueError('No final result to report')
    if snapshot:
        from deployment.state_snapshots import matching_reference
        if (snapshot.get('ein')!=ein or snapshot.get('state')!=state
            or not re.fullmatch(r'/state-snapshots/[a-f0-9]{64}\.pdf',snapshot.get('url',''))):raise ValueError('Wrong source snapshot binding')
        if completed_negative_result(result):
            if snapshot.get('identifier')!='@completed-search':raise ValueError('No bound negative source snapshot')
        elif (matching_reference(result,[snapshot])!=snapshot
              or snapshot.get('run_id')!=record.get('source_archive_run_id')):
            raise ValueError('No bound selected-record snapshot')
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
        if count is not None and (type(count) is not int or not 0<=count<=10000):raise ValueError('Invalid source row count')
        if receipt.get('observation_kind')=='transport_response':
            if count is not None or receipt.get('outcome')!='Transport response received; source validation not recorded' or type(receipt.get('http_status')) is not int or not 200<=receipt['http_status']<400:raise ValueError('Invalid transport observation')
        if state=='NV' and receipt['operation']=='search':
            mode=receipt.get('observed_search_mode');broad=receipt.get('broad_result_count')
            if mode not in {'STARTS_WITH','EXACT_MATCH'}:raise ValueError('NV filter receipt missing')
            if mode=='EXACT_MATCH' and (query.get('exact_above')!=20 or type(broad) is not int or not 20<broad<=10000):raise ValueError('NV filter receipt changed')
            if mode=='STARTS_WITH' and broad is not None:raise ValueError('NV filter receipt contradicted')
        validate_returned_details(receipt)
        entries.append({**receipt,'sequence':len(entries)+1})
    failed=record.get('search_failed_receipts',[])
    if not isinstance(failed,list) or len(failed)>(150 if record.get('history_order')=='issued-sequence-v1' else 10):raise ValueError('Invalid incomplete attempts')
    for e in failed:
        e=dict(e)
        if (e.get('outcome')!='Completion not confirmed' or e.get('completed_at') is not None
            or e.get('returned_rows') is not None or public_query(e['query'],state)!=e['query']
            or type(e.get('reported_at')) not in (int,float)
            or not record['issued']-1<=e['reported_at']<=now+1):raise ValueError('Invalid failure receipt')
        entries.append(e)
    if not entries or len(entries)>150 or len({e['query_id'] for e in entries})!=len(entries):raise ValueError('Missing or duplicate receipts')
    if record.get('history_order')=='issued-sequence-v1':
        orders=[e.get('source_order') for e in entries]
        if any(type(n) is not int or not 1<=n<=150 for n in orders) or len(set(orders))!=len(orders):raise ValueError('Invalid source request order')
        entries.sort(key=lambda e:e['source_order'])
    else:entries.sort(key=lambda e:e.get('completed_at') or e['reported_at'])
    for i,e in enumerate(entries):e['sequence']=i+1
    name=record.get('organization_name','')
    if not isinstance(name,str) or not 1<=len(name)<=500:raise ValueError('Invalid organization')
    reviewed=record.get('alternate_names',[])
    if not isinstance(reviewed,list) or len(reviewed)>30 or any(not isinstance(n,str) or len(n)>500 for n in reviewed):raise ValueError('Invalid input names')
    return {'schema':SCHEMA,'organization_name':name,'ein':ein,'state':state,
            'run_id':record.setdefault('source_archive_run_id',secrets.token_hex(16)),'started_at':record['issued'],'completed_at':now,
            'result_at_completion':result['status'],'snapshot_url':snapshot.get('url',''),
            'reviewed_names':list(dict.fromkeys([name]+reviewed)),
            'queries':entries,'source_limitations':'When available, the state image contains original source pixels. This separate document is CharityClarity\'s search history, not a state-issued certificate. Recorded searches do not establish an identity match by themselves. Attempts without confirmed completion remain explicitly incomplete.'}

def attach(record,result,store=None,now=None):
    """Optional paired output; preserve every original status/identity field."""
    from deployment import state_snapshots as ss
    data=dict(result)
    if record.get('state') not in STATES or record.get('purpose')!='registration':return data
    if not needs_search_history(result):
        from deployment.identity_evidence import retain
        return retain(record,data,store or ss.STORE)
    store=store or ss.STORE
    if store is None:return data
    try:
        snapshot=ss.matching_reference(result,record.get('source_snapshots',[]))
        doc=manifest(record,result,snapshot or {},time.time() if now is None else now)
        raw=json.dumps(doc,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        if len(raw)>150000 and drop_returned_details(doc):
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
    return datetime.fromtimestamp(value,ZoneInfo('America/New_York')).strftime('%Y-%m-%d %I:%M:%S %p %Z') if value is not None else 'Not recorded'

def query_label(q,receipt=None):
    if q.get('operation')=='detail' or 'identifier' in q or q.get('orgID'):return 'Selected detail: '+(q.get('identifier') or q.get('orgID') or q.get('url',''))
    if q.get('ein'):return 'EIN: '+q['ein']+(' | Name: '+(q.get('name') or q.get('orgName')) if q.get('name') or q.get('orgName') else '')+(' | '+q['filter_label'] if q.get('filter_label') else '')
    name=q.get('orgName') or q.get('name','')
    if q['state']=='GA':return 'Names beginning with "'+name+'" (entered as '+name+'*)'
    if q['state'] not in {'GA','NC'}:
        prefix='Official dataset lookup: ' if q.get('source_kind')=='official_dataset' else ''
        if q['state']=='NV':
            mode=(receipt or {}).get('observed_search_mode')
            if mode=='STARTS_WITH':return prefix+'Name: '+name+' | Starting With'
            if mode=='EXACT_MATCH':return prefix+'Name: '+name+' | Starting With returned '+str(receipt['broad_result_count'])+' rows, then Exact Match'
        return prefix+('Name: '+name+' | '+q.get('filter_label', 'No filter available (name-matching mode)' if q['state']=='AL' else 'Search method not captured'))
    mode={'STARTS_WITH':'Starting With','ALL_WORDS':'All Words','EXACT_MATCH':'Exact'}.get(q.get('search_mode'),'Starting With')
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
    if doc.get('identity_decisions'):
        story.append(Paragraph('User identity decisions',styles['Heading2']))
        for item in doc['identity_decisions']:
            story.append(p(item['name']+' ('+item['identifier']+'): rejected at '+stamp(item['reviewed_at'])))
        story.append(p('The state returned these candidate records; the user rejected their identities. This is not a zero-results state response.'))
    story += [Paragraph('Recorded source requests',styles['Heading2']),p('Completed responses and attempts without confirmed completion are labeled separately. Portal counts show rows returned by the state. Dataset counts show rows matching each name filter in the downloaded state list. Neither count confirms identity. A missing count is not zero.')]
    for e in doc['queries']:
        timing_label='Response received: ' if e.get('observation_kind')=='transport_response' else 'Completed: '
        cells=[[p(str(e['sequence'])+'. '+query_label(e['query'],e)),p(e['outcome'])],[p('Issued: '+stamp(e.get('issued_at'))),p(timing_label+stamp(e['completed_at']))]]
        dataset=e['query'].get('source_kind')=='official_dataset'
        count_label='Dataset rows matching this name: ' if dataset else 'Rows returned: '
        count_value=str(e['returned_rows']) if e.get('returned_rows') is not None else 'not captured'
        is_search=e['operation']=='search'
        if is_search:cells.append([p(count_label+count_value),p('Query receipt: '+e['query_id'])])
        else:cells.append([p('Opened an existing record; this was not another name search.'),p('Query receipt: '+e['query_id'])])
        if e.get('reason'):cells.append([p('Incomplete: '+e['reason']),p('Reported: '+stamp(e['reported_at']))])
        table=Table(cells,colWidths=[280,230],hAlign='LEFT');table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf3f7')),('BOX',(0,0),(-1,-1),.4,colors.HexColor('#ccd6df')),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8)]))
        story += [KeepTogether([table,Spacer(1,10)])]
        if is_search and e.get('returned_rows',0):
            story.append(p('Returned source records (not confirmed identity matches):'))
            records=e.get('returned_records')
            if records is None:story.append(p('Returned-record details were not captured in this saved history.'))
            else:
                if records:
                    rows=[[p('Record / organization'),p('Status and dates'),p('Address')]]
                    for record in records:
                        groups=[['Record '+str(record['row_number'])],[],[]]
                        for label,value in record['fields']:
                            key=re.sub(r'[^a-z0-9]','',label.casefold())
                            column=public_field_column(label)
                            groups[column].append(label+': '+(value if value else '(blank in source)'))
                        rows.append([Paragraph('<br/>'.join(escape(x) for x in group) if group else 'Not captured',styles['CCSmall']) for group in groups])
                    details=Table(rows,colWidths=[185,135,190],hAlign='LEFT',repeatRows=1)
                    details.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf3f7')),('GRID',(0,0),(-1,-1),.4,colors.HexColor('#ccd6df')),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
                    story += [details,Spacer(1,8)]
                if e.get('returned_records_not_listed'):story.append(p(str(e['returned_records_not_listed'])+' returned records are not listed: supported field or size limit.'))
    story += [Paragraph('Names supplied to CharityClarity',styles['Heading2']),p('These names were supplied for identity and search planning; they are not state registration matches. This list does not claim that each name was searched literally. The actual recorded requests are listed above.')]
    for n in doc['reviewed_names']:story.append(p(n))
    limits=[Paragraph('Evidence limits',styles['Heading2'])]
    if not doc.get('snapshot_url'):limits.append(p('Original state-page snapshot unavailable for this run. This search history does not replace the missing original image.'))
    limits.append(p(doc['source_limitations']))
    story += [Spacer(1,8),KeepTogether(limits)]
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
            body=render_pdf(doc);mime='application/pdf'
            if pdf is None:store.cache_pdf(match[1],body)
    except Exception:handler._send_json(503,{'error':'Saved evidence is unavailable. No registry search was run.'});return
    handler.send_response(200)
    for k,v in [('Content-Type',mime),('Content-Length',str(len(body))),('Content-Disposition',('inline' if mime=='application/pdf' else 'attachment')+'; filename="'+doc['state']+'-'+match[2]+'"'),('Cache-Control','no-store' if mime=='application/pdf' else 'private, max-age=86400'),('X-Content-Type-Options','nosniff')]:handler.send_header(k,v)
    handler.end_headers()
    if include_body:handler.wfile.write(body)


class SourceQueryReceipt:
    """Bounded observation of an existing source operation; performs no I/O."""
    def __init__(self,run,query):
        self.run=run;self.query=public_query(query,run.state)
        run.search_history_sequence=getattr(run,'search_history_sequence',0)+1
        self.sequence=run.search_history_sequence
        self.issued=time.time();self.query_id=secrets.token_hex(12);self.saved=False
    def complete(self,row_count=None,rows=None,headers=None):
        if row_count is not None and (type(row_count) is not int or not 0<=row_count<=10000):
            self.run.search_history_overflow=True;return
        details=returned_record_details({'rows':rows,'headers':headers}) if isinstance(rows,list) and row_count==len(rows) else {}
        self._save('Completed official dataset evaluation' if self.query.get('source_kind')=='official_dataset' else 'Completed source response',time.time(),row_count,**details)
    def received(self,status):
        self._save('Transport response received; source validation not recorded',time.time(),None,observation_kind='transport_response',http_status=status)
    def incomplete(self):
        self._save('Completion not confirmed',None,None)
    def _save(self,outcome,completed,count,**extra):
        if self.saved:return
        self.saved=True
        entries=getattr(self.run,'search_history_receipts',None)
        if entries is None:entries=self.run.search_history_receipts=[]
        if len(entries)>=150:
            self.run.search_history_overflow=True;return
        entries.append({'query':self.query,'query_id':self.query_id,'source_order':self.sequence,
            'issued_at':self.issued,'completed_at':completed,'reported_at':time.time(),
            'outcome':outcome,'returned_rows':count,**extra})

def begin_source_query(state,name,filter_label,source_url='',source_kind='state_portal'):
    """Called at the existing source operation, never from a planned-name list."""
    from deployment.state_snapshots import CURRENT
    run=CURRENT.get()
    if not run or run.state!=state:return None
    try:
        query={'state':state,'operation':'search','name':name,
               'filter_label':filter_label,'source_kind':source_kind}
        if source_url:query['url']=source_url
        return SourceQueryReceipt(run,query)
    except (ValueError,TypeError,KeyError):
        run.search_history_overflow=True;return None

def finish_worker_history(run,result):
    """Private child output only; the supervisor owns persistent storage."""
    for pending in getattr(run,'search_history_pending',[]):
        for receipts in pending.values():
            for receipt in receipts:receipt.incomplete()
        pending.clear()
    data=dict(result);entries=getattr(run,'search_history_receipts',[])
    from deployment.identity_evidence import has_review
    if not needs_search_history(data) and not has_review(data):return data
    if getattr(run,'search_history_overflow',False):
        data['search_history_capture']='unavailable';return data
    if not entries:return data
    issued=min(e['issued_at'] for e in entries)
    record={'state':run.state,'ein':run.ein,'organization_name':run.name,
        'purpose':'registration','issued':issued,'alternate_names':[n for n in dict.fromkeys(getattr(run,'known_names',[])) if n!=run.name],
        'source_archive_run_id':run.run_id,'history_order':'issued-sequence-v1','completed':[],'search_failed_receipts':[]}
    for entry in entries:
        entry=dict(entry);query=entry.pop('query')
        if entry['completed_at'] is not None:
            entry.pop('reported_at',None)
            entry['operation']=query['operation']
            entry['query_sha256']=hashlib.sha256(json.dumps(query,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            record['completed'].append({'query':query,'search_receipt':entry})
        else:
            entry.update(query=query,operation=query['operation'],reason='SOURCE_RETRIEVAL_INCOMPLETE')
            record['search_failed_receipts'].append(entry)
    # No private identity tokens, credentials, source bodies or page images.
    if len(json.dumps(record).encode())>150000:drop_returned_details(record)
    if len(json.dumps(record).encode())>150000:
        data['search_history_capture']='unavailable';return data
    data['_worker_search_history']=record
    return data

def persist_worker_history(result,job,record,refs,store=None):
    """Supervisor-only pairing; no source request occurs on report download."""
    from deployment.state_snapshots import digits
    data=dict(result)
    if not record:return data
    if (not isinstance(record,dict) or record.get('state')!=job.get('state')
        or record.get('state')!=data.get('state')
        or digits(record.get('ein'))!=digits(job.get('payload',{}).get('ein'))
        or digits(record.get('ein'))!=digits(data.get('ein'))):
        data['search_history_capture']='unavailable';return data
    record={**record,'source_snapshots':refs}
    return attach(record,data,store)
