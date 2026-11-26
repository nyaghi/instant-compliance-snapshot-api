"""Bind an explicit Minnesota exemption or withdrawal to the requested EIN."""
import re
from urllib.parse import parse_qs, urlencode, urlsplit

DETAIL_URL = "https://www.ag.state.mn.us/Charity/Search/CHR_GeneralInfo.asp"
EXPLICIT_STATUSES = {
    "exempt": "Exempt",
    "withdrawn": "Closed / Withdrawn / Canceled",
    "undefined": "Delinquent",
}



def _legacy_abbreviation(registry_name, trusted_names, name_key):
    """Compare a registry acronym only after the detail supplies the exact EIN."""
    def parts(name):
        return re.split(r"\s*[-–—]\s*", name, maxsplit=1)

    target = parts(registry_name)
    if (len(target) != 2 or len(name_key(target[0]).split()) < 3
            or not re.fullmatch(r"[A-Z]{3,8}", target[1])):
        return False
    for reviewed in trusted_names:
        base = parts(reviewed)
        if len(base) != 2 or name_key(base[0]) != name_key(target[0]):
            continue
        tokens = re.findall(r"[A-Za-z]+", base[1])
        if len(tokens) >= 3 and "".join(word[0].upper() for word in tokens) == target[1]:
            return True
    return False

def find(page, ein, trusted_names, name_key, timeout_ms):
    url = DETAIL_URL + "?" + urlencode({"FederalID": ein, "Yr": "CURR", "cmdSearch": "View"})
    response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms())
    actual = urlsplit(page.url)
    if response is None or response.status in (403, 408, 429) or response.status >= 500:
        raise TimeoutError("Minnesota exact-EIN detail did not return a usable response")
    if (response.status != 200 or actual.scheme != "https"
            or actual.netloc != "www.ag.state.mn.us"
            or actual.path.lower() != urlsplit(DETAIL_URL).path.lower()
            or parse_qs(actual.query) != parse_qs(urlsplit(url).query)):
        return None

    fields = page.locator("#content").evaluate(r"""content => {
        const names = [...content.querySelectorAll("h1")];
        const ids = [...content.querySelectorAll("h6")].filter(node => /^Federal ID#/i.test(node.innerText));
        const statuses = [...content.querySelectorAll("tr")].filter(row =>
            row.cells.length === 2 && row.cells[0].innerText.trim() === "Status");
        const periods = [...content.querySelectorAll("h4")].filter(node =>
            /^For Fiscal Year Ending\b/i.test(node.innerText.trim()));
        if (names.length !== 1 || ids.length !== 1 || statuses.length !== 1) return null;
        return {name: names[0].innerText.trim(), id: ids[0].innerText.trim(),
                status: statuses[0].cells[1].innerText.trim(),
                emptyPeriod: periods.length === 1 && /^For Fiscal Year Ending$/i.test(periods[0].innerText.trim())};
    }""", timeout=timeout_ms())
    if not fields or fields["id"].upper() not in (f"FEDERAL ID# {ein}", f"FEDERAL ID# {ein[:2]}-{ein[2:]}"):
        return None
    raw_status = fields["status"].casefold()
    status = EXPLICIT_STATUSES.get(raw_status)
    if raw_status == "undefined" and not fields["emptyPeriod"]:
        return None
    def identity_key(name):
        # Only after the detail itself has shown the exact requested EIN.
        return name_key(re.sub(r"(?<=\w)['’](?=s\b)", "", name, flags=re.I))
    names = [name for name in trusted_names if isinstance(name, str)]
    trusted_keys = {identity_key(name) for name in names} - {""}
    if not status:
        return None
    if identity_key(fields["name"]) not in trusted_keys and not _legacy_abbreviation(fields["name"], names, identity_key):
        return None
    return fields["name"], status, fields["status"], url


def unavailable(result):
    result.status = "Site Not Reachable"
    result.reason_code = "MN_EXACT_DETAIL_UNAVAILABLE"
    result.raw_status_text = "Exact-EIN detail unavailable"
    result.source_note = ("Minnesota’s search listed no qualifying match, but its current detail for the "
                          "requested EIN could not be checked. Retry Minnesota to verify the registration.")
    result.success = False
    result.error = ""
    return result
