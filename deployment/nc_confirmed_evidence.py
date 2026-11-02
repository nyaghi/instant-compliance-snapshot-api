"""Preserve selected NC identity independently of unresolved source standing."""
import re
from urllib.parse import urlsplit


def preserves_confirmed_record(result):
    from deployment.lab_identity import trial_identity
    if not trial_identity() or getattr(result, "state", "") != "NC":
        return False
    if (getattr(result, "status_reason", "") != "LICENSED_CHARITY_SOURCE"
            or getattr(result, "status", "") != "Unable to Confirm"
            or getattr(result, "_cc_identity_review", None)):
        return False
    row = getattr(result, "_cc_license_record", None)
    if not isinstance(row, dict) or row.get("_identity_outcome") != "accepted":
        return False
    if (not row.get("name") or not re.fullmatch(r"(?:SL|EX)\d+", str(row.get("identifier", "")))
            or row.get("name") != getattr(result, "matched_registry_name", "")
            or row.get("identifier") != getattr(result, "matched_registry_identifier", "")
            or row.get("raw_status") != getattr(result, "raw_status_text", "")
            or row.get("status") != getattr(result, "status", "")
            or row.get("url") != getattr(result, "source_url", "")):
        return False
    try:
        url = urlsplit(row["url"])
        return (url.scheme == "https" and url.netloc == "www.sosnc.gov"
                and re.fullmatch(r"/online_services/search/charities_profile/\d+", url.path) is not None
                and not url.query and not url.fragment)
    except (ValueError, TypeError):
        return False
