"""Photograph the original official Colorado fallback response for this lookup."""
import hashlib
import json
import re
import time
from urllib.parse import parse_qsl, urlsplit

NOTE = ("Colorado's regular search page was unavailable. This result uses the state's "
        "official registration dataset. This dataset result does not establish the "
        "initial registration date or renewal filing date.")


def dataset_ein(url):
    try:
        if not isinstance(url, str) or len(url) > 5000:
            return None
        u = urlsplit(url)
        if (u.scheme != 'https' or u.hostname != 'data.colorado.gov'
                or u.username or u.password or u.port not in (None, 443)
                or u.fragment or u.path != '/resource/37wu-kn3g.json'):
            return None
        pairs = parse_qsl(u.query, keep_blank_values=True)
        values = dict(pairs)
        if (len(pairs) != 3 or set(values) != {'$limit', '$where', '$order'}
                or values['$limit'] != '10'
                or values['$order'] != 'registrationapproveddate DESC'):
            return None
        match = re.fullmatch(r"fein='(\d{2})-(\d{7})'", values['$where'])
        return ''.join(match.groups()) if match and ''.join(match.groups()) != '000000000' else None
    except (ValueError, TypeError):
        return None


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def result_binding(result):
    get = result.get if isinstance(result, dict) else lambda k, d=None: getattr(result, k, d)
    return tuple(get(k) for k in ('state', 'ein', 'success', 'source_url',
                                  'matched_registry_name', 'matched_registry_identifier',
                                  'status', 'raw_status_text'))


def remember_lookup(result, rows, selected):
    """Private same-run proof; never add response bytes to public result/review tokens."""
    from deployment.state_snapshots import CURRENT, digits
    run = CURRENT.get()
    if run is None or run.state != 'CO':
        return False
    binding = result_binding(result)
    if (binding[0] != 'CO' or digits(binding[1]) != run.ein or binding[2] is not True
            or dataset_ein(binding[3]) != run.ein or not binding[4] or not binding[5]
            or binding[6] in {'Not Registered', 'Unable to Confirm', 'Site Not Reachable',
                              'Unable to Verify', 'Unknown'}
            or not isinstance(rows, list) or not 1 <= len(rows) <= 10
            or any(not isinstance(r, dict) or r.get('fein') != run.ein[:2]+'-'+run.ein[2:] for r in rows)
            or selected not in rows or selected.get('name') != binding[4]
            or str(selected.get('entityid') or selected.get('documentid') or '') != binding[5]):
        return False
    try:
        run.co_dataset_proof = {'run_id': run.run_id, 'binding': binding, 'serialized_binding': None,
                                'response': digest(rows), 'selected': digest(selected)}
    except (TypeError, ValueError):
        return False
    return True


def bound_proof(run, result):
    proof = getattr(run, 'co_dataset_proof', None)
    return proof if (run.state == 'CO' and proof and proof['run_id'] == run.run_id
                     and proof['serialized_binding' if isinstance(result, dict) else 'binding'] == result_binding(result)
                     and dataset_ein(proof['binding'][3]) == run.ein) else None


def seal_public_result(source_result, data):
    """Bind the existing serializer's result once, without reinterpreting status."""
    from deployment.state_snapshots import CURRENT
    run = CURRENT.get()
    if run is None or run.state != 'CO':
        return False
    proof = getattr(run, 'co_dataset_proof', None)
    if (not proof or proof['run_id'] != run.run_id or proof.get('serialized_binding') is not None
            or proof['binding'] != result_binding(source_result) or not isinstance(data, dict)):
        return False
    published = result_binding(data)
    # Every source identity/status-text field stays exact. Only the trusted
    # existing formatter may translate the internal status into its public label.
    if (any(published[i] != proof['binding'][i] for i in (0, 1, 2, 3, 4, 5, 7))
            or not isinstance(published[6], str) or not published[6]
            or published[6] in {'Not Registered', 'Unable to Confirm', 'Site Not Reachable',
                                'Unable to Verify', 'Needs Review', 'Unknown'}
            or data.get('confirmation_required')):
        return False
    proof['serialized_binding'] = published
    return True


def native_response(page, proof, timeout):
    if page.url != proof['binding'][3]:
        raise ValueError('CO dataset URL changed')
    text = page.locator('pre').inner_text(timeout=timeout)
    if len(text.encode()) > 3_000_000:
        raise ValueError('CO dataset response exceeds bound')
    rows = json.loads(text)
    if digest(rows) != proof['response'] or not any(digest(r) == proof['selected'] for r in rows):
        raise ValueError('CO dataset response changed')
    return text


def image_bound(run, result, url, raw, kind):
    proof = bound_proof(run, result)
    return bool(proof and kind == 'image' and url == proof['binding'][3]
                and getattr(run, 'co_dataset_image_bindings', {}).get(hashlib.sha256(raw).hexdigest())
                == (proof['response'], proof['selected'], proof['serialized_binding']))


def capture(master, result, run, deadline):
    proof = bound_proof(run, result)
    if not proof or getattr(run, 'co_dataset_visual_attempted', False):
        if (not proof and isinstance(result, dict) and dataset_ein(result.get('source_url')) == run.ein):
            saved = getattr(run, 'co_dataset_proof', None)
            run.visual_adapter_facts.append({'adapter': 'CO-official-dataset-original',
                                            'outcome': 'lookup_proof_unbound',
                                            'proof_present': bool(saved),
                                            'serialized_proof_present': bool(saved and saved.get('serialized_binding'))})
        return
    run.co_dataset_visual_attempted = True
    start = time.monotonic()
    # Prior inline CO photographs consume this same eight-second visual allowance.
    stop = min(deadline-1, start+max(0, 8-run.capture_ms/1000))
    fact = {'adapter': 'CO-official-dataset-original', 'outcome': 'not_started',
            'capture_ms': 0, 'total_ms': 0, 'requests': 0}
    run.visual_adapter_facts.append(fact)
    held = False
    context = browser = None

    def budget(reserve=0, cap=8):
        remaining = stop-time.monotonic()-reserve
        if remaining <= 0:
            raise TimeoutError('CO dataset visual allowance exhausted')
        return max(1, int(min(cap, remaining)*1000))

    try:
        budget(3)
        held = master.BROWSER_LOOKUP_SEMAPHORE.acquire(blocking=False)
        if not held:
            fact['outcome'] = 'browser_capacity_unavailable'
            return
        with master.checker.sync_playwright() as p:
            browser = master.launch_lookup_browser(p, headless=True)
            try:
                budget(3)
                options = {'viewport': {'width': 1280, 'height': 900}, 'locale': 'en-US'}
                if getattr(master, 'BROWSER_USER_AGENT', None):
                    options['user_agent'] = master.BROWSER_USER_AGENT
                context = browser.new_context(**options)
                page = context.new_page()
                fact['requests'] = 1
                response = page.goto(proof['binding'][3], wait_until='domcontentloaded', timeout=budget(3))
                if (response is None or response.status != 200
                        or response.headers.get('content-type', '').split(';')[0].strip() != 'application/json'):
                    raise ValueError('CO dataset response unavailable')
                text = native_response(page, proof, budget(2, 1))
                size = page.locator('body').evaluate(
                    '(b)=>({w:Math.max(b.scrollWidth,document.documentElement.scrollWidth,innerWidth),'
                    'h:Math.max(b.scrollHeight,document.documentElement.scrollHeight,innerHeight)})',
                    timeout=budget(1.5, .5))
                if not size or min(size['w'], size['h']) <= 0 or size['w']*size['h'] > 20_000_000:
                    raise ValueError('CO dataset page exceeds capture bound')
                capture_start = time.monotonic()
                try:
                    raw = page.screenshot(type='jpeg', quality=80, full_page=True, timeout=budget(.5, 5))
                finally:
                    fact['capture_ms'] = round((time.monotonic()-capture_start)*1000, 2)
                if native_response(page, proof, budget(0, .5)) != text or not bound_proof(run, result):
                    raise ValueError('CO dataset changed during capture')
                budget()
                if not 0 < len(raw) <= 3_000_000:
                    raise ValueError('CO dataset image exceeds byte bound')
                run.co_dataset_image_bindings = {
                    hashlib.sha256(raw).hexdigest(): (proof['response'], proof['selected'], proof['serialized_binding'])}
                run.document(proof['binding'][3], raw, 'image', text[:20000],
                             'Original official Colorado dataset response, captured and checked against the same lookup response.')
                fact['outcome'] = 'captured'
            finally:
                if context is not None:
                    context._captured = True
                    context.close()
                if browser is not None:
                    browser.close()
    except Exception as exc:
        fact['outcome'] = 'source_visual_unavailable'
        fact['error_type'] = type(exc).__name__
        run.errors.append('CO_dataset_visual_unavailable')
    finally:
        run.capture_ms += fact['capture_ms']
        if held:
            master.BROWSER_LOOKUP_SEMAPHORE.release()
        fact['total_ms'] = round((time.monotonic()-start)*1000, 2)
