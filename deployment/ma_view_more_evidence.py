"""Original MA filing-list and selected charity View more evidence."""
import base64
import hashlib
import json
import re
import time
from urllib.parse import urlsplit


def bound(text, record, run):
    from deployment.state_snapshots import digits, source_name_present
    account = str(record.get('ago_account', ''))
    accounts = re.findall(r'AG\s+Account\s+Number\s*:?\s*(\d+)', text, re.I)
    eins = {digits(x) for x in re.findall(r'(?<!\d)\d{2}[- ]?\d{7}(?!\d)', text)}
    return (bool(re.fullmatch(r'\d{6}', account)) and accounts == [account]
            and eins == {run.ein} and digits(record.get('ein', '')) == run.ein
            and source_name_present(record.get('name', ''), text, 'MA'))


def capture(run, page, record):
    from deployment.state_snapshots import DEADLINE
    if run is None or run.state != 'MA':
        return
    record_id = str(record.get('record_id', ''))
    if not re.fullmatch(r'a09[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?', record_id):
        return
    stop = min(time.monotonic() + 20, DEADLINE.get() - 1)
    detail = None
    previous_stop = getattr(run, 'page_capture_stop', None)
    observation = {'adapter': 'MA-selected-view-more', 'phase': 'main_binding'}
    run.visual_adapter_facts.append(observation)

    def timeout():
        remaining = stop - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('MA_view_more_deadline')
        return max(1, int(remaining * 1000))

    def retain(source, role):
        text = source.locator('body').inner_text(timeout=timeout())
        if not bound(text, record, run):
            raise ValueError('MA_view_more_identity_unbound')
        before = len(run.documents)
        run.page(source)
        if len(run.documents) <= before:
            raise ValueError('MA_view_more_capture_missing')
        document = run.documents[-1]
        if document[0] != source.url or document[2] != 'image' or not bound(document[3], record, run):
            del run.documents[before:]
            raise ValueError('MA_view_more_capture_unbound')
        bindings = getattr(run, 'ma_view_more_bindings', None)
        if bindings is None:
            run.ma_view_more_bindings = bindings = {}
        bindings[hashlib.sha256(document[1]).hexdigest()] = {
            'role': role, 'record': dict(record), 'url': document[0]}

    try:
        u = urlsplit(page.url)
        if u.scheme != 'https' or u.netloc != 'masscharities.my.site.com' or u.path != '/FilingSearch/s/' or u.query or u.fragment:
            return
        run.page_capture_stop = stop
        retain(page, 'main')
        observation['phase'] = 'view_more_open'
        with page.expect_popup(timeout=timeout()) as opened:
            page.get_by_role('button', name='View more', exact=True).click(timeout=timeout())
        detail = opened.value
        expected = 'https://masscharities.my.site.com/FilingSearch/s/detail/' + record_id
        detail.wait_for_url(expected, wait_until='domcontentloaded', timeout=timeout())
        observation['phase'] = 'detail_readiness'
        detail.get_by_text(re.compile(r'Employer Identification Number \(EIN\)')).first.wait_for(timeout=timeout())
        # A visible field label can precede the selected record values.
        # Wait for the same existing identity binding, inside the original cap,
        # leaving one second for the original image capture.
        while True:
            if detail.url != expected:
                raise ValueError('MA_view_more_wrong_record')
            text = detail.locator('body').inner_text(timeout=timeout())
            if bound(text, record, run):
                break
            if stop - time.monotonic() <= 1:
                raise ValueError('MA_view_more_identity_unbound')
            detail.wait_for_timeout(min(100, max(1, int((stop - time.monotonic() - 1) * 1000))))
        retain(detail, 'detail')
        observation['phase'] = 'complete'
    except Exception as exc:
        observation.update(error_type=type(exc).__name__, error_summary=str(exc)[:1500])
        run.errors.append('MA_view_more_original_unavailable')
    finally:
        if previous_stop is None:
            if hasattr(run, 'page_capture_stop'):
                del run.page_capture_stop
        else:
            run.page_capture_stop = previous_stop
        if detail is not None:
            try:
                detail.close()
            except Exception:
                pass


def select(run, ordered, row):
    """Never substitute a filing attachment for the charity View more page."""
    from deployment.state_snapshots import MAX_BYTES, digits, key
    if run.state != 'MA':
        return ordered
    if row.get('success') is not True or digits(row.get('ein', '')) != run.ein:
        return []
    selected = {}
    for document in ordered:
        binding = getattr(run, 'ma_view_more_bindings', {}).get(hashlib.sha256(document[1]).hexdigest(), {})
        record = binding.get('record', {})
        if (document[2] != 'image' or binding.get('url') != document[0]
                or str(record.get('ago_account', '')) != str(row.get('matched_registry_identifier', ''))
                or key(record.get('name', '')) != key(row.get('matched_registry_name', ''))
                or not bound(document[3], record, run)):
            continue
        selected.setdefault(binding['role'], document)
    main = selected.get('main')
    detail = selected.get('detail')
    if main is None:
        return []
    if detail is not None:
        raw = json.dumps([base64.b64encode(d[1]).decode('ascii') for d in (main, detail)]).encode('utf8')
        if len(raw) <= MAX_BYTES:
            return [(detail[0], raw, 'image_pages', (main[3] + '\n\n' + detail[3])[:20000], detail[4],
                     'Original Massachusetts filing-list page and the selected charity View more detail.')]
    return [main]
