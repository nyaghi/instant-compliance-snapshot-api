"""Bounded original-list evidence only after a selected MD detail access failure."""
import re,time
from urllib.parse import urlsplit,urlencode

LIST='https://onestop.md.gov/list_views/62f3e1797f7e3200016a3dab'
FIELD='a87e8739-62de-600d-728c-6300bf865f9e'
READ="""()=>{
 const tables=[...document.querySelectorAll('[role="table"],table')];
 const rows=tables.length===1?[...tables[0].querySelectorAll('[role="row"],tr')].filter(r=>r.querySelector('[role="cell"],td')):[];
 const norm=x=>(x||'').trim();
 return {url:location.href,criterion:document.querySelector('#filter-"""+FIELD+"""')?.value,
  count:[...document.querySelectorAll('[role="status"]')].map(e=>e.innerText).join(' '),
  text:document.body.innerText,rows:rows.map(r=>{
   const cell=r.querySelector('[role="cell"],td'),links=[...cell.querySelectorAll('a')];
   const fields={};for(const p of r.querySelectorAll('p')){const labels=p.querySelectorAll('strong');if(labels.length===1){const k=norm(labels[0].textContent).replace(/:$/,'');if(k in fields)fields[k]=null;else fields[k]=norm(p.textContent.slice(labels[0].textContent.length));}}
   return {links:links.map(a=>({name:norm(a.innerText),url:a.href})),fields};})};
}"""
def norm(s):return re.sub(r'[^a-z0-9]','',str(s).lower())
def bound(view,run,result,hint,url):
 try:
  rows=view['rows'];text=view['text'];criterion=run.ein[:2]+'-'+run.ein[2:]
  if (view['url']!=url or view['criterion']!=criterion or len(rows)!=1
      or not re.search(r'\b1 record\b',view['count'])
      or re.search(r'Loading\.\.\.|verify you are human|user validation required|access denied|just a moment',text,re.I)):return False
  row=rows[0];links=row['links'];f=row['fields'];target=urlsplit(hint['url'])
  return (len(links)==1 and norm(links[0]['name'])==norm(result['matched_registry_name'])
   and urlsplit(links[0]['url']).scheme=='https' and urlsplit(links[0]['url']).netloc=='onestop.md.gov'
   and urlsplit(links[0]['url']).path==target.path
   and re.sub(r'\D','',f.get('Charity EIN') or '')==run.ein
   and f.get('Charity ID')==str(result['matched_registry_identifier'])
   and (f.get('Registration Status') or '').casefold()==hint['source_fields']['status'].casefold())
 except (KeyError,TypeError,ValueError):return False

def capture(run,result,hint,context,stop):
 if (run.state!='MD' or result.get('state')!='MD' or not result.get('success')
     or re.sub(r'\D','',str(result.get('ein','')))!=run.ein
     or result.get('source_url')!=LIST or len(run.ein)!=9 or not hint.get('source_fields',{}).get('status')):return
 u=urlsplit(hint.get('url',''))
 if (u.scheme!='https' or u.netloc!='onestop.md.gov' or u.query or u.fragment
     or not re.fullmatch(r'/detail_views/62f3e17b7f7e3200016a4b6c/entry/[a-f0-9]{24}',u.path)):return
 start=time.monotonic();stop=min(stop,start+6);page=None
 fact={'adapter':'MD-selected-listing-after-detail-failure','outcome':'not_started','capture_ms':0};run.visual_adapter_facts.append(fact)
 def timeout(reserve=0,cap=6):
  left=stop-time.monotonic()-reserve
  if left<=0:raise TimeoutError('MD_listing_capture_deadline')
  return max(1,int(min(cap,left)*1000))
 try:
  timeout(1);page=context.new_page();page.set_extra_http_headers({});page.set_viewport_size({'width':1600,'height':1100})
  url=LIST+'?'+urlencode({FIELD:run.ein[:2]+'-'+run.ein[2:]})
  response=page.goto(url,wait_until='domcontentloaded',timeout=timeout(1))
  if response is None or response.status!=200 or page.url!=url:fact['outcome']='listing_navigation_rejected';return
  page.locator('[role="status"]').filter(has_text=re.compile(r'\b1 record\b')).wait_for(state='visible',timeout=timeout(1))
  view=page.evaluate(READ)
  if not bound(view,run,result,hint,url):fact['outcome']='listing_not_bound';return
  dismiss=page.get_by_role('button',name='Dismiss alert.',exact=True)
  if dismiss.count()==1 and dismiss.is_visible():dismiss.click(timeout=timeout(.7,.4));dismiss.wait_for(state='hidden',timeout=timeout(.7,.5))
  before=page.evaluate(READ)
  if not bound(before,run,result,hint,url):fact['outcome']='listing_changed_before_capture';return
  begin=time.perf_counter();raw=page.screenshot(type='jpeg',quality=80,full_page=True,timeout=timeout(.3,1.5));fact['capture_ms']=(time.perf_counter()-begin)*1000
  after=page.evaluate(READ);timeout()
  if before!=after or not bound(after,run,result,hint,url):fact['outcome']='listing_changed_during_capture';return
  count=len(run.documents)
  run.document(url,raw,'image',before['text'][:20000],note='Original official Maryland EIN-filtered listing. The selected detail page was unavailable; this listing independently matches its name, EIN, charity ID and registration status.')
  fact['outcome']='captured' if len(run.documents)>count else 'archive_rejected'
 except Exception as exc:fact.update(outcome='listing_unavailable',error_type=type(exc).__name__,error_summary=str(exc).splitlines()[0][:180])
 finally:
  run.capture_ms+=fact['capture_ms'];fact['total_ms']=(time.monotonic()-start)*1000
  if page is not None:
   try:page.close()
   except Exception:fact['page_close_error']=True
