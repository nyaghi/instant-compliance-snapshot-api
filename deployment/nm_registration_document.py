"""Append the original latest submitted NM filing to its bound detail image."""
import base64
import io
import re
import time
from datetime import datetime
from urllib.parse import urlsplit, parse_qsl
from pypdf import PdfReader, PdfWriter

def selected_submission(rows):
    candidates = []
    for row in rows:
        if not isinstance(row, list) or len(row) != 3: return None
        year, label, date = row
        if not re.fullmatch(r'20\d{2}', str(year)): continue
        match = re.fullmatch(r'Registration Submitted\s+(\d{10,20})', str(label))
        if not match: continue
        try: stamp = datetime.strptime(date, '%m/%d/%Y')
        except (ValueError, TypeError): return None
        candidates.append((int(year), stamp, match[1], date))
    if not candidates: return None
    rank = max((c[0], c[1]) for c in candidates)
    selected = {c for c in candidates if c[:2] == rank}
    return next(iter(selected)) if len(selected) == 1 else None

def append_to_asset(asset, document, record, query, evidence):
    """Optional evidence only. Any invalid/unavailable attachment keeps the image."""
    from deployment.state_snapshots import MAX_BYTES, digits, key, render_pdf
    if record.get('state') != 'NM' or query.get('state') != 'NM' or query.get('operation') != 'detail': return asset
    if not isinstance(document, dict): return asset
    try:
        selected = selected_submission(evidence.get('history_rows', []))
        if not selected: return asset
        year, _, number, submitted = selected
        ein = digits(record.get('ein'))
        if (document.get('query') != query or evidence.get('ein') != ein
                or query.get('identifier') != ein or asset.get('identifier') != ein
                or document.get('registration_number') != number
                or document.get('tax_year') != year or document.get('submitted_on') != submitted): return asset
        u = urlsplit(document.get('source_url', ''))
        if (u.scheme != 'https' or u.netloc != 'secure.nmdoj.gov' or u.path != '/coros/getregdoc.aspx'
                or u.fragment or parse_qsl(u.query) != [('RegNumber', number)]): return asset
        stamp = document.get('captured_at')
        if type(stamp) not in (int, float) or not record['issued']-60 <= stamp <= time.time()+60: return asset
        encoded = document.get('content', '')
        if not isinstance(encoded, str) or len(encoded) > 4_000_000: return asset
        raw = base64.b64decode(encoded, validate=True)
        if not raw.startswith(b'%PDF-') or not 0 < len(raw) <= MAX_BYTES: return asset
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted or not 1 <= len(reader.pages) <= 100: return asset
        text = reader.pages[0].extract_text() or ''
        if (not re.search(r'(?<!\d)'+ein[:2]+r'-?'+ein[2:]+r'(?!\d)', text)
                or not re.search(r'Registration Submitted\s*\('+re.escape(number)+r'\)', text)
                or not re.search(r'Tax Year\s+'+str(year)+r'\b', text)
                or not key(evidence['name']) or key(evidence['name']) not in key(text)): return asset
        first = render_pdf({'kind': asset['kind']}, base64.b64decode(asset['content'], validate=True))
        first_reader = PdfReader(io.BytesIO(first))
        if len(first_reader.pages) != 1: return asset
        writer = PdfWriter()
        writer.add_page(first_reader.pages[0])
        for page in reader.pages: writer.add_page(page)
        out = io.BytesIO(); writer.write(out)
        if len(out.getvalue()) > MAX_BYTES: return asset
        return {**asset, 'kind': 'source_pdf', 'operation': 'detail_registration',
                'content': base64.b64encode(out.getvalue()).decode('ascii'),
                'capture_note': 'Original latest submitted NM registration '+number+' (tax year '+str(year)+') appended in full after the selected detail. Source: '+document['source_url']}
    except Exception:
        return asset
