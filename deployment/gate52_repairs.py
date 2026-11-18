"""Source-schema repairs; no search expansion or inferred identity acceptance."""
import io
import re
import time


def ca_exempt_raffle_only(entity, registrations):
    """A completed raffle-only list cannot supply a charity credential ID."""
    return (isinstance(entity, dict) and entity.get('entityStatus') == 'Exempt'
            and re.fullmatch(r'\d+', str(entity.get('id') or '')) is not None
            and isinstance(registrations, list) and bool(registrations)
            and all(isinstance(row, dict)
                    and str(row.get('registrationType') or '').strip().casefold() == 'raffle'
                    and re.fullmatch(r'RF\d+', str(row.get('registrationNumber') or ''))
                    and not re.search(r'cease\s+and\s+desist|suspended|enforcement|revoked',
                                      str(row.get('registrationStatus') or ''), re.I)
                    for row in registrations))


def ga_compound_candidate(master, targets, label):
    """A complete legal name in a comma-delimited label merits review only."""
    label = str(label or '')
    prefixes = [label[:match.start()] for match in re.finditer(r'[,;]', label)
                if label[match.end():].strip()]
    if not prefixes:
        return False
    literal = lambda value: re.sub(r'[^a-z0-9]+', ' ', master.canonical_name_punctuation(value).casefold()).strip()
    return any(len(master.distinctive_match_tokens(target)) >= 2
               and literal(target) == literal(part)
               for target in targets for part in prefixes)


def ma_primary_return_identity(raw, name, ein, stop):
    """Read primary IRS header fields, never EINs in narrative or schedules."""
    import pdfplumber
    key = lambda value: re.sub(r'[^a-z0-9]', '', str(value).casefold())
    digits = lambda value: re.sub(r'\D', '', value)
    expected = key(name)
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        # Electronic covers commonly precede Form 990. Only four early pages
        # are inspected, under the caller's existing attachment deadline.
        for index in range(min(3, len(pdf.pages) - 1)):
            if time.monotonic() >= stop:
                return False
            first, second = pdf.pages[index:index+2]
            header = first.crop((0, 0, first.width, first.height * .205)).extract_text() or ''
            name_field = first.crop((first.width * .14, 0, first.width * .69, first.height * .205)).extract_text() or ''
            if (not re.search(r'Return of Organization Exempt From Income Tax', header, re.I)
                    or not re.search(r'Name of organization', header, re.I)
                    or not re.search(r'Employer identification number', header, re.I)
                    or not any(key(line) == expected for line in name_field.splitlines())):
                continue
            eins = {digits(value) for value in re.findall(r'(?<!\d)\d{2}-\d{7}(?!\d)', header)}
            following = second.crop((0, 0, second.width, second.height * .075)).extract_text() or ''
            following_eins = {digits(value) for value in re.findall(r'(?<!\d)\d{2}-\d{7}(?!\d)', following)}
            match = re.search(r'Form\s+990\s*\((20\d{2})\)\s+(.+?)\s+(\d{2}-\d{7})\s+Page\s+2\b', following)
            if (eins == {ein} and following_eins == {ein} and match
                    and key(match[2]) == expected and digits(match[3]) == ein
                    and time.monotonic() < stop):
                return True
    return False


def nj_discovery_discrepancies(master, names, sources, organization_name, ein=''):
    """Quarantine a sole-source unrelated registered name, not a proven alias."""
    key = master.identity_name_key
    primary = key(organization_name)
    primary_sources = {source.get('source') for source in sources if source.get('complete')
                       and any(key(item.get('name', '')) == primary for item in source.get('names', []))}
    if 'NJ' not in primary_sources or not primary_sources - {'NJ'}:
        return {}
    result = {}
    for item in names:
        proofs = item.get('evidence', [])
        if (item.get('historical') or key(item.get('name', '')) == primary or not proofs
                or any(proof.get('source') not in {'NJ', master.identity_source_label('NJ')}
                       or proof.get('type') != 'Registered name' for proof in proofs)
                or set(master.distinctive_match_tokens(item['name']))
                   & set(master.distinctive_match_tokens(organization_name))):
            continue
        result[key(item['name'])] = {
            'source': 'NJ', 'reason': 'Conflicting registered name in one source',
            'candidate_name': item['name'],
            'candidate_ein': master.format_ein(ein) if ein else 'not independently verified',
            'candidate_location': 'New Jersey source discrepancy',
            'source_url': proofs[0].get('url', ''),
            'explanation': 'New Jersey returned this unrelated registered name under the entered EIN. '
                           'Other completed sources corroborate the entered name, but do not establish '
                           'this alternate name. It is unchecked until you confirm the relationship.',
        }
    return result
