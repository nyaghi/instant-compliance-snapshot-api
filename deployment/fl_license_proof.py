"""Short-lived proof of a legacy FDACS license verified in this staged browser."""

import base64
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import hmac
import json
import re
import time

DAY = 86_400
LICENSE = re.compile(r"CH[0-9]{1,12}")
CONCLUSIVE = {"Current", "Upcoming Filing", "Delinquent", "Exempt", "Suspended", "Revoked",
              "Closed / Withdrawn / Canceled / Inactive"}
PROOF = ContextVar("fl_verified_license", default=None)
LEGACY = {
    "https://csapp.fdacs.gov/CSPublicApp/CheckACharity/CheckACharity.aspx",
    "https://csapp.fdacs.gov/CSPublicApp/BusinessSearch/BusinessSearch.aspx",
}


def _mac(master, purpose, message):
    return hmac.new(master.NY_CONNECTOR_SIGNING_KEY.encode(), purpose + b"." + message,
                    hashlib.sha256).hexdigest()


def _owner(master, owner):
    return _mac(master, b"cc-fl-license-owner-v1", json.dumps(owner, separators=(",", ":")).encode())


def _license(value):
    return isinstance(value, str) and LICENSE.fullmatch(value) is not None


def _ein(value):
    return value.replace("-", "") if isinstance(value, str) and re.fullmatch(r"[0-9]{2}-?[0-9]{7}", value) else ""


def issue(master, record, result):
    """Sign identity only. Expiration and status must always come from a fresh reply."""
    name = result.get("matched_registry_name")
    identifier = result.get("matched_registry_identifier")
    checked = result.get("evidence_captured_at")
    now = time.time()
    if (record["mode"] != "standard" or result.get("state") != "FL" or result.get("success") is not True
            or result.get("confirmation_required") or result.get("identity_review")
            or result.get("status") not in CONCLUSIVE
            or result.get("source_url") not in LEGACY
            or result.get("reason_code") not in {"MATCH_NAME_EXACT", "MATCH_EIN_EXACT"}
            or not (_ein(result.get("ein")) == record["ein"] and _license(identifier))
            or not isinstance(name, str) or not 1 <= len(name) <= 300
            or not master.complete_name_identity_key(name)
            or master.complete_name_identity_key(name) != master.complete_name_identity_key(record["name"])
            or not re.fullmatch(r"/state-snapshots/[0-9a-f]{64}\.pdf", result.get("evidence_url") or "")
            or type(checked) not in (int, float) or not max(now - DAY, record["issued"] - 5) <= checked <= now + 30):
        return None
    proof = {"owner": _owner(master, record["owner"]), "ein": record["ein"],
             "name": name, "id": identifier, "expires": int(min(now, checked)) + DAY}
    body = base64.urlsafe_b64encode(json.dumps(proof, separators=(",", ":")).encode()).rstrip(b"=")
    token = body.decode() + "." + _mac(master, b"cc-fl-license-v1", body)
    return {"token": token, "id": identifier, "expires": proof["expires"]}


def verify(master, token, owner, name, ein):
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,1400}\.[a-f0-9]{64}", token):
        return None
    body, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(signature, _mac(master, b"cc-fl-license-v1", body.encode())):
        return None
    try:
        proof = json.loads(base64.b64decode(body + "=" * (-len(body) % 4), altchars=b"-_", validate=True))
        now = time.time()
        if (proof["owner"] == _owner(master, owner) and proof["ein"] == _ein(ein)
                and type(proof["expires"]) is int and now < proof["expires"] <= now + DAY
                and _license(proof["id"]) and master.complete_name_identity_key(proof["name"])
                == master.complete_name_identity_key(name)):
            return {key: proof[key] for key in ("ein", "name", "id", "expires")}
    except (KeyError, ValueError, TypeError, AttributeError):
        pass
    return None


@contextmanager
def use(proof):
    token = PROOF.set(proof)
    try:
        yield
    finally:
        PROOF.reset(token)
