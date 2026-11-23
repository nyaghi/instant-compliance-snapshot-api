"""Reviewed identity links for two specific California public records.

The registry's currently returned record determines status. These links
reconcile separately documented identifiers without broadening name matching.
"""
import re

# Pepperdine institutional ID sheet:
# https://www.pepperdine.edu/academics/grant-funding/content/institutionaldataaug2025updated.pdf
# California RRF-1 and closure confirmation:
# https://ca-rcf.evokeplatform.com/app/publicPortal/documentDetails/09027b8f804e698a
# https://ca-rcf.evokeplatform.com/app/publicPortal/documentDetails/09027b8f8051798e
PEPPERDINE = ("951644037", "5000736", "941644037")
SAINT_FRANCIS = ("815469765", "6575026", "481059281")


def digits(value):
    return re.sub(r"\D", "", str(value or ""))


def binding(master, name, ein, entity):
    """Require the reviewed federal EIN and exact state entity and office."""
    if not isinstance(entity, dict) or entity.get("entityType") != "Business":
        return None
    key = (digits(ein), str(entity.get("id")), digits(entity.get("fein")))
    address = entity.get("officialAddress") or {}
    if not isinstance(address, dict):
        return None
    office = (
        master.registry_street_key(str(address.get("line1") or "")),
        str(address.get("city") or "").upper(),
        address.get("state"),
        digits(address.get("zipCode"))[:5],
    )
    if key == PEPPERDINE:
        expected = "PEPPERDINE UNIVERSITY"
        if entity.get("sosId") != "0171635" or office != (
                master.registry_street_key("24255 PACIFIC COAST HIGHWAY"), "MALIBU", "CA", "90263"):
            return None
    elif key == SAINT_FRANCIS:
        expected = "SAINT FRANCIS FOUNDATION INC."
        if office != (master.registry_street_key("405 E. IRON AVE."), "SALINA", "KS", "67401"):
            return None
    else:
        return None
    expected_name = master.complete_name_identity_key(expected)
    if (master.complete_name_identity_key(name) != expected_name
            or master.complete_name_identity_key(master.checker.ca_evoke_display_name(entity)) != expected_name):
        return None
    return key


def apply(master, org, result, entities, deadline):
    matches = [(entity, binding(master, org.organization_name, org.ein, entity)) for entity in entities]
    matches = [(entity, key) for entity, key in matches if key]
    if len(matches) != 1:
        return False
    entity, key = matches[0]
    registrations = master.checker.ca_evoke_api_get(
        "/data/objects/registrations/instances",
        {"where": {"entityRelated.id": key[1]}, "limit": 200},
        deadline=deadline,
    )
    if not isinstance(registrations, list):
        return False
    if any(not isinstance(record, dict) for record in registrations):
        return False
    status, raw, identifier, _ = master.checker.ca_evoke_status_from_record(entity, registrations)
    if key == PEPPERDINE:
        if registrations or status != "Exempt" or identifier != key[1]:
            return False
        note = ("Pepperdine's published institutional data links EIN 95-1644037 to California ID 0171635, "
                "which matches the state entity. California lists the entity as Exempt and displays "
                "a conflicting federal EIN, 94-1644037.")
    else:
        if len(registrations) != 1:
            return False
        record = registrations[0]
        if (str(record.get("id")) != "1616276" or (record.get("entityRelated") or {}).get("id") != key[1]
                or record.get("registrationType") != "Charitable Organization"
                or record.get("registrationStatus") != "Not Registered"
                or status != "Closed / Withdrawn / Canceled" or identifier != "CT0261177"):
            return False
        note = ("California's filed RRF-1 for CT0261177 names Saint Francis Foundation and shows its EIN "
                "81-5469765. The entity page displays group-return EIN 48-1059281. California's January 4, "
                "2024 notice confirms file closure. The current registration page says Not Registered.")
    result.status = status
    result.success = True
    result.matched_registry_name = master.checker.ca_evoke_display_name(entity)
    result.matched_registry_identifier = identifier
    result.raw_status_text = raw
    result.source_note = note
    result.identity_anchor = "CA_DOCUMENTED_STATE_ID"
    result._cc_registration_records = registrations
    result._cc_selected_entity = entity
    return True

