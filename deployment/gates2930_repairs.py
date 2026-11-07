"""Narrow state-specific decisions. No network or organization-specific rules."""
import re


def co_expired_restriction(text):
    """An explicit Expired restriction is not an explicit suspension."""
    if re.search(r'\b(?:suspended|revoked|cease\s+and\s+desist)\b', text or '', re.I):
        return ''
    match = re.search(r'\bExpired\s*[-\u2013\u2014:]\s*may\s+not\s+solicit\b(?:\s+as\s+of\s+\d{1,2}/\d{1,2}/\d{4})?', text or '', re.I)
    return match.group(0) if match else ''


def wi_literal_core_plan(original, required, direct):
    """Replace one optional spelling with a dotted legal-name core; same cap."""
    core = re.sub(r'(?:,?\s+)(?:incorporated|inc\.?|corporation|corp\.?|llc|ltd\.?)\s*$', '', original or '', flags=re.I).strip(' ,')
    if core == original or not re.search(r'[A-Za-z]{2,}\.[A-Za-z]{2,}', core):
        return direct
    mandatory = {v.casefold() for v in required}
    optional = [i for i, value in enumerate(direct) if value.casefold() not in mandatory]
    if not optional:
        return direct
    revised = list(direct)
    existing = next((i for i,v in enumerate(direct) if v.casefold()==core.casefold()),None)
    if existing is not None:
        if existing in optional:
            revised[optional[0]],revised[existing]=revised[existing],revised[optional[0]]
    else:
        revised[optional[0]] = core
    return revised


def sc_finish_deadline(stop, deadline, now):
    """After successful source navigation only, finish within a bounded reserve."""
    if 0 < stop-now < 8 and deadline-now > 4:
        return min(stop+5, deadline-1)
    return stop


def il_source_identity(result, selected, canonical):
    """Retain verified source heading before public display-name cleanup."""
    if (result.state != 'IL' or not selected or not result.success
            or str(selected.get('identifier','')) != str(result.matched_registry_identifier)
            or not selected.get('name') or selected.get('_identity_outcome') != 'accepted'):
        return None
    selected_ein = canonical(selected.get('ein',''))
    if selected_ein and selected_ein != canonical(result.ein):
        return None
    return {'ein':canonical(result.ein),'identifier':str(selected['identifier']),
            'name':selected['name'],'state':'IL'}
def tn_historical_prefix(targets, candidate):
    """A complete multiword reviewed prefix permits detail review, never acceptance."""
    def words(value):
        value = re.sub(r"\b(?:incorporated|inc|corporation|corp|limited|ltd)\.?\s*$", "", value.strip(), flags=re.I)
        return re.findall(r"[a-z0-9]+", value.casefold())
    actual = words(candidate)
    for target in targets:
        core = words(target)
        if len(core) >= 3 and len(actual) > len(core) and actual[:len(core)] == core:
            return True
    return False


def tn_possessive_plan(required, generated):
    """Replace optional probes only; preserve query count and every reviewed literal."""
    output = list(generated)
    additions = []
    primary = re.sub(r'[^a-z0-9]','',required[0].casefold()) if required else ''
    for target in required[1:]:
        if re.sub(r'[^a-z0-9]','',target.casefold()) == primary:
            continue
        core = re.sub(r"[,\s]+(?:incorporated|inc|corporation|corp|limited|ltd)\.?$", "", target.strip(), flags=re.I)
        words = re.findall(r"[A-Za-z]+", core)
        if len(words) < 3 or re.search(r"['’]", core):
            continue
        # Literal Contains needs the plural possessive inside a reviewed phrase.
        for hit in re.finditer(r"\b[A-Za-z]{3,}(?<!s)s(?=\s+[A-Za-z])", core, re.I):
            variant = core[:hit.end()] + "'" + core[hit.end():]
            if variant.casefold() not in {v.casefold() for v in [*required,*output,*additions]}:
                additions.append(variant)
    # At most one optional punctuation probe; ordinary names remain unchanged.
    if additions and output:
        # Replace only a redundant literal-Contains probe: another retained
        # query already covers every result it could return. Never sacrifice
        # an independent spelling or reviewed name to make room.
        redundant = [i for i,value in enumerate(output) if any(
            other.casefold() != value.casefold() and other.casefold() in value.casefold()
            for other in [*required,*output])]
        if redundant:
            output.pop(redundant[-1])
            output.insert(0, additions[0])
    return output


def tn_primary_over_alias(org, accepted, possible, conflicts, normalize, street_key, digits):
    if conflicts or len(accepted) != 1 or not possible:
        return False
    primary = accepted[0]
    if normalize(primary.get('name','')) != normalize(org.organization_name):
        return False
    same_ein = len(digits(org.ein)) == 9 and digits(primary.get('ein','')) == digits(org.ein)
    proof = primary.get('address_evidence') or {}
    full_office = any(r.get('address_role') == 'organization' and digits(r.get('ein','')) == digits(org.ein)
        and street_key(r.get('street')) and street_key(r.get('street')) == street_key(primary.get('street'))
        and str(r.get('state','')).upper() == str(primary.get('region','')).upper()
        and re.fullmatch(r'\d{5}', str(primary.get('postal_code',''))[:5])
        and str(r.get('postal_code',''))[:5] == str(primary.get('postal_code',''))[:5]
        for r in proof.get('cross_state_records', []))
    if not same_ein and not full_office:
        return False
    return all(r.get('match',{}).get('reason') == 'ALIAS_IDENTITY_UNCONFIRMED'
        and normalize(r.get('name','')) != normalize(org.organization_name)
        and not set(normalize(r.get('name','')).split()) & set(normalize(org.organization_name).split())
        for r in possible)
