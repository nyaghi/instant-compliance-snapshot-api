"""Original PA name-fallback grid, bound to the completed API record."""
import hashlib
import json
import re
import time
from .state_snapshots import CURRENT, DEADLINE, digits, key

URL = 'https://www.charities.pa.gov/#/page/searchCharities'
API = 'https://www.charities.pa.gov/api/Charities/Search'


def selected_row(rows, result):
    ident = str(getattr(result, 'matched_registry_identifier', '') or '')
    name = getattr(result, 'matched_registry_name', '')
    hits = [r for r in rows if isinstance(r, dict)
            and str(r.get('CertificateNumber') or r.get('PersonId') or '') == ident
            and key(r.get('EntityName', '')) == key(name)]
    unique = {json.dumps(r, sort_keys=True) for r in hits}
    return json.loads(next(iter(unique))) if len(unique) == 1 else None


def visible_values(row):
    # PA's internal PersonId is not printed. Name and full office bind its grid row.
    return {0: key(row.get('EntityName', '')), 3: key(row.get('CertificateNumber') or ''),
            5: digits(row.get('EIN') or ''), 7: key(row.get('AddressLine') or ''),
            8: key(row.get('City') or ''), 9: key(row.get('StateName') or ''),
            10: key(row.get('Zip') or '')}


def image_bound(run, result, url, raw, kind):
    if (run.state != 'PA' or result.get('state') != 'PA' or digits(result.get('ein')) != run.ein
            or kind != 'image' or url != URL or result.get('success') is not True):
        return False
    proof = getattr(run, 'pa_selected_images', {}).get(hashlib.sha256(raw).hexdigest())
    return bool(proof and proof == (run.ein, result.get('matched_registry_name'),
        str(result.get('matched_registry_identifier') or '')))


def capture(page, org, result, rows, query, deadline):
    run = CURRENT.get()
    if (run is None or run.state != 'PA' or digits(org.ein) != run.ein
            or result.state != 'PA' or not result.success or page.url != URL):
        return
    chosen = selected_row(rows, result)
    if not chosen or (digits(chosen.get('EIN') or '') not in {'', run.ein}):
        return
    expected = visible_values(chosen)
    if not all(expected[i] for i in [0, 7, 8, 9, 10]):
        return
    expected = {str(i): value for i, value in expected.items()}
    stop = min(deadline, DEADLINE.get()-1)
    if stop-time.monotonic() < 3:
        return
    start = len(run.documents)
    fact = {'adapter':'PA-selected-name-grid','outcome':'pending'}
    run.visual_adapter_facts.append(fact)
    started = time.perf_counter()
    def timeout():
        remaining = stop-time.monotonic()
        if remaining <= 0: raise TimeoutError('PA selected grid allowance exhausted')
        return max(1, int(remaining*1000))
    try:
        page.get_by_role('button', name=re.compile(r'^Clear$', re.I)).first.click(timeout=timeout())
        page.locator('select[name="searchCategory"]').select_option(label='Charities & IPP',timeout=timeout())
        page.locator('select[name="searchCriteria"]').select_option(label='Contains',timeout=timeout())
        page.locator('input[name="entityName"]').fill(query,timeout=timeout())
        def response_matches(response):
            if response.url != API or response.request.method != 'POST': return False
            try:
                data=response.request.post_data_json
                return (data.get('EntityName')==query and not data.get('EIN')
                        and data.get('SearchCriteria')=='Contains'
                        and data.get('SearchCategory')=='Charities_IPP')
            except Exception:return False
        with page.expect_response(response_matches, timeout=timeout()) as pending:
            page.get_by_role('button',name=re.compile('Search',re.I)).first.click(timeout=timeout())
        response=pending.value
        if response.status != 200:return
        data=response.json();new_rows=data.get('Table');counts=data.get('Table1')
        if (not isinstance(new_rows,list) or not counts or counts[0].get('RESULTCOUNT')!=len(new_rows)
                or selected_row(new_rows,result)!=chosen):return
        probe='''expected=>{
          const norm=s=>String(s||'').toLowerCase().replace(/[^a-z0-9]/g,'');
          const rows=[...document.querySelectorAll('tr#SearchResults')].filter(r=>r.getClientRects().length);
          const hits=rows.map(r=>[...r.querySelectorAll('td')].map(c=>c.innerText.trim()))
            .filter(cs=>cs.length>=11&&Object.entries(expected).every(([i,v])=>norm(cs[Number(i)])===v));
          return hits.length===1?JSON.stringify(hits[0]):false;
        }'''
        page.wait_for_function(probe,arg=expected,timeout=timeout())
        before=page.evaluate(probe,expected)
        timeout();run.page(page);timeout()
        if page.url!=URL or not before or page.evaluate(probe,expected)!=before:
            del run.documents[start:];return
        bindings=getattr(run,'pa_selected_images',None)
        if bindings is None:run.pa_selected_images={}
        for doc in run.documents[start:]:
            if doc[0]==URL and doc[2]=='image':
                run.pa_selected_images[hashlib.sha256(doc[1]).hexdigest()]=(run.ein,result.matched_registry_name,str(result.matched_registry_identifier))
        fact['outcome']='captured' if len(run.documents)>start else 'capture_unavailable'
    except Exception as exc:
        del run.documents[start:]
        fact.update(outcome='unavailable',error_type=type(exc).__name__)
    finally:
        if fact['outcome']=='pending':fact['outcome']='binding_rejected'
        fact['total_ms']=round((time.perf_counter()-started)*1000,2)
