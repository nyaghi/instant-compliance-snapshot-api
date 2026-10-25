"""Prepare the evidence index from the exact refreshed original PDF bytes."""
import hashlib
import io
import re
from pypdf import PdfReader
from deployment.state_snapshots import source_name_present


def build_page_index(state, raw, records, asset):
    if state not in {'KY', 'NH'} or not raw.startswith(b'%PDF'):
        raise ValueError('Expected an original KY/NH PDF')
    known = {str(row[0]): str(row[1]) for row in records}
    if not known:
        raise ValueError('Empty record identifiers')
    variants = {}
    for row in records:
        variants.setdefault(str(row[0]), set()).add(str(row[1]))
    pages = {}
    reader = PdfReader(io.BytesIO(raw))
    for number, page in enumerate(reader.pages):
        text = page.extract_text() or ''
        candidates = set(re.findall(r'(?<!\d)\d{1,6}(?!\d)', text)) & known.keys()
        if '' in known:
            candidates.add('')
        for identifier in candidates:
            if any(source_name_present(name, text, state) for name in variants[identifier]):
                pages.setdefault(identifier, []).append(number)
    if len(pages) < len(known) * .8:
        raise ValueError('Insufficient original-page identity coverage')
    return {'asset': asset, 'source_sha256': hashlib.sha256(raw).hexdigest(),
            'pages': pages, 'record_names': known}
