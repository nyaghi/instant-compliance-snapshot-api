"""State-specific, evidence-bound Gate 41 recovery rules."""
import io
import re
import time
from datetime import timedelta
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

_SUFFIX = re.compile(r"[, ]+(?:inc\.?|incorporated|corp\.?|corporation|llc|ltd\.?)$", re.I)

def legal_core(value):
    return _SUFFIX.sub('', value.strip()).strip(' ,')

def plain_key(value):
    return re.sub(r'[^a-z0-9]', '', legal_core(value).lower())

def ct_service_variant(name):
    core = legal_core(name)
    if not re.fullmatch(r'[A-Za-z]+(?: [A-Za-z]+){2,7}', core):
        return ''
    matches = list(re.finditer(r'\bServices?\b', core, re.I))
    if len(matches) != 1 or matches[0].start() == 0 or matches[0].end() == len(core):
        return ''
    m = matches[0]
    alternate = m[0][:-1] if m[0].lower().endswith('s') else m[0] + 's'
    return core[:m.start()] + alternate + core[m.end():]

def ga_possessive_variant(name):
    core = legal_core(name)
    m = re.fullmatch(r"([A-Za-z]{4,})( (?:Academy|Institute|School))", core, re.I)
    if not m or m[1].lower().endswith('s') or m[1].casefold() in {'the','national','american','united','international','global','world','state','public','community','federal','royal'}:
        return ''
    return m[1] + "'s" + m[2]

def replace_low_value_slot(names, protected, original, variant):
    if not variant or variant.casefold() in {n.casefold() for n in names}:
        return names
    protected = {n.casefold() for n in protected}
    root = legal_core(original)
    words = root.casefold().split()
    for i in range(len(names)-1, 0, -1):
        n = names[i]
        if n.casefold() not in protected and (
                n.casefold() in words or plain_key(n) == plain_key(original)):
            return [*names[:i], variant, *names[i+1:]]
    return names

def nm_submitted_period(rows, submitted, periods, parse):
    """Two contiguous fiscal years with the same tax label after a short transition."""
    if not submitted:
        return ''
    year, number, when = submitted
    candidates = [(parse(p['period_start']), parse(p['period_end']), p['period_end'])
                  for p in periods if p['tax_year'] == year]
    by_end = {p[2] for p in candidates}
    if len(by_end) <= 1:
        return next(iter(by_end), '')
    candidates = sorted(set(candidates))
    if len(candidates) == 2 and all(p[0] and p[1] for p in candidates):
        (short_start, short_end, _), (full_start, full_end, full_text) = candidates
        submissions = [(m[1], parse(on)) for y, detail, on in rows if y == year
                       and (m := re.fullmatch(r'Registration Submitted (\d{10,})', detail))]
        if (0 < (short_end - short_start).days < 364
                and full_start == short_end + timedelta(days=1)
                and 364 <= (full_end - full_start).days <= 365
                and len(submissions) == 2 and len({n for n, _ in submissions}) == 2
                and all(d for _, d in submissions)):
            earlier, latest = sorted(submissions, key=lambda item: item[1])
            if (latest == (number, parse(when))
                    and short_end <= earlier[1] < full_end <= latest[1]):
                return full_text
    raise ValueError('Conflicting New Mexico fiscal periods')

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def or_filing_link(href):
    u = urlsplit(urljoin('https://justice.oregon.gov/', href))
    if (u.scheme == 'https' and u.netloc == 'justice.oregon.gov'
            and u.path == '/Charities/Charity/GetCharityReport' and not u.fragment
            and re.fullmatch(r'rptId=\d{1,15}', u.query)):
        return u.geturl()
    return ''

def or_filing_identity(raw, name, identifier, ein, period):
    """Bind Oregon cover plus the attached federal return's filer header."""
    from pypdf import PdfReader
    if len(raw) > 8_000_000 or not raw.startswith(b'%PDF'):
        return False
    pdf = PdfReader(io.BytesIO(raw))
    if not 2 <= len(pdf.pages) <= 140:
        return False
    cover = pdf.pages[0].extract_text() or ''
    if not re.search(r'\bOregon Department of Justice\b', cover, re.I):
        return False
    def field(label):
        m = re.search(label + r'\s*:?\s*([^\r\n]+)', cover, re.I)
        return m[1].strip() if m else ''
    if (field(r'Registration\s*#') != identifier
            or plain_key(field(r'Organization Name')) != plain_key(name)
            or field(r'Period Ending') != period):
        return False
    for index, page in enumerate(pdf.pages[1:7], 1):
        head = ' '.join((page.extract_text(extraction_mode='layout') or '')[:4200].split())
        if ('Return of Organization Exempt From Income Tax' not in head
                or 'Employer identification number' not in head):
            continue
        # Read only boxes C/D on the first Form 990 page.
        m = re.search(r'Employer identification number(.*?)Number and street', head, re.I | re.S)
        if not m:
            return False
        ein_values = {v.replace('-', '') for v in re.findall(r'\b\d{2}-\d{7}\b', m[1])}
        words = re.findall(r'[a-z0-9]+', legal_core(name).lower())
        label = r'\b' + r'[^a-z0-9]+'.join(map(re.escape, words)) + r'\b'
        if ein_values != {ein} or not re.search(label, m[1], re.I):
            return False
        from pypdf import PdfWriter
        output = io.BytesIO()
        writer = PdfWriter()
        writer.add_page(pdf.pages[0])
        writer.add_page(pdf.pages[index])
        writer.write(output)
        return output.getvalue()
    return False

def fetch_or_filing(url, deadline):
    remaining = deadline - time.monotonic()
    if not or_filing_link(url) or remaining <= 2:
        return b''
    try:
        req = Request(url, headers={'Accept':'application/pdf'})
        with build_opener(NoRedirect()).open(req, timeout=min(5.0, remaining-1)) as response:
            if response.status != 200 or response.headers.get_content_type() != 'application/pdf':
                return b''
            raw = bytearray()
            while len(raw) <= 8_000_000 and time.monotonic() < deadline - .5:
                part = response.read1(65536)
                if not part:
                    return bytes(raw)
                raw.extend(part)
    except (OSError, ValueError):
        pass
    return b''


def ms_recovery_name(record, payload, now):
    pending = record.get('pending') or {}
    query = pending.get('query') or {}
    if (record.get('state') != 'MS' or record.get('completed') or record.get('ms_search_recovery')
            or query.get('state') != 'MS' or query.get('operation') != 'search'
            or not pending.get('query_id') or payload.get('query_id') != pending['query_id']
            or payload.get('reason') not in {'NY_CONNECTOR_INCOMPLETE', 'NY_CONNECTOR_TAB_READY_TIMEOUT'}
            or record.get('expires', 0) - now < 18):
        return ''
    name = query.get('name', '')
    recovery = legal_core(name)
    return recovery if len(recovery.split()) >= 2 and recovery != name else ''
