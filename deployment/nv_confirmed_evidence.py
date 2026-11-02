"""Keep the original NV detail name after the existing matcher accepted it."""
import re
from urllib.parse import urlsplit, parse_qs


def preserves_confirmed_detail(result):
    from deployment.lab_identity import trial_identity
    if not trial_identity() or getattr(result, "state", "") != "NV":
        return False
    row = getattr(result, "_cc_license_record", None)
    if (not isinstance(row, dict) or row.get("_identity_outcome") != "accepted"
            or getattr(result, "status_reason", "") != "LICENSED_CHARITY_SOURCE"
            or getattr(result, "success", False) is not True
            or getattr(result, "_cc_identity_review", None)
            or getattr(result, "status", "") in {"Not Registered", "Unable to Confirm", "Needs Review"}):
        return False
    if (not row.get("name") or not re.fullmatch(r"NV\d+", str(row.get("identifier", "")))
            or row["name"] != getattr(result, "matched_registry_name", "")
            or row["identifier"] != getattr(result, "matched_registry_identifier", "")
            or row.get("raw_status") != getattr(result, "raw_status_text", "")
            or row.get("status") != getattr(result, "status", "")
            or row.get("url") != getattr(result, "source_url", "")):
        return False
    try:
        url = urlsplit(row["url"])
        path, _, query = url.fragment.partition("?")
        params = parse_qs(query)
        return bool(url.scheme == "https" and url.netloc == "orion.nv.gov"
            and url.path == "/portal/public/" and not url.query
            and path == "/public/nvsos/en/CaseXscreen"
            and set(params) == {"screen", "id"} and params["screen"] == ["Manage-Business"]
            and len(params["id"]) == 1
            and re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", params["id"][0]))
    except (ValueError, TypeError, KeyError):
        return False
