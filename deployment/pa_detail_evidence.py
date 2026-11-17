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
DETAIL_ID=r"""()=>{
 const ids=new Set(), seen=new WeakSet();
 const visit=(obj,depth)=>{
   if(!obj||typeof obj!=='object'||seen.has(obj)||depth<0)return;
   seen.add(obj);
   for(const [k,v] of Object.entries(obj)){
     if(/^personid$/i.test(k)&&/^\d+$/.test(String(v)))ids.add(String(v));
     else if(!k.startsWith('$')&&v&&typeof v==='object')visit(v,depth-1);
   }
 };
 const panel=document.querySelector('#panelEntityInfo');
 if(panel){
   for(const el of [panel,...panel.querySelectorAll('[ng-model]')]){
     const scope=window.angular?.element(el).scope();
     visit(scope,2);visit(window.angular?.element(el).isolateScope?.(),2);
   }
   for(const el of panel.querySelectorAll('input[name]'))
     if(/^personid$/i.test(el.name)&&/^\d+$/.test(el.value))ids.add(el.value);
 }
 return [...ids];
}"""
SETTLED="""()=>![...document.querySelectorAll('.cg-busy')].some(el=>el.getClientRects().length && getComputedStyle(el).visibility!=='hidden' && getComputedStyle(el).display!=='none')"""


def bound(fields, row, *, exempt=False):
    return (key(fields.get('EntityName'))==key(row[0])
        and str(fields.get('RegNum') or '').strip()==row[3].strip()
        and digits(fields.get('FederalID'))==digits(row[5])
        and str(fields.get('Expdt') or '').strip()==row[4].strip()
        and bool(row[0]) and (bool(row[3]) or exempt and len(digits(row[5])) == 9))


def selected_row(rows, ein, result):
    """Select the same EIN/filing shown in the result, not an empty duplicate."""
    identifier = str(getattr(result, 'matched_registry_identifier', '') or '')
    name = getattr(result, 'matched_registry_name', '')
    hits = [r for r in rows if len(r['cells']) >= 12 and (
        digits(r['cells'][5]) == ein or identifier and name
        and r['cells'][3] == identifier and key(r['cells'][0]) == key(name)
        and not digits(r['cells'][5]))]
    if len(hits) == 1:
        return hits[0]
    raw = str(getattr(result, 'raw_status_text', '') or '').strip()
    # A unique, numbered row with the exact expiration used for the status
    # can coexist with a same-EIN profile having no registration at all.
    # Do not rank conflicting dated registrations or choose the first row.
    matching = [r for r in hits if r['cells'][3] and r['cells'][4]
                and r['cells'][4].strip() == raw
                and (not identifier or r['cells'][3] == identifier)
                and (not name or key(r['cells'][0]) == key(name))]
    return matching[0] if len(matching) == 1 else None


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
        chosen=selected_row(rows,run.ein,result)
        source_record = getattr(run, 'pa_selected_record', None)
        blank_record = None
        if chosen is None and isinstance(source_record, dict):
            from .pa_selected_evidence import selected_row as selected_api_row, visible_values
            if selected_api_row([source_record], result) is not None:
                expected = visible_values(source_record)
                matches = [r for r in rows if len(r['cells']) >= 12 and all(
                    (digits(r['cells'][index]) if index == 5 else key(r['cells'][index])) == value
                    for index, value in expected.items())]
                if len(matches) == 1 and not source_record.get('CertificateNumber') and not source_record.get('ExpDate'):
                    chosen = matches[0]
                    blank_record = source_record
        if chosen is None:return
        cells=chosen['cells']
        exempt = (str(result.status).strip().casefold() == 'exempt'
                  and str(cells[4]).strip().casefold() == 'exempt')
        if (not cells[3] or not cells[4]) and not exempt and blank_record is None:return
        page.wait_for_function(SETTLED,timeout=timeout())
        grid=page.screenshot(type='jpeg',quality=80,full_page=True,timeout=min(timeout(),2000))
        with page.expect_popup(timeout=timeout()) as opened:
            page.locator('tr#SearchResults').nth(chosen['index']).locator('i[ng-click="search.redirectEntityDetails(row)"]').click(timeout=timeout())
        popup=opened.value
        popup.wait_for_url(DETAIL,timeout=timeout())
        popup.wait_for_function("() => !!document.querySelector('#panelEntityInfo input[name=EntityName]')?.value",timeout=timeout())
        popup.wait_for_function(SETTLED,timeout=timeout())
        fields=popup.evaluate(PROBE)
        if blank_record is None:
            if not bound(fields,cells,exempt=exempt):return
        else:
            # The completed API result supplies PersonId and the full office
            # when PA omits its public certificate and EIN. The clicked row
            # must still carry that exact ID, and the detail must identify it.
            binding = page.locator('tr#SearchResults').nth(chosen['index']).locator('i[ng-click="search.redirectEntityDetails(row)"]').evaluate(
                "el => { const s=window.angular?.element(el).scope(); return s?.row?.PersonId == null ? '' : String(s.row.PersonId); }")
            requested_id = str(blank_record.get('PersonId') or '')
            if (binding != requested_id or not requested_id
                    or popup.evaluate(DETAIL_ID) != [requested_id]
                    or key(fields.get('EntityName')) != key(cells[0])
                    or digits(fields.get('FederalID')) not in {'', run.ein}
                    or str(fields.get('RegNum') or '').strip() != cells[3].strip()
                    or str(fields.get('Expdt') or '').strip() != cells[4].strip()):
                return
        if exempt and str(fields.get('Expdt') or '').strip().casefold() != 'exempt':return
        raw=popup.screenshot(type='jpeg',quality=80,full_page=True,timeout=min(timeout(),3000))
        if blank_record is not None and popup.evaluate(DETAIL_ID) != [str(blank_record['PersonId'])]:return
        if popup.url!=DETAIL or not popup.evaluate(SETTLED) or popup.evaluate(PROBE)!=fields or time.monotonic()>=stop:return
        packed=json.dumps([base64.b64encode(v).decode('ascii') for v in (grid,raw)]).encode()
        if len(packed)>MAX_BYTES:return
        # Metadata describes the actual disabled input values visible in pixels.
        text=' | '.join(cells[:11])+'\n'+'\n'.join(k+': '+str(v) for k,v in fields.items())
        run.document(DETAIL,packed,'image_pages',text,note='Original Pennsylvania search result and selected detail page; same identity and applicable registration fields verified before and after capture.')
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
