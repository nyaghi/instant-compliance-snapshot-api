"""Only pre-response transport failures qualify for FL initial-GET recovery."""
import re

_CODES = {"ERR_TIMED_OUT", "ERR_CONNECTION_TIMED_OUT", "ERR_CONNECTION_RESET",
          "ERR_CONNECTION_CLOSED", "ERR_CONNECTION_REFUSED", "ERR_EMPTY_RESPONSE"}

def initial_transport_failure(exc):
    if isinstance(exc, TimeoutError):
        return True
    if type(exc).__name__ == "TimeoutError" and type(exc).__module__.startswith("playwright."):
        return True
    match = re.search(r"net::(ERR_[A-Z0-9_]+)", str(exc))
    return bool(match and match[1] in _CODES)
