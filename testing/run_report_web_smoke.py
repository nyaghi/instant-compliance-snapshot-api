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
    page.evaluate("(rows) => renderResults(rows)", rows)
    started = time.perf_counter()
    with page.expect_download(timeout=45000) as event:
        page.locator("#generateReportButton").click()
    download = event.value
    target = out / "CharityClarity-Make-A-Wish-staging.pdf"
    download.save_as(target)
    reader = PdfReader(target)
    assert len(reader.pages) == 5
    assert sum(url.endswith("/api/report") for url in requests) == 1
    assert not any("/api/check" in url for url in requests)
    assert not errors, errors
    text = "\n".join(p.extract_text() for p in reader.pages)
    assert "LA: downloaded" in text and "OR: downloaded" in text
    page.locator("#generateReportButton").scroll_into_view_if_needed()
    page.screenshot(path=str(out / "report-button.png"))
    result = dict(live=args.live, pages=5, seconds=round(time.perf_counter()-started, 2), report_requests=1, state_lookups=0, javascript_errors=errors, file=download.suggested_filename)
    (out / "report-web-smoke.json").write_text(json.dumps(result, indent=2), encoding="utf8")
    print(json.dumps(result))
    browser.close()
if server:
    server.shutdown(); server.server_close()
