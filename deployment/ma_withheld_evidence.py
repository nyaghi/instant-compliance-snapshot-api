"""Original publication-restriction evidence, not a substitute filing status."""
import hashlib
import re

URL = 'https://masscharities.my.site.com/FilingSearch/s/'
REASON = 'MA_RECORD_NOT_PUBLIC'
MESSAGE = 'This Charity is not available for public.'


def preserves_identity(result):
    """Keep only the identity bound to this lookup's publication notice."""
    proof = getattr(result, '_ma_withheld_identity', None)
    return bool(getattr(result, 'state', '') == 'MA'
        and getattr(result, 'status_reason', '') == REASON
        and getattr(result, 'status', '') == 'Unable to Confirm'
        and getattr(result, 'success', False) is True
        and proof == (re.sub(r'\D', '', result.ein),
                      getattr(result, 'matched_registry_identifier', ''),
                      getattr(result, 'matched_registry_name', ''), URL)
        and proof and re.fullmatch(r'\d{9}', proof[0])
        and re.fullmatch(r'a09[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?', proof[1])
        and proof[2] and result.source_url == URL)


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
    observation = {'adapter': 'MA-owned-publication-notice', 'phase': 'identity_guard', 'outcome': 'pending'}
    run.visual_adapter_facts.append(observation)
    try:
        if page.url != URL or not page.evaluate(script, wanted):
            observation.update(outcome='rejected', reason='displayed_query_or_selection_not_bound')
            return False
        before = len(run.documents)
        observation['phase'] = 'original_capture'
        run.page(page)
        if page.url != URL or not page.evaluate(script, wanted):
            observation.update(outcome='rejected', reason='source_changed_during_capture')
            return False
        bindings = getattr(run, 'ma_withheld_bindings', {})
        captured = False
        for url, raw, kind, text, *_ in run.documents[before:]:
            if url == URL and kind == 'image' and MESSAGE in text:
                bindings[hashlib.sha256(raw).hexdigest()] = (query, candidate['value'], candidate['label'])
                captured = True
        run.ma_withheld_bindings = bindings
        observation.update(outcome='bound' if captured else 'unavailable', phase='archive_binding')
        return captured
    except Exception as exc:
        observation.update(outcome='failed', error_type=type(exc).__name__)
        return False


def bound(run, row, document):
    url, raw, kind, text, *_ = document
    return bool(row.get('status_reason') == REASON and row.get('status') == 'Unable to Confirm'
        and row.get('success') is True and url == URL and kind == 'image' and MESSAGE in text
        and getattr(run, 'ma_withheld_bindings', {}).get(hashlib.sha256(raw).hexdigest())
        == (run.ein, row.get('matched_registry_identifier'), row.get('matched_registry_name')))
