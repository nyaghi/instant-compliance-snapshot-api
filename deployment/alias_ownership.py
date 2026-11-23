"""Resolve separate legal entities behind discovered brands and DBA names."""
import json
import re
import time
import threading
from urllib.parse import urlencode

RECORD_CACHE = {}
CACHE_LOCK = threading.Lock()


def records(master, name, deadline, offices=()):
    key = master.normalized_match_name(name)
    compact = re.sub(r"[^A-Z0-9]", "", key.upper())
    words = list(compact)
    if len("".join(words)) < 3 or not words:
        return []
    locations = sorted({(region, postal) for _, region, postal in offices})
    if not locations or len(locations) > 12:
        return []
    cache_key = ("alias-legal-owner", compact, tuple(locations))
    with CACHE_LOCK:
        saved = RECORD_CACHE.get(cache_key)
    if saved and saved[0] > time.time():
        return saved[1]
    if deadline <= time.monotonic():
        return []
    location_where = " OR ".join("(upper(principalstate) = '" + region +
        "' AND principalzipcode like '" + postal + "%')" for region, postal in locations)
    url = "https://data.colorado.gov/resource/37wu-kn3g.json?" + urlencode({
        "$limit": "100", "$where": "upper(name) like '%" + "%".join(words) + "%' AND (" + location_where + ")",
        "$order": "registrationapproveddate DESC",
    })
    data = json.loads(master.identity_fetch(url, deadline, request_timeout=2.0))
    if not isinstance(data, list) or len(data) >= 100:
        return []
    matches = [dict(row, source_url=url) for row in data if isinstance(row, dict)
               and re.sub(r"[^a-z0-9]", "", master.normalized_match_name(str(row.get("name") or ""))) == compact.lower()]
    with CACHE_LOCK:
        if len(RECORD_CACHE) >= 1200:
            RECORD_CACHE.pop(next(iter(RECORD_CACHE)))
        RECORD_CACHE[cache_key] = (time.time() + 300, matches)
    return matches


def office(master, street, region, postal, *, street_key=None):
    street = (street_key or master.registry_street_key)(street)
    region = str(region or "").upper()
    postal = str(postal or "")[:5]
    if not re.match(r"^\d+\s", street) or not re.fullmatch(r"[A-Z]{2}", region) or not re.fullmatch(r"\d{5}", postal):
        return None
    return street, region, postal


def conflict(master, name, ein, offices, deadline, *, street_key=None):
    requested = master.canonical_ein_digits(ein)
    valid_offices = {value for value in offices if value is not None}
    if len(requested) != 9 or not valid_offices:
        return {}
    try:
        matched = [row for row in records(master, name, deadline, valid_offices)
                   if office(master, row.get("principaladdress"), row.get("principalstate"),
                             row.get("principalzipcode"), street_key=street_key) in valid_offices]
    except (OSError, ValueError, TypeError, TimeoutError, RuntimeError):
        return {}
    owners = {master.canonical_ein_digits(str(row.get("fein") or "")) for row in matched}
    # An absent response, conflicting owners or same-EIN evidence cannot prove
    # that an alternate-name record belongs to a different legal entity.
    if len(owners) != 1 or requested in owners or any(len(value) != 9 for value in owners):
        return {}
    return {"decision": "different_ein", "ein": next(iter(owners)), "source": "CO",
            "registry_name": matched[0]["name"], "source_url": matched[0]["source_url"],
            "basis": "The full legal name and street, state and ZIP match official records for a different EIN.",
            "records": matched}


def candidate_conflict(master, org, name, deadline, row=None, *, state=''):
    """Share at most three seconds of added ownership work across one state's rows."""
    budgets = getattr(org, '_cc_alias_ownership_seconds', None)
    if budgets is None:
        budgets = org._cc_alias_ownership_seconds = {}
    started = time.monotonic()
    stop = min(deadline, started + max(0.0, 3.0 - budgets.get(state, 0.0)))
    try:
        return _candidate_conflict(master, org, name, stop, row,
                                   street_key=master.al_ownership_street_key if state == "AL" else None)
    finally:
        budgets[state] = budgets.get(state, 0.0) + time.monotonic() - started


def _candidate_conflict(master, org, name, deadline, row=None, *, street_key=None):
    if (master.normalized_match_name(name) == master.normalized_match_name(org.organization_name)
            or not master.is_reviewed_alias(org.ein, name)):
        return {}
    if row and master.canonical_ein_digits(str(row.get("ein") or "")) == master.canonical_ein_digits(org.ein):
        return {}
    stop = min(deadline, time.monotonic() + 3.0)
    offices = []
    if row:
        offices.append(office(master, row.get("street"), row.get("region"), row.get("postal_code"), street_key=street_key))
    if not any(offices):
        try:
            source = master.identity_source_result("CO", master.canonical_ein_digits(org.ein), stop)
        except (OSError, ValueError, TypeError, TimeoutError, RuntimeError):
            return {}
        offices = [office(master, record.get("street"), record.get("state"), record.get("postal_code"), street_key=street_key)
                   for record in source.get("organization_records", [])
                   if record.get("address_role") == "organization"
                   and master.canonical_ein_digits(str(record.get("ein") or "")) == master.canonical_ein_digits(org.ein)]
    return conflict(master, name, org.ein, offices, stop, street_key=street_key)


def review_discovery(master, names, sources, organization_name, ein, deadline):
    offices = []
    for source in sources:
        for record in source.get("organization_records", []):
            if (record.get("address_role") == "organization"
                    and master.canonical_ein_digits(str(record.get("ein") or "")) == ein):
                offices.append(office(master, record.get("street"), record.get("state"), record.get("postal_code")))
    reviewed = 0
    stop = min(deadline, time.monotonic() + 3.0)
    for item in names:
        if (reviewed >= 3 or time.monotonic() >= stop
                or master.normalized_match_name(item["name"]) == master.normalized_match_name(organization_name)
                or not any(proof.get("type") in {"DBA", "AKA / DBA", "Form 990 DBA", "Other Name"}
                           for proof in item.get("evidence", []))):
            continue
        reviewed += 1
        proof = conflict(master, item["name"], ein, offices, stop)
        if proof:
            item["verified"] = False
            item["identity_conflict"] = {
                "source": "CO", "reason": "Separate legal entity uses this alternate name",
                "candidate_name": proof["registry_name"], "candidate_ein": master.format_ein(proof["ein"]),
                "candidate_location": ", ".join(str(proof['records'][0].get(k) or '') for k in ('principalcity', 'principalstate')),
                "source_url": proof["source_url"],
                "explanation": "This name also identifies a separate legal entity with a different EIN at the same office. Confirm the relationship before using it as an alternate name.",
            }
    return names


def discovery_conflicts(master, sources, organization_name, ein, deadline):
    """Review completed sources while slower discovery sources are still running."""
    # The reverse lookup uses Colorado's offices, including older locations.
    # Do not spend its small allowance before that same-EIN source completes.
    if not any(source.get('source') == 'CO' and source.get('organization_records') for source in sources):
        return {}
    merged = {}
    for source in sources:
        for item in source.get('names', []):
            key = master.identity_name_key(item['name'])
            if key not in merged:
                merged[key] = {**item, 'evidence': list(item.get('evidence', []))}
            else:
                for proof in item.get('evidence', []):
                    if proof not in merged[key]['evidence']:
                        merged[key]['evidence'].append(proof)
    names = list(merged.values())
    review_discovery(master, names, sources, organization_name, ein, deadline)
    return {master.identity_name_key(item['name']): item['identity_conflict']
            for item in names if item.get('identity_conflict', {}).get('reason') ==
            'Separate legal entity uses this alternate name'}
