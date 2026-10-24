"""Passive AR/WV search receipts, bound to the actual submitted request.

Uses rows already read by the established search path. No browser calls,
requests, matching, retries, waits, screenshot or status decisions.
"""
import re,time
from urllib.parse import urlsplit,parse_qs
from deployment.state_snapshots import CURRENT
from deployment.search_history import SourceQueryReceipt
from deployment.history_returned_rows import returned_record_details

URLS={'WV':'https://erls.wvsos.gov/OnlineCharitiesSearch/Search',
      'AR':'https://sos-corp-search.ark.org/index.php/charity',
      'CT':'https://www.elicense.ct.gov/lookup/licenselookup.aspx',
      'OK':'https://www.sos.ok.gov/corp/charityInquiryFind.aspx',
      'ME':'https://www.pfr.maine.gov/almsonline/almsquery/SearchCompany.aspx'}

class Query:
    def __init__(self,run,name,url):
        self.run=run;self.name=name;self.url=url;self.issued=time.time()
        self.receipts=[];self.done=False;self.rows=[];self.rows_valid=False;self.bad_read=False
        self.pending={id(self):[self]}
        run.search_history_pending=getattr(run,'search_history_pending',[])+[self.pending]
    def incomplete(self):
        if self.done:return
        self.done=True
        if not self.receipts:
            receipt=SourceQueryReceipt(self.run,self.query())
            receipt.issued=self.issued;receipt.incomplete()
    def query(self):
        return {'state':self.run.state,'operation':'search','name':self.name,
                'url':self.url,'source_kind':'state_portal',
                'filter_label':('Charity Name; Type CHARITABLE ORGANIZATIONS; source name comparison not specified'
                                if self.run.state=='WV' else 'Name field; first result page under the existing source policy'
                                if self.run.state=='OK' else getattr(self,'filter_label','Begins With; charity category; rows on this result page')
                                if self.run.state=='ME' else 'Name field; source name comparison not specified')}
    def complete(self,rows):
        if self.done:return
        # A navigation with multiple matching submissions is ambiguous. Keep
        # its separate transport receipts rather than assign one row set twice.
        if len(self.receipts)>1:return
        if self.receipts:
            receipt=self.receipts[0]
            entry=next((e for e in getattr(self.run,'search_history_receipts',[])
                        if e['query_id']==receipt.query_id),None)
            if entry is None and not receipt.saved:
                receipt.query['filter_label']=self.query()['filter_label']
                receipt.complete(len(rows),rows=rows)
                self.done=True;self.pending.clear();return
            if entry is None or entry.get('observation_kind')!='transport_response':return
            entry.update(outcome='Completed source response',returned_rows=len(rows),
                         completed_at=time.time(),observation_kind='validated_source_rows',
                         **returned_record_details({'rows':rows}))
            entry['query']['filter_label']=self.query()['filter_label']
        else:
            receipt=SourceQueryReceipt(self.run,self.query())
            receipt.issued=self.issued;receipt.complete(len(rows),rows=rows)
        self.done=True;self.pending.clear()

def begin_query(state,name,url):
    try:
        run=CURRENT.get()
        if run is None or run.state!=state or URLS.get(state)!=url:return None
        previous=getattr(run,'validated_history_query',None)
        if previous:previous.incomplete()
        query=Query(run,name,url);run.validated_history_query=query
        return query
    except Exception:return None

def bind_transport(run,receipts):
    try:
        active=getattr(run,'validated_history_query',None)
        if active is None or active.done:return
        for receipt in receipts:
            q=receipt.query
            url_matches=q.get('url')==active.url or run.state=='ME' and q.get('url','').lower()==active.url.lower()
            if (q.get('state')==run.state and q.get('name')==active.name
                and url_matches and q.get('operation')=='search'):
                active.receipts.append(receipt)
    except Exception:pass

def finish_me(active,rows,all_pages=False):
    try:
        if active is None or active.run.state!='ME' or not isinstance(rows,list):return
        if any(not isinstance(r,dict) or not r.get('name') or not r.get('number') for r in rows):return
        active.filter_label='Begins With; charity category; '+('all completed result pages' if all_pages else 'rows on this result page')
        active.complete(rows)
    except Exception:pass

def finish_wv(active,body,snapshot,url):
    try:
        if active is None or active.run.state!='WV' or url!=active.url:return
        empty=bool(re.search(r'No records found with your search criteria\.',body,re.I))
        rows=[]
        for record in snapshot:
            if record.get('count',0)<5:continue # table headers/footer
            values=record.get('values')
            if (not isinstance(values,list) or len(values)!=3 or not all(isinstance(v,str) for v in values)
                or not re.fullmatch(r'[A-Z]?\d{1,20}',values[0].strip()) or not values[1].strip()):return
            rows.append(dict(zip(('ID','Name','Status'),values)))
        if empty:
            if rows or re.search(r'records\s+1\s+to\s+[1-9]',body,re.I):return
        else:
            pages=re.findall(r'Page\s+1\s+of\s+1,\s+records\s+1\s+to\s+(\d+)\s+of\s+(\d+)',body,re.I)
            if len(pages)!=1 or not rows or any(int(v)!=len(rows) for v in pages[0]):return
        active.complete(rows)
    except Exception:pass

def _ar():
    run=CURRENT.get()
    query=getattr(run,'validated_history_query',None) if run and run.state=='AR' else None
    return query if query and not query.done else None

def ar_rows_start():
    query=_ar()
    if query:query.rows=[];query.rows_valid=True;query.bad_read=False

def ar_rows_failed(kind='unreadable'):
    query=_ar()
    if query:
        query.rows_valid=False
        if kind!='layout':query.bad_read=True

def ar_row(values):
    query=_ar()
    if query:query.rows.append(dict(zip(('Name','Registration Type','Status','Registration Date'),values)))

def finish_ar(active,body,url,empty):
    try:
        if active is None or active.run.state!='AR' or active.bad_read:return
        u=urlsplit(url)
        if u._replace(query='',fragment='').geturl()!=active.url or parse_qs(u.query).get('name')!=[active.name]:return
        if re.search(r'captcha|verify you are human|request could not be satisfied',body,re.I):return
        if empty:
            if active.rows or not re.search(r'\bNo\s+Results\s+Found\b',body,re.I):return
        elif not active.rows or not active.rows_valid:return
        # The existing collector reads at most 100 rows. Do not call a capped
        # list a complete source count or overlook a visible pagination marker.
        if len(active.rows)>=100 or re.search(r'\b(?:Next\s+Page|Page\s+\d+\s+of\s+[2-9]\d*)\b',body,re.I):return
        active.complete(active.rows)
    except Exception:pass

def finish_ok(active,body,url,rows=None):
    try:
        if active is None or active.run.state!='OK' or url!=active.url:return
        if re.search(r'captcha|verify you are human|access denied',body,re.I):return
        if rows is None:
            if not re.search(r'no records found|no matching|no result',body,re.I):return
            # Do not certify a contradictory page containing a registration.
            if re.search(r'\b\d{10}\b',body):return
            rows=[]
        elif not rows or any(not r.get('Name') or not re.fullmatch(r'\d+',r.get('Registration Number','')) for r in rows):return
        active.complete(rows)
    except Exception:pass

def finish_ct(active,body,url,rows=None):
    try:
        if active is None or active.run.state!='CT' or url!=active.url:return
        if re.search(r'captcha|verify you are human|access denied',body,re.I):return
        counts=re.findall(r'Showing\s+(\d+)\s+result',body,re.I)
        if len(counts)!=1:return
        count=int(counts[0]);records=[]
        for item in rows or []:
            text=item.get('text','')
            match=re.fullmatch(r'(.*?)\s+Credential\s+(CHR\.\d+)\s+Credential Description\s+PUBLIC CHARITY\s+(?:Department of Consumer Protection\s+)?Status\s+(.*?)\s+Status Reason\s+.*',text,re.I)
            if not match or not match[1].strip():return
            records.append({'Name':match[1].strip(),'Credential':match[2],'Status':match[3].strip()})
        if count!=len(records):return
        active.complete(records)
    except Exception:pass
