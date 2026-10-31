"""Original verified FDACS response retained privately for its own lookup image.

No generated record markup, altered source body, extra registry query or status
interpretation. Browser caching of the exact response removes a second visit.
"""
import hashlib
import re
import time

URL='https://csapp.fdacs.gov/CSPublicApp/BusinessSearch/BusinessSearch.aspx'
NOTE='Original verified FDACS response from this lookup, rendered without changing its source HTML.'
FIELDS=('state','ein','success','source_url','matched_registry_name','matched_registry_identifier','status','raw_status_text')


def binding(result):
    get=result.get if isinstance(result,dict) else lambda k:getattr(result,k,None)
    return tuple(get(k) for k in FIELDS)


def current():
    from deployment.state_snapshots import CURRENT
    run=CURRENT.get()
    return run if run is not None and run.state=='FL' else None


def remember_response(master,source,query):
    run=current()
    if run is None:return False
    run.fl_response_candidate=None
    run.fl_response_proof=None
    run.fl_response_images={}
    if (not isinstance(source,str) or not 0<len(source.encode())<=2_000_000
            or not re.search(r'</html>\s*$',source,re.I)
            or query!=master.canonical_name_punctuation(run.name)):return False
    run.fl_response_candidate={'run_id':run.run_id,'query':query,'html':source,
                               'sha256':hashlib.sha256(source.encode()).hexdigest()}
    return True


def bind_lookup(master,result):
    run=current();source=getattr(run,'fl_response_candidate',None)
    if not run or not source or source['run_id']!=run.run_id:return False
    b=binding(result)
    if (getattr(result,'_cc_fl_business_source_verified',False) is not True
            or b[0]!='FL' or re.sub(r'\D','',str(b[1]))!=run.ein or b[2] is not True
            or b[3]!=URL or not b[4] or not re.fullmatch(r'CH\d+',str(b[5]))
            or b[6] in {'Not Registered','Unknown','Unable to Confirm','Site Not Reachable'}):return False
    rows=master.fl_business_candidate_rows(source['html'])
    selected=[row for row in rows if row['business_evidence']['identifier']==b[5]
              and row['business_evidence']['name']==b[4]]
    if (len(selected)!=1 or getattr(result,'_cc_registration_date_evidence',None)
            !=selected[0]['business_evidence']):return False
    # Parser/matcher selected the record before this hook; this only binds it.
    run.fl_response_proof={**source,'lookup_binding':b,'capture_status':master.public_status(result),
                           'public_binding':None,'selected':selected[0]}
    return True


def capture_bound(run,result):
    p=getattr(run,'fl_response_proof',None)
    if (not p or p['run_id']!=run.run_id or run.state!='FL'
            or re.sub(r'\D','',str(p['lookup_binding'][1]))!=run.ein):return None
    b=p['lookup_binding']
    if (not isinstance(result,dict) or any(result.get(FIELDS[i])!=b[i] for i in (0,1,2,3,4,5))
            or result.get('status')!=p['capture_status']
            or hashlib.sha256(p['html'].encode()).hexdigest()!=p['sha256']):return None
    return p


def seal_public_result(source_result,data):
    run=current();p=getattr(run,'fl_response_proof',None)
    if (not p or p['run_id']!=run.run_id or p['public_binding'] is not None
            or binding(source_result)!=p['lookup_binding'] or not isinstance(data,dict)):
        return False
    b=binding(data)
    if (any(b[i]!=p['lookup_binding'][i] for i in (0,1,2,3,4,5,7))
            or not isinstance(b[6],str) or not b[6]
            or b[6] in {'Not Registered','Unknown','Unable to Confirm','Unable to Verify','Site Not Reachable','Needs Review'}
            or data.get('confirmation_required')):return False
    p['public_binding']=b
    return True


def image_bound(run,result,url,raw,kind):
    p=getattr(run,'fl_response_proof',None)
    return bool(p and p['run_id']==run.run_id and p['public_binding']==binding(result)
                and url==URL and kind=='image'
                and getattr(run,'fl_response_images',{}).get(hashlib.sha256(raw).hexdigest())
                ==(p['sha256'],p['lookup_binding']))


def capture(master,run,result,page,stop,fact):
    """Use the existing owned page and absolute twenty-second visual stop."""
    proof=capture_bound(run,result)
    if not proof:return False
    started=time.perf_counter();served=[];route_installed=False
    def budget(reserve=0,cap=20):
        remaining=stop-time.monotonic()-reserve
        if remaining<=0:raise TimeoutError('FL original-response visual allowance exhausted')
        return max(1,int(min(remaining,cap)*1000))
    def route(request):
        req=request.request
        if (req.url!=URL or req.method!='GET' or req.resource_type!='document' or served
                or page.is_closed() or not capture_bound(run,result) or time.monotonic()>=stop):
            request.abort();return
        served.append(proof['sha256'])
        request.fulfill(status=200,content_type='text/html; charset=utf-8',body=proof['html'])
    def read():
        budget(0,.5)
        if page.url!=URL or not capture_bound(run,result):raise ValueError('FL retained response context changed')
        # The original public HTML is parsed unchanged by the existing parser.
        source=page.locator('html').evaluate('(e)=>e.outerHTML',timeout=budget(0,.5))
        rows=master.fl_business_candidate_rows(source)
        selected=[r for r in rows if r['business_evidence']['identifier']==result['matched_registry_identifier']
                  and r['business_evidence']['name']==result['matched_registry_name']]
        if selected!=[proof['selected']]:raise ValueError('FL selected original fields changed')
        text=page.inner_text('body',timeout=budget(0,.5))
        if re.search(r'verify you are human|user validation required|access denied|just a moment',text,re.I):
            raise ValueError('FL source verification pending')
        return text
    try:
        budget(3)
        fact.update(phase='retained_response_navigation',retained_response=True,extra_registry_queries=0,
                    new_source_document_requests=0,source_response_sha256=proof['sha256'])
        page.route(URL,route);route_installed=True
        response=page.goto(URL,wait_until='domcontentloaded',timeout=budget(2))
        if response is None or response.status!=200 or served!=[proof['sha256']]:
            raise ValueError('FL original response was not rendered')
        # Failed original styles cannot silently become a different-looking image.
        page.wait_for_function('()=>[...document.querySelectorAll("link[rel=stylesheet]")].every(e=>!!e.sheet)',timeout=budget(2))
        fact['phase']='retained_response_binding';text=read()
        size=page.locator('body').evaluate('(b)=>({w:Math.max(b.scrollWidth,document.documentElement.scrollWidth,innerWidth),h:Math.max(b.scrollHeight,document.documentElement.scrollHeight,innerHeight)})',timeout=budget(1.5,.5))
        if min(size.values())<=0 or size['w']*size['h']>20_000_000:raise ValueError('FL original page exceeds image bound')
        fact['phase']='retained_response_capture';begin=time.perf_counter()
        raw=page.screenshot(type='jpeg',quality=80,full_page=True,timeout=budget(.5,5))
        fact['capture_ms']=round((time.perf_counter()-begin)*1000,2)
        if read()!=text or not capture_bound(run,result):raise ValueError('FL original response changed during image')
        budget()
        if not 0<len(raw)<=3_000_000:raise ValueError('FL original image exceeds byte bound')
        run.fl_response_images={hashlib.sha256(raw).hexdigest():(proof['sha256'],proof['lookup_binding'])}
        count=len(run.documents)
        run.document(URL,raw,'image',text[:20000],note=NOTE)
        run.capture_ms+=fact['capture_ms']
        fact.update(outcome='captured' if len(run.documents)>count else 'image_admission_rejected',phase='retained_response_complete')
        return len(run.documents)>count
    except Exception as exc:
        fact.update(retained_response_error=type(exc).__name__,retained_response_error_summary=str(exc).splitlines()[0][:160])
        return False
    finally:
        if route_installed:page.unroute(URL,route)
        fact['retained_response_ms']=round((time.perf_counter()-started)*1000,2)
