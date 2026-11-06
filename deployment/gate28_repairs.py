"""Bounded retrieval and source-field repairs; no network or timing changes."""
import re
from urllib.parse import urlsplit, parse_qsl


def ga_article_queries(master, required, generated):
    """Trade one punctuation-equivalent fallback for one internal-article form."""
    names = list(required) + list(generated)
    if not required:
        return names
    original = required[0]
    variant = re.sub(r'(?<=\S)\s+(?:the|a|an)\s+(?=\S)', ' ', original, flags=re.I)
    key = lambda value: re.sub(r'[^a-z0-9]', '', value.lower())
    if (variant == original or len(master.distinctive_match_tokens(variant)) < 2
            or variant.casefold() in {n.casefold() for n in names}):
        return names
    replacement = next((n for n in reversed(generated)
                        if key(n) == key(original) and n not in required), None)
    if replacement is None:
        return names
    rest = list(generated)
    rest.remove(replacement)
    candidate = [required[0], variant, *required[1:], *rest]
    def completed_probes(values):
        covered = set()
        probes = []
        for value in values:
            if value.casefold() in covered:
                continue
            prefix = master.ga_distinctive_covering_prefix(value)
            coverage = [n for n in values if prefix and n.casefold().startswith(prefix.casefold())]
            probe = prefix if len(coverage) > 1 else value
            probes.append(probe)
            covered.update(n.casefold() for n in (coverage if len(coverage) > 1 else [value]))
        return probes
    return candidate if len(completed_probes(candidate)) <= len(completed_probes(names)) else names


def ms_dash_space_queries(name, planned, protected):
    """Reach a literal dash-space legal core without increasing the query count."""
    base = re.sub(r'(?:,\s*|\s+)(?:inc\.?|incorporated|corp\.?|corporation|llc|ltd\.?|limited)\s*$', '', name, flags=re.I)
    variant = re.sub(r'(?<=[A-Za-z0-9])-(?=[A-Za-z0-9])', '- ', base)
    if variant == base or variant.casefold() in {v.casefold() for v in planned}:
        return planned
    core = lambda value: re.sub(r'[^a-z0-9]', '', re.sub(
        r'(?:,\s*|\s+)(?:inc\.?|incorporated|corp\.?|corporation|llc|ltd\.?|limited)\s*$', '', value, flags=re.I).lower())
    protected = {v.casefold() for v in protected}
    replacement = next((v for v in reversed(planned[1:])
                        if v.casefold() not in protected and core(v) == core(name)), None)
    if replacement is None:
        return planned
    rest = list(planned)
    rest.remove(replacement)
    return [rest[0], variant, *rest[1:]]


def nv_historical_expired_empty(master, record, records, identity):
    """Only a later confirmed CSR can resolve a completed expired empty record."""
    if (not record or record.get('_nv_complete_empty_history') is not True
            or record.get('raw_status', '').casefold() != 'expired'
            or not record.get('expiration') or record['expiration'] >= master.date.today()
            or record.get('ein') or identity != 'accepted'
            or record.get('match', {}).get('decision') != 'accepted'
            or record.get('address_evidence', {}).get('decision') in {'conflict', 'different_ein'}):
        return False
    return any(
        other.get('_identity_outcome') == 'accepted'
        and other.get('match', {}).get('decision') == 'accepted'
        and master.normalized_match_name(other['name']) == master.normalized_match_name(record['name'])
        and other.get('solicitation_statement_filed')
        and other['solicitation_statement_filed'] > record['expiration']
        and other.get('expiration') and other['expiration'] > record['expiration']
        and other.get('status') in {'Current', 'Upcoming Filing', 'Delinquent', 'Exempt'}
        and other.get('address_evidence', {}).get('decision') not in {'conflict', 'different_ein'}
        for other in records)


def or_malformed_review(master, org, result, name, body, url):
    """Keep an exact named record with an invalid source EIN for signed review."""
    displayed = master.checker.extract_labeled_value_from_text(body, ['Federal EIN', 'EIN'])
    digits = re.sub(r'\D', '', displayed or '')
    requested = master.canonical_ein_digits(org.ein)
    if not digits or len(digits) == 9 or len(requested) != 9:
        return None
    u = urlsplit(str(url))
    pairs = parse_qsl(u.query)
    registration = re.search(r'\bRegistration\s*:\s*#?\s*(\d+)\b', body, re.I)
    status = master.true_status_from_body(result, body)
    if (u.scheme != 'https' or u.netloc != 'justice.oregon.gov'
            or u.path != '/Charities/Charity/details' or u.fragment
            or len(pairs) != 1 or pairs[0][0] != 'charityID' or not pairs[0][1].isdigit()
            or not registration or not name
            or master.normalized_match_name(name) not in {
                master.normalized_match_name(v) for v in [org.organization_name, *master.known_names_for_ein(org.ein)]}
            or len(master.distinctive_match_tokens(name)) < 2
            or status not in {'Current', 'Upcoming Filing', 'Delinquent', 'Exempt', 'Pending', 'Suspended', 'Revoked', 'Closed / Withdrawn / Canceled'}):
        return None
    identifier = registration[1]
    due = getattr(result, 'computed_due_date', '')
    row = dict(name=name, identifier=identifier, ein='', url=url, location='',
               raw_status=result.raw_status_text, expiration=due, status=status,
               _identity_outcome='possible')
    result.status = 'Needs Review'
    result.success = False
    result.reason_code = 'OR_MALFORMED_EIN_IDENTITY_REVIEW'
    result.status_reason = 'OR_MALFORMED_EIN_IDENTITY_REVIEW'
    result.matched_registry_name = name
    result.matched_registry_identifier = identifier
    result.source_url = url
    result.source_note = (f'Oregon displays the malformed Federal EIN {displayed!s} on {name} '
                          f'(registration {identifier}). It is not a valid nine-digit EIN and does not prove '
                          'a different organization. Review the original record and accept or reject its identity. '
                          'The candidate status uses the existing Oregon filing-history rules; no EIN digit was repaired.')
    result._cc_identity_review = {'records': [row], 'search_complete': False, 'freshness': ''}
    return result
