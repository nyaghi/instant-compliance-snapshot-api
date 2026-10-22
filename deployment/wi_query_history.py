"""Observe existing WI HTTP responses; never issue an additional request."""
import html
import re
from urllib.parse import urlsplit

TABLE='ctl00_cphMainContent_OrgCredentialSearch_gvCredentialSearchResults'
LABEL='Charitable Organization; No filter available (name-matching mode)'
FIELDS=('License Number','Credential Type','Name','Location','Granted Date','Expiration Date')

def visible(source):
    return ' '.join(html.unescape(re.sub(r'<[^>]*>',' ',source)).split())

def result_rows(source,name):
    """Require the echoed submitted name, charity scope and a complete table."""
    if not isinstance(source,str) or len(source)>2000000:return None
    def span(suffix):
        values=re.findall(r'<span\b[^>]*\bid=["\']ctl00_cphMainContent_'+suffix+r'["\'][^>]*>([\s\S]*?)</span>',source,re.I)
        return visible(values[0]) if len(values)==1 else None
    if span('lblSearchParam1')!='Profession : Charitable Organization':return None
    if span('lblSearchParam2')!='Firm Name : '+' '.join(name.split()):return None
    tables=re.findall(r'<table\b[^>]*\bid=["\']'+TABLE+r'["\'][^>]*>([\s\S]*?)</table>',source,re.I)
    if len(tables)!=1:return None
    body=tables[0]
    if re.search(r'<table\b',body,re.I):return None
    parts=re.findall(r'<tr\b[^>]*>([\s\S]*?)</tr>',body,re.I)
    if len(parts)!=len(re.findall(r'<tr\b',body,re.I)):return None
    cells=[[visible(c) for c in re.findall(r'<t[dh]\b[^>]*>([\s\S]*?)</t[dh]>',row,re.I)] for row in parts]
    totals=re.findall(r'Total Search Results\s*:\s*(\d+)',visible(source),re.I)
    if cells==[['There are no query results.']]:
        return [] if not totals or totals==['0'] else None
    if not cells or cells[0]!=['License#','Profession','Name','Location','Granted Date','Expiration Date']:return None
    rows=[]
    for row in cells[1:]:
        if len(row)!=6 or not re.fullmatch(r'\d+-800',row[0]) or row[1]!='Charitable Organization' or not row[2]:return None
        rows.append(dict(zip(FIELDS,row)))
    if not rows or totals!=[str(len(rows))]:return None
    return rows

def read_wi_response(call,request,**kwargs):
    """One original open/read/close; recording failures cannot change its text."""
    from deployment.search_observation import start_transport,received,complete_public_rows,observed_http_call
    from deployment.state_snapshots import CURRENT
    run=CURRENT.get()
    if run is None or run.state!='WI':
        with observed_http_call(call,request,**kwargs) as response:
            return response.read().decode('utf-8',errors='replace')
    receipts=[]
    try:receipts=start_transport(request.full_url,request.data,run=run)
    except Exception:pass
    try:
        with call(request,**kwargs) as response:
            source=response.read().decode('utf-8',errors='replace')
            try:status=response.status;final_url=response.geturl()
            except Exception:status=None;final_url=''
    except BaseException:
        for receipt in receipts:
            try:receipt.incomplete()
            except Exception:pass
        raise
    for receipt in receipts:
        try:
            u=urlsplit(final_url)
            rows=None
            if (type(status) is int and 200<=status<300 and u.scheme=='https' and u.hostname=='apps.dfi.wi.gov'
                and u.path in {'/ice/berg/Registration/OrgCredentialSearchResults.aspx','/ice/berg/Registration/Search.aspx'}
                and receipt.query.get('name')):
                rows=result_rows(source,receipt.query['name'])
            if rows is not None:
                receipt.query['filter_label']=LABEL
                complete_public_rows(receipt,len(rows),rows)
            else:received([receipt],status)
        except Exception:
            try:receipt.incomplete()
            except Exception:pass
    return source
