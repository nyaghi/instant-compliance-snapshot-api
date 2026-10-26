"""Presentation-only package of displayed results and existing original evidence.

No registry requests, matching, or status decisions occur here. Archive failures
remain visible. Original evidence pages are appended without cropping or scaling.
"""
import copy
import hashlib
import io
import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer

from charity_clarity_report import HIGH, INCOMPLETE, NO_LISTING, validate_results, snapshot_due_date, date_text
from deployment import state_snapshots as ss, search_history as sh

SLOTS = threading.BoundedSemaphore(1)
MAX_BYTES = 60 * 1024 * 1024
MAX_PAGES = 350
ROOT = Path(__file__).resolve().parents[1]


def status_label(row):
    review = row.get('identity_review') or {}
    if row['status'] in INCOMPLETE and any(not c.get('decision') for c in review.get('candidates', [])):
        return 'Confirm match'
    return 'Unable to Confirm' if row['status'] == 'Needs Review' else row['status']


def negative(row):
    return row.get('success') is True and row['status'] in NO_LISTING


def references(row):
    """Retain the displayed decision state; never select an unresolved identity."""
    if negative(row):
        return [('Names searched', row.get('search_history_url', ''), None, 'history')]
    candidates = (row.get('identity_review') or {}).get('candidates', [])
    accepted = [c for c in candidates if c.get('decision') == 'accept']
    unresolved = any(not c.get('decision') for c in candidates)
    if candidates and (unresolved or row['status'] in INCOMPLETE):
        selected = [c for c in candidates if c.get('decision') != 'reject']
        if selected:
            return [(c.get('name', 'Candidate') + (' — identity accepted' if c.get('decision') == 'accept' else ' — identity not yet confirmed'),
                     c.get('evidence_url', ''), c, 'snapshot') for c in selected]
    if accepted:
        return [(c.get('name', 'Accepted record') + ' — identity accepted', c.get('evidence_url', ''), c, 'snapshot') for c in accepted]
    return [('State evidence', row.get('evidence_url', ''), row, 'snapshot')]


def evidence(row, ref, store):
    label, url, selected, kind = ref
    if store is None:
        raise ValueError('Saved archive unavailable')
    if kind == 'history':
        match = re.fullmatch(r'/state-evidence/([a-f0-9]{64})/search-history\.pdf', str(url))
        if not match:
            raise ValueError('Names searched unavailable for this check')
        item = sh.loaded(match[1], store)
        if not item:
            raise ValueError('Saved names searched unavailable')
        meta, doc, _ = item
        if doc.get('state') != row['state'] or ss.digits(doc.get('ein')) != row['ein']:
            raise ValueError('Saved names do not belong to this result')
        return sh.render_names_pdf(doc)
    match = re.fullmatch(r'/state-snapshots/([a-f0-9]{64})\.pdf', str(url))
    if not match:
        raise ValueError('State snapshot unavailable for this check')
    item = store.load(match[1])
    if not item:
        raise ValueError('Saved state snapshot unavailable')
    meta, raw, _ = item
    if (meta.get('state') != row['state'] or ss.digits(meta.get('ein')) != row['ein']
            or meta.get('kind') not in {'image', 'image_pages', 'source_pdf'}
            or hashlib.sha256(raw).hexdigest() != meta.get('source_sha256')):
        raise ValueError('Saved evidence integrity or organization binding failed')
    identifier = str(selected.get('matched_registry_identifier') or selected.get('identifier') or '')
    original_id = str(meta.get('identifier') or '')
    if identifier and identifier != original_id:
        # NM already uses the formatted and unformatted forms of the same EIN.
        if not (row['state'] == 'NM' and ss.digits(identifier) == row['ein'] == ss.digits(original_id)):
            raise ValueError('Saved evidence does not match the selected record')
    return ss.render_pdf(meta, raw)


def section_pdf(title, paragraphs, subtitle='', logo=False):
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='PackageBody', fontName='Helvetica', fontSize=10,
                              leading=14, spaceAfter=8, textColor=colors.HexColor('#172B45')))
    styles.add(ParagraphStyle(name='PackageSmall', fontSize=8, leading=11, spaceAfter=7,
                              textColor=colors.HexColor('#536274')))
    story = []
    asset = ROOT / 'report-assets/compliance-express.png'
    if logo and asset.exists():
        from PIL import Image as Pixels
        with Pixels.open(asset) as im:
            width, height = im.size
        image = Image(str(asset), width=150, height=150 * height / width)
        image.hAlign = 'LEFT'
        story.extend([image, Spacer(1, 18)])
    story.append(Paragraph(escape(title), styles['Title']))
    if subtitle:
        story.append(Paragraph(escape(subtitle), styles['PackageSmall']))
    for style, value in paragraphs:
        story.append(Paragraph(escape(str(value)).replace('\n', '<br/>'), styles[style]))
    output = io.BytesIO()
    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#536274'))
        canvas.drawString(42, 25, 'Compliance Express | www.compliance-express.com | info@compliance-express.com')
        canvas.restoreState()
    SimpleDocTemplate(output, pagesize=(612, 792), leftMargin=42, rightMargin=42,
                      topMargin=35, bottomMargin=45, title=title, author='Compliance Express').build(
                          story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def action_summary(rows, missing):
    sections = []
    def group(title, items):
        sections.append(('Heading2', title))
        sections.extend(('PackageBody', item) for item in (items or ['No items identified in the supplied results.']))
    group('1. Registration issues requiring attention', [
        f"{r['state']} — {r['status']}. Confirm the current record and any later filing, extension or reinstatement before deciding the corrective action."
        for r in rows if r['status'] in HIGH])
    upcoming = []
    now = datetime.now(ZoneInfo('America/New_York')).date()
    for row in rows:
        due = snapshot_due_date(row)
        if row['status'] == 'Upcoming Filing' or (row['status'] == 'Current' and due and 0 <= (due - now).days <= 60):
            upcoming.append(f"{row['state']} — {row['status']}. " +
                            (f"Returned due date: {date_text(due)}. " if due else 'Due date not supplied. ') +
                            'Confirm the applicable renewal or filing and assign an owner.')
    group('2. Upcoming renewals and filings', upcoming)
    group('3. Not registered', [
        f"{r['state']} — {r['status']}. Review activity, any exemption and recent submissions before deciding whether registration is required."
        for r in rows if negative(r)])
    exempt = [r['state'] for r in rows if r['status'] == 'Exempt']
    targets = [r['state'] for r in rows if r['status'] in {'Current', 'Upcoming Filing', 'Not Registered'} and r.get('success') is not False]
    opportunities = []
    if exempt and targets:
        opportunities.append('Exemption review: an exemption is recorded in ' + ', '.join(exempt) +
                             '. Use its documented basis to screen ' + ', '.join(targets) +
                             ' for possible relief under each state’s own criteria. This is a review lead, not a finding of eligibility. An exemption does not transfer between states; keep existing obligations current during review.')
    group('4. Potential opportunities', opportunities)
    unresolved = [r['state'] + ': ' + status_label(r) for r in rows if r['status'] in INCOMPLETE]
    if unresolved or missing:
        sections.append(('Heading2', 'Items still requiring confirmation'))
        if unresolved:
            sections.append(('PackageBody', 'Unresolved results: ' + '; '.join(unresolved) + '. These are not findings of non-registration.'))
        if missing:
            sections.append(('PackageBody', 'Evidence unavailable: ' + '; '.join(missing) + '. The state sections identify each missing document.'))
    return sections


def generate(payload, supported_states, store=None):
    rows = validate_results(payload, supported_states)
    originals = {str(r['state']).upper(): r for r in payload['results']}
    for row in rows:
        original = originals[row['state']]
        for key in ('success', 'identity_review', 'evidence_url', 'search_history_url', 'matched_registry_name'):
            if key in original:
                row[key] = copy.deepcopy(original[key])
        review = row.get('identity_review') or {}
        if not isinstance(review, dict) or not isinstance(review.get('candidates', []), list) or len(review.get('candidates', [])) > 24:
            raise ValueError('Invalid identity review')
        if any(not isinstance(c, dict) or c.get('decision') not in {None, 'accept', 'reject'} for c in review.get('candidates', [])):
            raise ValueError('Invalid identity decision')
    rows.sort(key=lambda r: r['state'])
    store = store if store is not None else ss.STORE
    started = time.monotonic()
    documents, missing, total = {}, [], 0
    for row in rows:
        documents[row['state']] = []
        seen = set()
        for ref in references(row):
            if ref[1] and ref[1] in seen:
                continue
            seen.add(ref[1])
            try:
                if time.monotonic() - started > 75:
                    raise ValueError('Package preparation time limit reached; retry this download')
                pdf = evidence(row, ref, store)
                total += len(pdf)
                if total > MAX_BYTES:
                    raise ValueError('Saved evidence exceeds the package size limit')
                # Validate before claiming that evidence is included.
                pages = len(PdfReader(io.BytesIO(pdf)).pages)
                if pages < 1 or pages > 48:
                    raise ValueError('Saved evidence exceeds the document page limit')
                documents[row['state']].append((ref[0], pdf, None))
            except Exception as exc:
                reason = str(exc) if isinstance(exc, ValueError) else 'Saved evidence could not be read'
                missing.append(row['state'] + ' / ' + ref[0])
                documents[row['state']].append((ref[0], None, reason))
    writer = PdfWriter()
    def append(pdf, title):
        reader = PdfReader(io.BytesIO(pdf))
        if len(writer.pages) + len(reader.pages) > MAX_PAGES:
            raise ValueError('Package exceeds 350 pages; download fewer states together')
        start = len(writer.pages)
        for page in reader.pages:
            writer.add_page(page)
        writer.add_outline_item(title, start)
    stamp = datetime.now(ZoneInfo('America/New_York')).strftime('%B %d, %Y at %I:%M %p %Z')
    identity = rows[0]['organization_name'] + ' | EIN ' + rows[0]['ein'][:2] + '-' + rows[0]['ein'][2:]
    summary = [('PackageBody', identity), ('PackageSmall', f'Prepared {stamp}. {len(rows)} state results supplied; {len(supported_states) - len(rows)} supported states not included.'),
               ('PackageSmall', 'Based on the displayed Aurora results and user decisions at download time. No new state searches were run. Potential actions require review of the applicable facts and state requirements.')]
    append(section_pdf('Compliance Package', summary + action_summary(rows, missing), logo=True), 'Action summary')
    for row in rows:
        body = [('Heading2', status_label(row)), ('PackageBody', row.get('comments', ''))]
        for label, key in [('Registry match', 'matched_registry_name'), ('Registry ID', 'matched_registry_identifier'),
                           ('Initial registration', 'registration_date'), ('Last renewal / filed period', 'renewal_filing_value'),
                           ('Date context', 'renewal_filing_note'), ('Source', 'source_url'), ('Release', 'app_version')]:
            if row.get(key):
                body.append(('PackageBody', label + ': ' + str(row[key])))
        checked = row.get('checked_at_epoch')
        if isinstance(checked, (float, int)):
            body.append(('PackageSmall', 'Checked ' + sh.stamp(checked)))
        for candidate in (row.get('identity_review') or {}).get('candidates', []):
            body.append(('PackageBody', 'Identity decision: ' + str(candidate.get('name', '')) + ' (' + str(candidate.get('identifier', '')) + ') — ' +
                         {'accept': 'Accepted', 'reject': 'Rejected', None: 'Not yet decided'}[candidate.get('decision')]))
        for label, pdf, reason in documents[row['state']]:
            body.append(('PackageBody', label + ': ' + ('included on the following evidence pages.' if pdf else 'UNAVAILABLE — ' + reason + '.')))
        append(section_pdf(row['state'] + ' — Aurora result', body, identity), row['state'] + ' — ' + status_label(row))
        for label, pdf, reason in documents[row['state']]:
            if pdf:
                append(pdf, row['state'] + ' — ' + label)
    writer.add_metadata({'/Title': 'Compliance Package — ' + rows[0]['organization_name'], '/Author': 'Compliance Express'})
    output = io.BytesIO()
    writer.write(output)
    if output.tell() > MAX_BYTES:
        raise ValueError('Package exceeds the download size limit; select fewer states')
    return output.getvalue()


def handle(master, handler):
    admitted = False
    try:
        length = int(handler.headers.get('Content-Length', '0'))
        if not 0 < length <= 524288:
            return handler._send_json(413, {'error': 'Package input must be between 1 byte and 512 KB.'})
        payload = json.loads(handler.rfile.read(length))
        if not isinstance(payload, dict):
            raise ValueError('Invalid package request')
        email = master.normalize_email(payload.get('email') or '')
        passcode = str(payload.get('admin_passcode') or '').strip()
        error = master.staging_access_error(email, passcode)
        if error or not master.is_exempt_domain(master.email_domain(email)) or passcode != master.ADMIN_PASSCODE:
            return handler._send_json(403, {'error': error or 'Sign in with authorized Compliance Express access.'})
        admitted = SLOTS.acquire(blocking=False)
        if not admitted:
            return handler._send_json(429, {'error': 'A compliance package is being prepared. Try again shortly.'})
        pdf = generate(payload, master.SUPPORTED_STATES)
        handler.send_response(200)
        for key, value in [('Content-Type', 'application/pdf'), ('Content-Length', str(len(pdf))),
                           ('Content-Disposition', 'attachment; filename="Compliance-Package.pdf"'),
                           ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff')]:
            handler.send_header(key, value)
        handler.end_headers()
        handler.wfile.write(pdf)
    except (ValueError, TypeError, UnicodeError) as exc:
        handler._send_json(400, {'error': str(exc)})
    except Exception:
        handler._send_json(500, {'error': 'The package could not be prepared. Your results are retained.'})
    finally:
        if admitted:
            SLOTS.release()
