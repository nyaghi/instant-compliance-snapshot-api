"""Append PA's original matched detail, without a second registry search."""
import base64
import hashlib
import json
import re
import time
from .state_snapshots import CURRENT, DEADLINE, digits, key, MAX_BYTES

SEARCH='https://www.charities.pa.gov/#/page/searchCharities'
DETAIL='https://www.charities.pa.gov/#/page/charitiesEntityDetails'
PROBE="""()=>Object.fromEntries([...document.querySelectorAll('#panelEntityInfo input')]
 .filter(el=>el.getClientRects().length).map(el=>[el.name,el.value]))"""


def bound(fields, row):
    return (key(fields.get('EntityName'))==key(row[0])
        and str(fields.get('RegNum') or '').strip()==row[3].strip()
        and digits(fields.get('FederalID'))==digits(row[5])
        and str(fields.get('Expdt') or '').strip()==row[4].strip()
        and bool(row[0]) and bool(row[3]))


def capture(page, org, result):
    run=CURRENT.get()
    if (not run or run.state!='PA' or page.url!=SEARCH or result.state!='PA'
        or not result.success or result.status=='Not Registered' or digits(org.ein)!=run.ein):return
    stop=min(DEADLINE.get()-1,time.monotonic()+8)
    popup=None
    fact={'adapter':'PA-selected-detail','outcome':'pending'}
    run.visual_adapter_facts.append(fact)
    started=time.monotonic()
    def timeout():
        remaining=stop-time.monotonic()
        if remaining<=0:raise TimeoutError('PA detail allowance exhausted')
        return max(1,int(remaining*1000))
    try:
        timeout()
        rows=page.locator('tr#SearchResults').evaluate_all("nodes=>nodes.map((el,index)=>({index,cells:[...el.querySelectorAll('td')].map(x=>x.innerText.trim())}))")
        identifier=str(getattr(result,'matched_registry_identifier','') or '')
        name=getattr(result,'matched_registry_name','')
        hits=[r for r in rows if len(r['cells'])>=12 and (
            digits(r['cells'][5])==run.ein or identifier and name
            and r['cells'][3]==identifier and key(r['cells'][0])==key(name) and not digits(r['cells'][5]))]
        if len(hits)!=1:return
        chosen=hits[0];cells=chosen['cells']
        if not cells[3] or not cells[4]:return
        grid=page.screenshot(type='jpeg',quality=80,full_page=True,timeout=min(timeout(),2000))
        with page.expect_popup(timeout=timeout()) as opened:
            page.locator('tr#SearchResults').nth(chosen['index']).locator('i[ng-click="search.redirectEntityDetails(row)"]').click(timeout=timeout())
        popup=opened.value
        popup.wait_for_url(DETAIL,timeout=timeout())
        popup.wait_for_function("() => !!document.querySelector('#panelEntityInfo input[name=FederalID]')?.value",timeout=timeout())
        fields=popup.evaluate(PROBE)
        if not bound(fields,cells):return
        raw=popup.screenshot(type='jpeg',quality=80,full_page=True,timeout=min(timeout(),3000))
        if popup.url!=DETAIL or popup.evaluate(PROBE)!=fields or time.monotonic()>=stop:return
        packed=json.dumps([base64.b64encode(v).decode('ascii') for v in (grid,raw)]).encode()
        if len(packed)>MAX_BYTES:return
        # Metadata describes the actual disabled input values visible in pixels.
        text=' | '.join(cells[:11])+'\n'+'\n'.join(k+': '+str(v) for k,v in fields.items())
        run.document(DETAIL,packed,'image_pages',text,note='Original Pennsylvania search result and selected detail page; same name, EIN, certificate and expiration verified before and after capture.')
        run.pa_detail_hash=hashlib.sha256(packed).hexdigest()
        fact.update(outcome='captured',pages=2)
    except Exception as exc:
        fact.update(outcome='unavailable',error_type=type(exc).__name__)
    finally:
        if popup:
            try:popup.close()
            except Exception:pass
        if fact['outcome']=='pending':fact['outcome']='binding_rejected'
        fact['total_ms']=round((time.monotonic()-started)*1000)


def select(run,ordered):
    proof=getattr(run,'pa_detail_hash',None)
    paired=[d for d in ordered if d[0]==DETAIL and d[2]=='image_pages' and hashlib.sha256(d[1]).hexdigest()==proof]
    return paired+ordered
