"""Explicit CA nonregistration, distinct from corporate entity standing."""
import re


def explicit_absence(entity, registrations):
    """Only complete, uncredentialed charity records establish this case.

    Mixed credentials, dates, reporting/enforcement flags, and other license
    categories are not permission to infer charity-registration absence.
    """
    if not isinstance(entity, dict) or not isinstance(registrations, list) or not registrations:
        return False
    if re.search(r'\b(?:exempt|registration\s+not\s+required|suspended|revoked|enforcement|cease\s+and\s+desist)\b',
                 str(entity.get('entityStatus') or ''), re.I):
        return False
    for record in registrations:
        if not isinstance(record, dict):
            return False
        if (str(record.get('registrationType', '')).strip().casefold() != 'charitable organization'
                or str(record.get('registrationStatus', '')).strip().casefold() != 'not registered'
                or any(record.get(field) for field in (
                    'registrationNumber', 'currentExpirationDate', 'renewalEvaluationDate',
                    'currentIssuanceDate', 'initialRegistrationDate', 'reportingStatus'))
                or record.get('complianceStatus')):
            return False
        related = record.get('entityRelated')
        if related and (not isinstance(related, dict) or str(related.get('id')) != str(entity.get('id'))):
            return False
    return True


def review_status(row):
    """Allow only the signed explicit CA record to carry its negative status."""
    raw = str(row.get('raw_status', ''))
    return (row.get('interpreted_status') == 'Not Registered'
            and bool(re.search(r'(?:^|\|)\s*Registration Type:\s*Charitable Organization\s*(?:\||$)', raw, re.I))
            and bool(re.search(r'(?:^|\|)\s*Registration Status:\s*Not Registered\s*(?:\||$)', raw, re.I))
            and not re.search(r'\b(?:suspended|revoked|enforcement|cease\s+and\s+desist)\b', raw, re.I)
            and not row.get('expiration'))


def remember_detail(run, result):
    """Bind a real no-number registration page to its selected entity."""
    if (run is None or run.state != 'CA' or not getattr(result, 'success', False)
            or getattr(result, 'status', '') != 'Not Registered'):
        return
    entity = getattr(result, '_cc_selected_entity', None)
    records = getattr(result, '_cc_registration_records', None)
    if not explicit_absence(entity, records) or len(records) != 1:
        return
    norm = lambda value: re.sub(r'[^a-z0-9]', '', str(value).lower())
    identifier = str(getattr(result, 'matched_registry_identifier', '') or '')
    name = str(getattr(result, 'matched_registry_name', '') or '')
    record = records[0]
    detail_id = str(record.get('id') or '')
    related = record.get('entityRelated') or {}
    source_ein = re.sub(r'\D', '', str(entity.get('fein') or ''))
    if (not name or not re.fullmatch(r'\d+', identifier) or str(entity.get('id')) != identifier
            or not re.fullmatch(r'\d+', detail_id) or str(related.get('id')) != identifier
            or norm(related.get('name')) != norm(name + ' - ' + identifier)
            or norm(entity.get('entityName') or entity.get('legalName') or entity.get('name')) != norm(name)
            or source_ein and source_ein != run.ein):
        return
    run.remember_detail(identifier, name,
        'https://ca-rcf.evokeplatform.com/app/publicPortal/registrationDetails/' + detail_id)
    hint = run.source_detail_hints.get(identifier)
    if hint:
        hint['ca_explicit_nonregistration'] = dict(entity_id=identifier, detail_id=detail_id, name=name)


def selected_result(result):
    """A selected nonregistered CA record is not an empty-search result."""
    return (isinstance(result, dict) and result.get('state') == 'CA'
            and result.get('success') is True
            and bool(result.get('matched_registry_name'))
            and bool(re.fullmatch(r'\d+', str(result.get('matched_registry_identifier') or '')))
            and review_status(dict(interpreted_status=result.get('status'),
                raw_status=result.get('raw_status_text'), expiration=result.get('computed_due_date'))))


def preserves_selected_record(result):
    if getattr(result, 'state', '') != 'CA':
        return False
    entity = getattr(result, '_cc_selected_entity', None)
    records = getattr(result, '_cc_registration_records', None)
    if not explicit_absence(entity, records):
        return False
    data = {key:getattr(result, key, None) for key in ('state','success','status',
        'matched_registry_name','matched_registry_identifier','raw_status_text','computed_due_date')}
    norm = lambda value: re.sub(r'[^a-z0-9]', '', str(value).lower())
    return (selected_result(data) and str(entity.get('id')) == data['matched_registry_identifier']
        and norm(entity.get('entityName') or entity.get('legalName') or entity.get('name')) == norm(data['matched_registry_name'])
        and (not entity.get('fein') or re.sub(r'\D','',str(entity['fein'])) == re.sub(r'\D','',str(getattr(result,'ein','')))))


def bound_core(text, proof):
    """Require the original selected entity and explicit empty credential fields."""
    if not isinstance(proof, dict):
        return None
    sections = re.findall(r'\bEntity Related\b[\s\S]*?\bCHARITABLE ORGANIZATION DETAILS\b', text)
    if len(sections) != 1:
        return None
    core = sections[0]
    related = re.search(r'Entity Related\s+(.*?)\s+(?:Email\s+)?Registration Number\b', core, re.S)
    norm = lambda value: re.sub(r'[^a-z0-9]', '', str(value).lower())
    if (not related or norm(related[1]) != norm(proof.get('name', '') + ' - ' + proof.get('entity_id', ''))
            or not re.search(r'Registration Number\s+Registration Type\s+Charitable Organization\b', core)
            or not re.search(r'Registration Status\s+Not Registered\s+(?:Initial Registration Date|Reporting Status)\b', core)
            or re.search(r'\b(?:suspended|revoked|enforcement|verify you are human|access denied)\b', core, re.I)
            or re.search(r'\b\d{1,4}[-/]\d{1,2}[-/]\d{1,4}\b', core)):
        return None
    return core
