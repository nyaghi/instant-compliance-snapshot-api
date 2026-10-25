"""Bind desktop BOSS evidence to the master's already confirmed DC license.

This is an adapter of the existing master-owned evidence transport, not a new
lookup service. It does not select identities or alter status interpretations.
"""
import math,re,time
from datetime import datetime
SEARCH='https://boss.dc.gov/business/business-license-search'
DETAILS={'https://boss.dc.gov/licensing/license-details','https://boss.dc.gov/homepage/license-details'}
LABELS=('Licensee','Trade Name','License Category','License Activity','License Number','Premise Address','License Status','Issue Date','Expiration Date')
def norm(v):return re.sub(r'[^a-z0-9]','',str(v).lower())
def eligible(r):
 return (r.get('state')=='DC' and r.get('success') is True and r.get('status') not in {'Not Registered','Unable to Confirm','Unable to Verify','Site Not Reachable','Needs Review'} and not r.get('confirmation_required') and not r.get('_worker_identity_review'))
def retained_request(run,result):
 from deployment.state_snapshots import DEADLINE
 expected=getattr(run,'dc_boss_selected',None)
 if not eligible(result) or not isinstance(expected,dict):return None
 if str(result.get('matched_registry_identifier'))!=expected['identifier'] or norm(result.get('matched_registry_name'))!=norm(expected['name']):return None
 remaining=min(30.,DEADLINE.get()-time.monotonic()-1)
 if remaining<5:return None
 return dict(state='DC',operation='detail',ein=run.ein,run_id=run.run_id,issued_at=time.time(),expires_at=time.time()+remaining,url=SEARCH,name=expected['name'],identifier=expected['identifier'],raw_status=expected['raw_status'],expiration=expected['expiration'],result_raw_status=result.get('raw_status_text'))
def describe(result):
 d=result.get('_worker_desktop_evidence')
 if not eligible(result) or result.get('evidence_url') or not isinstance(d,dict):return None
 if d.get('state')!='DC' or d.get('operation')!='detail' or d.get('url')!=SEARCH:return None
 if not re.fullmatch(r'\d{5,16}',str(d.get('identifier',''))) or not re.fullmatch(r'[a-f0-9]{32}',str(d.get('run_id',''))):return None
 if not re.fullmatch(r'\d{9}',str(d.get('ein',''))) or d['ein']!=re.sub(r'\D','',str(result.get('ein',''))):return None
 if not isinstance(d.get('name'),str) or not 1<=len(d['name'])<=300 or not isinstance(d.get('raw_status'),str) or not 1<=len(d['raw_status'])<=100:return None
 if str(result.get('matched_registry_identifier'))!=d['identifier'] or norm(result.get('matched_registry_name'))!=norm(d['name']) or result.get('raw_status_text')!=d.get('result_raw_status'):return None
 if any(type(d.get(k)) not in (int,float) or not math.isfinite(d[k]) for k in ('issued_at','expires_at')):return None
 if not 0<d['expires_at']-d['issued_at']<=30.1 or not -5<=time.time()-d['issued_at']<600:return None
 try:datetime.strptime(d['expiration'],'%Y-%m-%d')
 except (KeyError,ValueError,TypeError):return None
 return dict(d)
def fields(url,text,d):
 if url not in DETAILS or not isinstance(text,str) or not 1<=len(text)<=20000:return None
 if re.search(r'user validation required|recaptcha timeout|verify you are human|access denied',text,re.I):return None
 if text.count('License Information')!=1 or text.count('Licensee Information')!=1:return None
 lines=[v.strip() for v in text.split('License Information',1)[1].split('Licensee Information',1)[0].splitlines() if v.strip()]
 if any(lines.count(label)!=1 for label in LABELS):return None
 positions=[lines.index(v) for v in LABELS]
 if positions!=sorted(positions):return None
 f={label:' '.join(lines[positions[i]+1:positions[i+1] if i+1<len(positions) else len(lines)]) for i,label in enumerate(LABELS)}
 if any(not v or v=='N/A' for k,v in f.items() if k not in {'Trade Name','Premise Address'}):return None
 if f['License Number']!=d['identifier'] or norm(f['Licensee'])!=norm(d['name']) or f['License Activity'].lower()!='charitable solicitation' or f['License Status']!=d['raw_status']:return None
 try:
  if datetime.strptime(f['Expiration Date'],'%m/%d/%Y').date().isoformat()!=d['expiration']:return None
  datetime.strptime(f['Issue Date'],'%m/%d/%Y')
 except ValueError:return None
 return f
def validate_completion(result,payload):
 d=describe(result)
 if not d or not isinstance(payload,dict) or payload.get('request')!=d:raise ValueError('DC source binding changed')
 stamp=payload.get('captured_at');text=payload.get('public_text');url=payload.get('url')
 if type(stamp) not in (int,float) or not math.isfinite(stamp) or not d['issued_at']<=stamp<=min(time.time()+5,d['expires_at']):raise ValueError('DC capture outside deadline')
 f=fields(url,text,d)
 if not f or payload.get('source_fields')!=f:raise ValueError('DC selected license changed')
 image=payload.get('image')
 if not isinstance(image,str) or not 1<=len(image)<=4_000_000:raise ValueError('Invalid DC source image')
 return dict(kind='image',state='DC',ein=d['ein'],run_id=d['run_id'],source_url=url,captured_at=stamp,content=image,identifier=d['identifier'],record_name=d['name'],organization_name=result.get('organization_name',''),public_text=text,capture_note='Original BOSS selected-license detail captured in this run. License fields matched the selected record; no status or identity change.')
