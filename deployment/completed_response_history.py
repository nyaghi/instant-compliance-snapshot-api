"""Attach already-read public rows to their exact request receipt. No I/O.

Only callers that finished reading a source response invoke this module. A
transport success alone, overall Not Registered status, or empty DOM is never
enough to assign zero. Response identities are bounded to the current run.
"""
import json,re,time
from urllib.parse import urlsplit
from deployment.state_snapshots import CURRENT
from deployment.history_returned_rows import returned_record_details

STATES={'CT','NJ','PA','VA','ND','OR','SC'}

def remember(response,receipts,run=None):
    try:
        run=run or CURRENT.get()
        if run is None or run.state not in STATES or not receipts:return
        mapping=getattr(run,'history_response_objects',None)
        if mapping is None:mapping=run.history_response_objects={}
        if len(mapping)<150:mapping[id(response)]=(response,receipts)
    except Exception:pass

def complete_receipts(run,receipts,rows,label):
    if not isinstance(rows,list) or len(rows)>10000:return
    for receipt in receipts:
        entries=[e for e in getattr(run,'search_history_receipts',[]) if e.get('query_id')==receipt.query_id]
        if not entries and not receipt.saved:
            if label:receipt.query['filter_label']=label
            receipt.complete(len(rows),rows=rows)
            continue
        if len(entries)!=1 or entries[0].get('observation_kind')!='transport_response':continue
        entry=entries[0]
        entry.update(outcome='Completed source response',returned_rows=len(rows),completed_at=time.time(),
                     observation_kind='validated_source_rows',**returned_record_details({'rows':rows}))
        if label:entry['query']['filter_label']=label

def pa_rows(data):
    if not isinstance(data,dict) or any(data.get(k) for k in ('error','Error','ErrorMessage')):return
    rows=data.get('Table');totals=data.get('Table1')
    if (not isinstance(rows,list) or not isinstance(totals,list) or len(totals)!=1
        or not isinstance(totals[0],dict)):return
    count=totals[0].get('RESULTCOUNT')
    if type(count) is not int or count!=len(rows):return
    mapping={'EntityName':'Name','PersonId':'ID','CertificateNumber':'Registration Number',
             'StatusName':'Status','ExpDate':'Expiration Date'}
    out=[]
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('EntityName'),str) or not row['EntityName'].strip():return
        out.append({v:row[k] for k,v in mapping.items() if k in row})
    return out

def nj_rows(data):
    if (not isinstance(data,dict) or data.get('Success') is False
        or any(data.get(k) for k in ('Error','error','ErrorMessage','errorMessage'))):return
    rows=data.get('Records');count=data.get('ItemCount')
    if (not isinstance(rows,list) or type(count) is not int or count!=len(rows)
        or data.get('MoreRecords') is not False or data.get('PageNumber')!=1):return
    mapping={'name':'Name','accountnumber':'Registration Number','crsm_filestanding':'Status',
             'crsm_addressline1':'Address','crsm_mailingcity':'City','crsm_mailingstate':'State','crsm_mailingzip':'ZIP'}
    out=[]
    for row in rows:
        attrs=row.get('Attributes') if isinstance(row,dict) else None
        if not isinstance(attrs,list) or any(not isinstance(a,dict) or not isinstance(a.get('Name'),str) for a in attrs):return
        fields={a['Name']:a.get('DisplayValue') for a in attrs}
        if len(fields)!=len(attrs) or not isinstance(fields.get('name'),str) or not fields['name'].strip():return
        out.append({v:fields[k] for k,v in mapping.items() if k in fields})
    return out

def va_rows(data):
    if not isinstance(data,list):return
    out=[]
    for row in data:
        if not isinstance(row,dict) or not isinstance(row.get('name'),str) or not row['name'].strip():return
        out.append({k:row[k] for k in ('name','fullName','primaryName','id','status') if k in row and k!='primaryName'})
    return out

def ct_rows(body):
    # Use only a completed CT result count and its actual licensed table rows.
    from html import unescape
    text=lambda s:re.sub(r'\s+',' ',unescape(re.sub('<[^>]+>',' ',s))).strip()
    if not isinstance(body,str) or re.search('verify you are human|access denied',body,re.I):return
    counts=re.findall(r'Showing\s+(\d+)\s+result',text(body),re.I)
    if len(counts)!=1:return
    rows=[]
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>',body,re.I|re.S):
        if not re.search(r'\bPUBLIC\s+CHARITY\b|\bCHR[.\s-]*\d+',text(row),re.I):continue
        cells=[text(c) for c in re.findall(r'<td\b[^>]*>(.*?)</td>',row,re.I|re.S)]
        if len(cells)==1 and 'forge-card' in row:
            name=re.search(r'<b\b[^>]*class=[\'"][^\'"]*forge-typography--headline6[^\'"]*[\'"][^>]*>(.*?)</b>',row,re.I|re.S)
            if not name or not text(name.group(1)):return
            pairs=re.findall(r'<b\b[^>]*>([^<]*)</b>\s*<p\b[^>]*>(.*?)</p>',row,re.I|re.S)
            fields={text(k):text(v) for k,v in pairs}
            if not re.fullmatch(r'CHR\.\d+',fields.get('Credential','')) or not fields.get('Status'):return
            rows.append({'Name':text(name.group(1)),'Credential':fields['Credential'],
                         'Status':fields['Status'],'City':fields.get('City','')})
            continue
        if len(cells)<4:return
        # Header mapping is intentionally source-derived, never column guesses.
        headers=[]
        for candidate in re.findall(r'<tr\b[^>]*>(.*?)</tr>',body,re.I|re.S):
            h=[text(c) for c in re.findall(r'<th\b[^>]*>(.*?)</th>',candidate,re.I|re.S)]
            if len(h)==len(cells) and any(re.search('name',v,re.I) for v in h):headers=h;break
        if not headers:return
        rows.append(dict(zip(headers,cells)))
    if int(counts[0])!=len(rows):return
    return rows

def nd_rows(data):
    if not isinstance(data,dict) or not isinstance(data.get('rows'),dict) or not isinstance(data.get('template'),list):return
    rows=[]
    for row in data['rows'].values():
        if not isinstance(row,dict) or not isinstance(row.get('TITLE'),list) or not row['TITLE'] or not isinstance(row['TITLE'][0],str) or not row['TITLE'][0].strip() or not row.get('ID'):return
        rows.append({'Name':row['TITLE'][0],'Registration Number':row.get('RECORD_NUM',row['ID']),'Status':row.get('STATUS','')})
    return rows

def sc_rows(body):
    from html import unescape
    if not isinstance(body,str) or re.search('access denied|service unavailable|verify you are human',body,re.I):return
    matches=list(re.finditer(r'CharityInfo\((\d+)\)[^>]*>\s*(.*?)\s*</a>',body,re.I|re.S))
    rows=[{'ID':m[1],'Name':re.sub(r'\s+',' ',unescape(re.sub('<[^>]+>',' ',m[2]))).strip()} for m in matches]
    if any(not r['Name'] for r in rows):return
    text=re.sub('<[^>]+>',' ',body)
    empty=bool(re.search(r'\bNo\s+results\s+found\b',text,re.I))
    if rows and empty:return
    return rows if rows or empty else None

def or_rows(body):
    # The caller already verified that the complete response equals the displayed
    # grid. Read its original cells, including candidates later rejected.
    from html.parser import HTMLParser
    if not isinstance(body,str):return
    class Grid(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True);self.depth=0;self.found=False;self.closed=False;self.records=[];self.row=None;self.cell=None;self.text=[]
        def handle_starttag(self,tag,attrs):
            attrs=dict(attrs)
            if tag=='table':
                if self.depth:self.depth+=1
                elif attrs.get('id')=='grid':self.depth=1;self.found=True
            if self.depth!=1:return
            if tag=='tr':self.row=[]
            if tag in ('th','td') and self.row is not None:self.cell=[tag,attrs.get('class',''),[]]
        def handle_data(self,data):
            self.text.append(data)
            if self.cell is not None:self.cell[2].append(data)
        def handle_endtag(self,tag):
            if self.depth==1:
                if tag in ('th','td') and self.cell is not None:
                    self.row.append((self.cell[0],self.cell[1],' '.join(' '.join(self.cell[2]).split())));self.cell=None
                if tag=='tr' and self.row is not None:self.records.append(self.row);self.row=None
            if tag=='table' and self.depth:
                self.depth-=1
                if not self.depth:self.closed=True
    grid=Grid();grid.feed(body);grid.close()
    if not grid.found:
        return [] if re.search(r'\bno (?:matching )?records? (?:were )?found\b',' '.join(grid.text),re.I) else None
    if not grid.closed or grid.cell is not None or grid.row is not None:return
    header_rows=[r for r in grid.records if r and all(c[0]=='th' for c in r)]
    if len(header_rows)!=1:return
    headers=[c[2] for c in header_rows[0]]
    if not headers or not any('name' in h.lower() for h in headers):return
    rows=[]
    for tr in grid.records:
        if tr==header_rows[0]:continue
        if any('dataTables_empty' in c[1].split() for c in tr):
            if re.search('no data|no records|no matching',' '.join(c[2] for c in tr),re.I):continue
            return
        cells=[c[2] for c in tr if c[0]=='td']
        if len(cells)!=len(headers):return
        rows.append(dict(zip(headers,cells)))
    return rows

def finish(response,data,*,run=None):
    try:
        run=run or CURRENT.get()
        if run is None or run.state not in STATES:return
        pair=getattr(run,'history_response_objects',{}).get(id(response))
        receipts=pair[1] if pair and pair[0] is response else None
        if receipts is None:
            request=getattr(response,'request',None)
            receipts=getattr(run,'search_history_transport_requests',{}).get(request,[])
        if not receipts:return
        url=str(getattr(response,'url','') or getattr(response,'geturl',lambda:'')())
        u=urlsplit(url)
        if any(r.query.get('url')!=u._replace(query='',fragment='').geturl() for r in receipts):return
        if isinstance(data,(str,bytes)) and run.state not in {'CT','OR','SC'}:data=json.loads(data)
        if run.state=='PA' and u.hostname=='www.charities.pa.gov' and u.path.lower().rstrip('/')=='/api/charities/search':
            rows=pa_rows(data);label='Submitted Pennsylvania EIN or name search'
        elif run.state=='NJ' and u.hostname=='charportal.dca.njoag.gov' and u.path.startswith('/_services/entity-grid-data.json/'):
            rows=nj_rows(data);label='Public charity search; completed first-page response'
        elif run.state=='VA' and u.hostname=='vdacs.evokeplatform.com' and u.path=='/api/data/objects/entity/instances':
            rows=va_rows(data);label='Submitted entity filter; rows returned in this response'
        elif run.state=='CT' and u.hostname=='www.elicense.ct.gov' and u.path.lower()=='/lookup/licenselookup.aspx':
            rows=ct_rows(data);label='Organization / DBA name; Public Charity search'
        elif run.state=='ND' and u.hostname=='firststop.sos.nd.gov' and u.path=='/api/Records/charitablesearch':
            rows=nd_rows(data);label='Submitted North Dakota name search; completed response'
        elif run.state=='OR' and u.hostname=='justice.oregon.gov' and u.path.lower().rstrip('/')=='/charities/charity/results':
            rows=or_rows(data);label='Organization name; all rows in completed state response'
        elif run.state=='SC' and u.hostname=='search.scsos.com' and u.path.lower().endswith('/charities'):
            rows=sc_rows(data);label='Contains; rows returned on this result page'
        else:return
        complete_receipts(run,receipts,rows,label)
    except Exception:pass
