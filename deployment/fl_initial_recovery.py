"""Only pre-response transport failures qualify for FL initial-GET recovery."""
from html import unescape
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

def completed_empty_business_query(run, query):
    """Recognize the submitted FDACS Business Lookup form's own empty result."""
    proof = getattr(run, "fl_response_candidate", None)
    if not proof or proof.get("run_id") != run.run_id or proof.get("query") != query:
        return False
    source = proof["html"]
    inputs = re.findall(r'<input\b[^>]*\bid="cpMainContent_BusinessNameTb"[^>]*>', source, re.I)
    if len(inputs) != 1 or re.search(r'captcha|verify you are human|access denied', source, re.I):
        return False
    echoed = re.search(r'\bvalue="([^"]*)"', inputs[0], re.I)
    no_result = re.search(
        r'<span\b[^>]*\bid="cpMainContent_NoResultLb"[^>]*>'
        r'\s*No results found for the search criteria specified\.\s*</span>', source, re.I)
    return bool(echoed and unescape(echoed[1]) == query and no_result)
