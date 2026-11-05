"""Original publication-restriction evidence, not a substitute filing status."""
import hashlib
import re

URL = 'https://masscharities.my.site.com/FilingSearch/s/'
REASON = 'MA_RECORD_NOT_PUBLIC'
MESSAGE = 'This Charity is not available for public.'


def capture(page, run, candidate, query):
    if (run is None or run.state != 'MA' or query != run.ein
            or not re.fullmatch(r'a09[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?', candidate.get('value', ''))):
        return False
    script = r'''wanted => {
      const norm=s=>(s||'').replace(/\s+/g,' ').trim();
      const selects=[...document.querySelectorAll('select')].filter(e=>e.getClientRects().length);
      const mode=selects.find(e=>norm(e.selectedOptions[0]?.textContent)==='Employer Identification Number');
      const record=selects.filter(e=>e.value===wanted.id&&norm(e.selectedOptions[0]?.textContent)===wanted.name);
      const fields=[...document.querySelectorAll('input')].filter(e=>e.getClientRects().length&&e.value===wanted.ein);
      const text=document.body.innerText;
      return !!(mode&&record.length===1&&fields.length===1&&text.includes(wanted.message)
        &&!text.includes('Please wait...')&&!/verify you are human|access denied/i.test(text));
    }'''
    wanted = {'id': candidate['value'], 'name': candidate['label'], 'ein': query, 'message': MESSAGE}
    try:
        if page.url != URL or not page.evaluate(script, wanted):
            return False
        before = len(run.documents)
        run.page(page)
        if page.url != URL or not page.evaluate(script, wanted):
            return False
        bindings = getattr(run, 'ma_withheld_bindings', {})
        for url, raw, kind, text, *_ in run.documents[before:]:
            if url == URL and kind == 'image' and MESSAGE in text:
                bindings[hashlib.sha256(raw).hexdigest()] = (query, candidate['value'], candidate['label'])
        run.ma_withheld_bindings = bindings
        return bool(bindings)
    except Exception:
        return False


def bound(run, row, document):
    url, raw, kind, text, *_ = document
    return bool(row.get('status_reason') == REASON and row.get('status') == 'Unable to Confirm'
        and row.get('success') is True and url == URL and kind == 'image' and MESSAGE in text
        and getattr(run, 'ma_withheld_bindings', {}).get(hashlib.sha256(raw).hexdigest())
        == (run.ein, row.get('matched_registry_identifier'), row.get('matched_registry_name')))
