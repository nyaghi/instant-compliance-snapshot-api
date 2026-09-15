"""Exercise the real report button with captured staging results, without repeating state checks."""
import argparse
import json
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc
from playwright.sync_api import sync_playwright
from pypdf import PdfReader

parser = argparse.ArgumentParser()
parser.add_argument("--live", action="store_true")
parser.add_argument("--input", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()
all_rows = [json.loads(line) for line in Path(args.input).read_text(encoding="utf8").splitlines()]
first_ein = all_rows[0]["ein"]
rows = [r["result"] for r in all_rows if r["ein"] == first_ein]
assert len(rows) == 30
out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
server = None
if not args.live:
    server = ThreadingHTTPServer(("127.0.0.1", 0), cc.RegistrySnapshotHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    local = f"http://127.0.0.1:{server.server_address[1]}"
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(accept_downloads=True, viewport={"width": 1440, "height": 1000})
    requests, errors = [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("request", lambda req: requests.append(req.url))
    page.route("**/api/funnel/event", lambda route: route.fulfill(status=200, content_type="application/json", body="{}"))
    if not args.live:
        html = (Path(__file__).resolve().parents[1] / "web-staging/index.html").read_text(encoding="utf8")
        page.route("https://staging.compliance-express.com/", lambda route: route.fulfill(status=200, content_type="text/html", body=html))
        def api(route):
            request = urllib.request.Request(local + "/api/report", data=route.request.post_data.encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request) as response:
                route.fulfill(status=response.status, content_type=response.headers["Content-Type"], body=response.read())
        page.route("**/api/report", api)
    page.goto("https://staging.compliance-express.com/", wait_until="domcontentloaded")
    assert page.locator("#generateReportButton").is_hidden()
    page.locator("#stagingEmail").fill("staging-smoke@" + cc.EXEMPT_EMAIL_DOMAIN)
    page.locator("#stagingPasscode").fill(cc.ADMIN_PASSCODE)
    page.locator("#stagingUnlockButton").click()
    assert page.locator('label[for="ein"]').inner_text().strip() == 'EIN'
    assert page.locator('#ein').get_attribute('required') is not None
    page.locator('#organizationName').fill('Example Community Foundation')
    page.locator('input[name="states"][value="CO"]').check()
    page.locator('#consent').check()
    for value in ['', '123', '01-234567', '01-23456789', 'ab012345678', '01 2345678']:
        page.locator('#ein').fill(value)
        assert not page.locator('#ein').evaluate('(el) => el.checkValidity()'), value
        page.locator('#snapshotForm').evaluate("el => el.dispatchEvent(new Event('submit', {bubbles:true,cancelable:true}))")
        assert page.get_by_text('Enter the organization’s 9-digit EIN (XX-XXXXXXX).', exact=True).is_visible()
    for value in ['01-2345678','012345678']:
        page.locator('#ein').fill(value)
        assert page.locator('#ein').evaluate('(el) => el.checkValidity()'), value
    assert 'preliminary results for diagnostic purposes only' in page.locator('body').inner_text()
    page.locator('#ein').scroll_into_view_if_needed()
    page.screenshot(path=str(out / 'required-ein.png'))
    page.evaluate("(rows) => renderResults(rows)", rows)
    started = time.perf_counter()
    with page.expect_download(timeout=45000) as event:
        page.locator("#generateReportButton").click()
    download = event.value
    target = out / "CharityClarity-Make-A-Wish-staging.pdf"
    download.save_as(target)
    reader = PdfReader(target)
    assert 5 <= len(reader.pages) <= 24
    for index,pdfpage in enumerate(reader.pages,1):
        assert f"{index} / {len(reader.pages)}" in pdfpage.extract_text()
    assert sum(url.endswith("/api/report") for url in requests) == 1
    assert not any("/api/check" in url for url in requests)
    assert not errors, errors
    text = "\n".join(p.extract_text() for p in reader.pages)
    assert "LA: scheduled download" in text and "OR: scheduled download" in text
    assert 'Operational Insights' in text and 'Downloadable data freshness' not in text
    page.locator("#generateReportButton").scroll_into_view_if_needed()
    page.screenshot(path=str(out / "report-button.png"))
    result = dict(live=args.live, pages=len(reader.pages), seconds=round(time.perf_counter()-started, 2), report_requests=1, state_lookups=0, javascript_errors=errors, file=download.suggested_filename)
    (out / "report-web-smoke.json").write_text(json.dumps(result, indent=2), encoding="utf8")
    print(json.dumps(result))
    browser.close()
if server:
    server.shutdown(); server.server_close()
