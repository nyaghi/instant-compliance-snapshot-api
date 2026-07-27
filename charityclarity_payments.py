from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import string
import time
import urllib.error
import urllib.parse
import urllib.request


STRIPE_API_VERSION = "2026-06-24.dahlia"


class StripeCheckoutError(RuntimeError):
    pass


def _random_letters(length: int = 8) -> str:
    alphabet = string.ascii_lowercase
    return "".join(secrets.choice(alphabet) for _ in range(length))


def integration_identifier(prefix: str = "charityclarity_ad") -> str:
    safe_prefix = "".join(char for char in prefix.lower() if char.isalnum() or char == "_").strip("_")
    return f"{safe_prefix or 'charityclarity'}_{_random_letters(8)}"


def checkout_session_form(
    *,
    price_id: str,
    success_url: str,
    cancel_url: str,
    customer_email: str = "",
    client_reference_id: str = "",
    metadata: dict[str, str] | None = None,
) -> dict[str, str]:
    form = {
        "mode": "payment",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "integration_identifier": integration_identifier(),
    }
    if customer_email:
        form["customer_email"] = customer_email[:320]
    if client_reference_id:
        form["client_reference_id"] = client_reference_id[:200]
    for key, value in (metadata or {}).items():
        safe_key = "".join(char for char in str(key) if char.isalnum() or char in "_-")[:40]
        safe_value = str(value or "").strip()[:500]
        if safe_key and safe_value:
            form[f"metadata[{safe_key}]"] = safe_value
    return form


def create_checkout_session(api_key: str, form: dict[str, str], timeout_seconds: float = 12.0) -> dict:
    if not api_key:
        raise StripeCheckoutError("Stripe API key is not configured.")
    body = urllib.parse.urlencode(form).encode("utf-8")
    token = base64.b64encode(f"{api_key}:".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        "https://api.stripe.com/v1/checkout/sessions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Basic {token}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Stripe-Version": STRIPE_API_VERSION,
            "User-Agent": "CharityClarity/stripe-checkout",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
            message = detail.get("error", {}).get("message") or "Stripe rejected the checkout request."
        except Exception:
            message = "Stripe rejected the checkout request."
        raise StripeCheckoutError(message) from exc
    except Exception as exc:
        raise StripeCheckoutError("Stripe checkout is temporarily unavailable.") from exc


def parse_stripe_signature(header: str) -> tuple[int, list[str]]:
    timestamp = 0
    signatures: list[str] = []
    for part in str(header or "").split(","):
        name, _, value = part.partition("=")
        if name == "t":
            try:
                timestamp = int(value)
            except ValueError:
                timestamp = 0
        elif name == "v1" and value:
            signatures.append(value)
    return timestamp, signatures


def verify_stripe_signature(
    payload: bytes,
    header: str,
    secret: str,
    *,
    now: int | None = None,
    tolerance_seconds: int = 300,
) -> bool:
    if not payload or not header or not secret:
        return False
    timestamp, signatures = parse_stripe_signature(header)
    if not timestamp or not signatures:
        return False
    current = int(time.time() if now is None else now)
    if abs(current - timestamp) > tolerance_seconds:
        return False
    signed = f"{timestamp}.".encode("utf-8") + payload
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, signature) for signature in signatures)
