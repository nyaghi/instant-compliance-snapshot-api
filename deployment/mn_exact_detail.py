"""Bind an explicit Minnesota exemption or withdrawal to the requested EIN."""
from urllib.parse import parse_qs, urlencode, urlsplit

DETAIL_URL = "https://www.ag.state.mn.us/Charity/Search/CHR_GeneralInfo.asp"
EXPLICIT_STATUSES = {
    "exempt": "Exempt",
    "withdrawn": "Closed / Withdrawn / Canceled",
}


def find(page, ein, trusted_names, name_key, timeout_ms):
    url = DETAIL_URL + "?" + urlencode({"FederalID": ein, "Yr": "CURR", "cmdSearch": "View"})
    response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms())
    actual = urlsplit(page.url)
    if (response is None or response.status != 200 or actual.scheme != "https"
            or actual.netloc != "www.ag.state.mn.us"
            or actual.path.lower() != urlsplit(DETAIL_URL).path.lower()
            or parse_qs(actual.query) != parse_qs(urlsplit(url).query)):
        return None

    fields = page.locator("#content").evaluate("""content => {
        const names = [...content.querySelectorAll("h1")];
        const ids = [...content.querySelectorAll("h6")].filter(node => /^Federal ID#/i.test(node.innerText));
        const statuses = [...content.querySelectorAll("tr")].filter(row =>
            row.cells.length === 2 && row.cells[0].innerText.trim() === "Status");
        if (names.length !== 1 || ids.length !== 1 || statuses.length !== 1) return null;
        return {name: names[0].innerText.trim(), id: ids[0].innerText.trim(),
                status: statuses[0].cells[1].innerText.trim()};
    }""", timeout=timeout_ms())
    if not fields or fields["id"].upper() not in (f"FEDERAL ID# {ein}", f"FEDERAL ID# {ein[:2]}-{ein[2:]}"):
        return None
    status = EXPLICIT_STATUSES.get(fields["status"].casefold())
    trusted_keys = {name_key(name) for name in trusted_names} - {""}
    if not status or name_key(fields["name"]) not in trusted_keys:
        return None
    return fields["name"], status, fields["status"], url
