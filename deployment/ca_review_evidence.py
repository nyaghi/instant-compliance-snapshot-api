"""Capture original CA candidate records without making the identity decision."""
import re
import time
from types import SimpleNamespace


def remember(run, result):
    from deployment.lab_identity import trial_identity
    if not trial_identity() or run is None or run.state != "CA":
        return
    review = getattr(result, "_cc_identity_review", None)
    sources = getattr(result, "_cc_ca_name_sources", None)
    if not isinstance(review, dict) or not isinstance(sources, dict):
        return
    rows = review.get("records")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 5:
        return
    from deployment.source_visual_adapters import remember_ca_selected
    norm = lambda s: re.sub(r"[^a-z0-9]", "", str(s).lower())
    candidates = []
    for row in rows:
        if not isinstance(row, dict) or row.get("_identity_outcome") not in {"possible", "accepted"}:
            continue
        number, name = str(row.get("identifier", "")), row.get("name", "")
        source = sources.get(number, {})
        entity, registrations = source.get("entity"), source.get("registrations")
        if not isinstance(entity, dict) or not isinstance(registrations, list) or not name:
            continue
        ein = re.sub(r"\D", "", str(entity.get("fein") or ""))
        entity_name = entity.get("entityName") or entity.get("legalName") or entity.get("name")
        if (ein and ein != run.ein) or norm(entity_name) != norm(name):
            continue
        proxy = SimpleNamespace(state="CA", success=True, status=row.get("status"),
            matched_registry_identifier=number, matched_registry_name=name,
            _cc_registration_records=registrations, _cc_selected_entity=entity)
        if (row.get("status") == "Exempt" and entity.get("entityStatus") == "Exempt"
                and registrations == [] and str(entity.get("id")) == number
                and re.fullmatch(r"\d+", number) and not ein):
            run.remember_detail(number, name,
                "https://ca-rcf.evokeplatform.com/app/publicPortal/entityDetails/" + number)
            hint = run.source_detail_hints.get(number)
            if hint:
                hint["exempt_entity_review"] = True
        else:
            remember_ca_selected(run, proxy)
        if number in run.source_detail_hints:
            candidates.append(dict(state="CA", ein=run.ein, success=True,
                status=row.get("status"), raw_status_text=row.get("raw_status", ""),
                matched_registry_name=name, matched_registry_identifier=number))
    run.ca_review_candidates = candidates


def capture(master, result, run, deadline):
    """One shared visual allowance for all already retrieved candidates."""
    from deployment.source_visual_adapters import capture_selected_ca_source
    candidates = getattr(run, "ca_review_candidates", [])
    if not candidates or result.get("state") != "CA" or result.get("success") is True:
        return False
    stop = min(deadline, time.monotonic() + 30)
    attempted = getattr(run, "selected_visual_attempted", False)
    if attempted:
        return True
    try:
        for candidate in candidates:
            if stop - time.monotonic() < 4:
                run.errors.append("ca_candidate_capture_deadline")
                break
            run.selected_visual_attempted = False
            capture_selected_ca_source(master, candidate, run, stop)
    finally:
        run.selected_visual_attempted = True
    return True
