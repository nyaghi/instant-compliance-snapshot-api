"""Original publication-restriction evidence, not a substitute filing status."""
import hashlib
import re

URL = 'https://masscharities.my.site.com/FilingSearch/s/'
REASON = 'MA_RECORD_NOT_PUBLIC'
MESSAGE = 'This Charity is not available for public.'

GUARD_SCRIPT = r'''wanted => {
  const norm=s=>(s||'').replace(/\s+/g,' ').trim();
  const roots=[document], nodes=[];
  // Salesforce puts the actual form inside an open component shadow root.
  // Read it without modifying the page or broadening identity admission.
  for(let i=0;i<roots.length;i++) {
    if(roots.length>32)return {bound:false,reason:'source_structure_exceeds_bound'};
    for(const e of roots[i].querySelectorAll('*')) {
      nodes.push(e);
      if(nodes.length>15000)return {bound:false,reason:'source_structure_exceeds_bound'};
      if(e.shadowRoot)roots.push(e.shadowRoot);
    }
  }
  const selects=nodes.filter(e=>e.tagName==='SELECT'&&e.getClientRects().length);
  const modes=selects.filter(e=>norm(e.selectedOptions[0]?.textContent)==='Employer Identification Number');
  const records=selects.filter(e=>e.value===wanted.id&&norm(e.selectedOptions[0]?.textContent)===wanted.name);
  const fields=nodes.filter(e=>e.tagName==='INPUT'&&e.getClientRects().length&&e.value===wanted.ein);
  const text=roots.map(root=>root===document?document.body.innerText:
    [...root.children].filter(e=>e.getClientRects().length).map(e=>e.innerText||'').join('\n')).join('\n');
  const fact={modes:modes.length,records:records.length,fields:fields.length,
    message:text.includes(wanted.message),loading:text.includes('Please wait...'),
    blocked:/verify you are human|access denied/i.test(text),shadow_roots:roots.length-1};
  return {...fact,source_text:text.slice(0,20000),bound:fact.modes===1&&fact.records===1&&fact.fields===1&&fact.message&&!fact.loading&&!fact.blocked};
}'''


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
    wanted = {'id': candidate['value'], 'name': candidate['label'], 'ein': query, 'message': MESSAGE}
    observation = {'adapter': 'MA-owned-publication-notice', 'phase': 'identity_guard', 'outcome': 'pending'}
    run.visual_adapter_facts.append(observation)
    try:
        facts = page.evaluate(GUARD_SCRIPT, wanted) if page.url == URL else {'bound':False,'reason':'source_url_changed'}
        source_text = facts.pop('source_text', '')
        observation['guard'] = facts
        if not facts.get('bound'):
            observation.update(outcome='rejected', reason='displayed_query_or_selection_not_bound')
            return False
        before = len(run.documents)
        observation['phase'] = 'original_capture'
        run.page(page)
        after = page.evaluate(GUARD_SCRIPT, wanted) if page.url == URL else {'bound':False,'reason':'source_url_changed'}
        after_text = after.pop('source_text', '')
        observation['post_capture_guard'] = after
        if not after.get('bound') or after_text != source_text:
            observation.update(outcome='rejected', reason='source_changed_during_capture')
            return False
        bindings = getattr(run, 'ma_withheld_bindings', {})
        captured = False
        for index in range(before, len(run.documents)):
            url, raw, kind, text, *tail = run.documents[index]
            if url == URL and kind == 'image' and MESSAGE in source_text:
                # Preserve the original image bytes. Some Chromium versions
                # omit shadow-root text from body.innerText; this metadata is
                # read from the same visible roots before and after capture.
                run.documents[index] = (url, raw, kind, source_text, *tail)
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
