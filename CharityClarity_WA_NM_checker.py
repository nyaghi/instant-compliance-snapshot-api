#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("Install Playwright first: py -m pip install playwright && py -m playwright install", file=sys.stderr)
    raise

try:
    from curl_cffi import requests as curl_requests
except Exception:
    curl_requests = None


WA_SEARCH_URL = "https://ccfs.sos.wa.gov/#/cftSearch"
WA_SEARCH_API_FRAGMENT = "CFTPublicSearch/GetCFPublicSearchList"
NM_SEARCH_URL = "https://secure.nmdoj.gov/CharitySearch/"
BUNDLED_PDF_PYTHON = (
    Path.home()
    / ".cache"
    / "codex-runtimes"
    / "codex-primary-runtime"
    / "dependencies"
    / "python"
    / "python.exe"
)

STATUS_UNKNOWN = "Unknown"
STATUS_NOT_REGISTERED = "Not registered"
STATUS_CURRENT = "Current"
STATUS_UPCOMING = "Upcoming Filing"
STATUS_DELINQUENT = "Delinquent"
STATUS_PENDING = "Pending"
STATUS_CLOSED = "Closed / Withdrawn / Canceled"


@dataclass
class Organization:
    organization_name: str
    ein: str


@dataclass
class SearchResult:
    organization_name: str
    ein: str
    state: str
    status: str
    raw_status_text: str
    source_url: str
    source_note: str
    success: bool = False
    error: str = ""
    matched_registry_name: str = ""
    matched_registry_identifier: str = ""


def digits_only(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def format_ein(value: str) -> str:
    digits = digits_only(value)
    if len(digits) == 8:
        digits = f"0{digits}"
    if len(digits) == 9:
        return f"{digits[:2]}-{digits[2:]}"
    return (value or "").strip()


def normalize_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", value or "").strip().upper()
    return re.sub(r"\s+", " ", cleaned)


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_date(value: str) -> Optional[date]:
    value = (value or "").strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except Exception:
            continue
    return None


def add_months(d: date, months: int) -> date:
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    mdays = [
        31,
        29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ]
    day = min(d.day, mdays[month - 1])
    return date(year, month, day)


def safe_wait_for_network_idle(page, timeout: int = 25000) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass


def print_result(result: SearchResult) -> None:
    print(f"Organization: {result.organization_name}")
    print(f"EIN: {result.ein}")
    print(f"State: {result.state}")
    print(f"Status: {result.status}")
    print(f"Raw Status: {result.raw_status_text}")
    print(f"Source URL: {result.source_url}")
    print(f"Source Note: {result.source_note}")
    if result.error:
        print(f"Error: {result.error}")


def launch_context(playwright, show_process: bool):
    browser = playwright.chromium.launch(
        headless=not show_process,
        slow_mo=500 if show_process else 0,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
        ],
    )
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1440, "height": 1100},
        locale="en-US",
        accept_downloads=True,
    )
    context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        """
    )
    return browser, context


def extract_label(text: str, label: str) -> str:
    patterns = [
        rf"{re.escape(label)}\s*[:\-]\s*([^\n\r|]+)",
        rf"{re.escape(label)}\s*\n\s*([^\n\r]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return normalize_spaces(match.group(1))
    return ""


def terminal_closed_status_text(text: str) -> str:
    match = re.search(
        r"\b(Involuntarily\s+Closed|Administratively\s+Closed|Closed|Withdrawn|Terminated|Dissolved|Revoked|Cancel(?:ed|led))\b",
        text or "",
        re.I,
    )
    return normalize_spaces(match.group(1)) if match else ""


def classify_by_renewal(renewal: Optional[date], raw_status: str, detail_text: str = "") -> str:
    normalized = " ".join([raw_status or "", detail_text or ""]).strip().lower()
    if terminal_closed_status_text(normalized):
        return STATUS_CLOSED
    if "pending" in normalized:
        return STATUS_PENDING
    if not renewal:
        return STATUS_UNKNOWN
    today = date.today()
    six_months = today + timedelta(days=183)
    if renewal < today:
        return STATUS_DELINQUENT
    if renewal <= six_months:
        return STATUS_UPCOMING
    return STATUS_CURRENT


def switch_to_fein_mode(page) -> None:
    for candidate in [
        page.get_by_text("FEIN Number", exact=True),
        page.locator("input[value='FEINNo']").first,
        page.locator("label").filter(has_text=re.compile(r"FEIN Number", re.I)).first,
    ]:
        try:
            candidate.click(timeout=5000, force=True)
            time.sleep(1)
            return
        except Exception:
            continue

    page.evaluate(
        """
        () => {
          const feinRadio = document.querySelector("input[value='FEINNo']");
          if (feinRadio) {
            feinRadio.checked = true;
            feinRadio.dispatchEvent(new Event('click', { bubbles: true }));
            feinRadio.dispatchEvent(new Event('change', { bubbles: true }));
          }
        }
        """
    )
    time.sleep(1)


def fill_fein_and_search(page, ein: str) -> bool:
    try:
        page.locator("#txtKeywordSearch").first.fill("")
    except Exception:
        pass

    fein_box = page.locator("#FEINNoSearchField").first
    fein_box.wait_for(state="visible", timeout=10000)
    fein_box.click(timeout=5000, force=True)
    time.sleep(1)
    fein_box.fill("")
    fein_box.type(digits_only(ein), delay=50)
    page.evaluate(
        """
        () => {
          const feinBox = document.querySelector('#FEINNoSearchField');
          if (feinBox) {
            feinBox.dispatchEvent(new Event('input', { bubbles: true }));
            feinBox.dispatchEvent(new Event('change', { bubbles: true }));
          }
        }
        """
    )
    time.sleep(1)

    for candidate in [
        page.get_by_role("button", name=re.compile(r"^Search$", re.I)),
        page.locator("button").filter(has_text=re.compile(r"^Search$", re.I)).first,
        page.locator("input[value='Search']").first,
    ]:
        try:
            candidate.click(timeout=5000, force=True)
            return True
        except Exception:
            continue
    return False


def switch_to_name_mode(page) -> None:
    for candidate in [
        page.get_by_text(re.compile(r"Organization\s+Name|Charity\s+Name|Business\s+Name|Name", re.I)).first,
        page.locator("label").filter(has_text=re.compile(r"Organization\s+Name|Charity\s+Name|Business\s+Name|Name", re.I)).first,
        page.locator("input[value='OrgName']").first,
        page.locator("input[value='OrganizationName']").first,
        page.locator("input[value='Name']").first,
    ]:
        try:
            candidate.click(timeout=3000, force=True)
            time.sleep(1)
            return
        except Exception:
            continue

    page.evaluate(
        """
        () => {
          const radios = Array.from(document.querySelectorAll("input[type='radio']"));
          const nameRadio = radios.find((radio) => {
            const value = String(radio.value || radio.id || radio.name || "");
            const label = radio.id ? String(document.querySelector(`label[for="${radio.id}"]`)?.textContent || "") : "";
            return /org|organization|charity|business|name/i.test(value + " " + label)
              && !/fein|ein/i.test(value + " " + label);
          });
          if (nameRadio) {
            nameRadio.checked = true;
            nameRadio.dispatchEvent(new Event('click', { bubbles: true }));
            nameRadio.dispatchEvent(new Event('change', { bubbles: true }));
          }
        }
        """
    )
    time.sleep(1)


def fill_name_and_search(page, org_name: str) -> bool:
    try:
        page.locator("#FEINNoSearchField").first.fill("")
    except Exception:
        pass

    name_box = page.locator("#txtKeywordSearch").first
    name_box.wait_for(state="visible", timeout=10000)
    name_box.click(timeout=5000, force=True)
    time.sleep(1)
    name_box.fill("")
    name_box.type(org_name, delay=35)
    page.evaluate(
        """
        () => {
          const nameBox = document.querySelector('#txtKeywordSearch');
          if (nameBox) {
            nameBox.dispatchEvent(new Event('input', { bubbles: true }));
            nameBox.dispatchEvent(new Event('change', { bubbles: true }));
          }
        }
        """
    )
    time.sleep(1)

    for candidate in [
        page.get_by_role("button", name=re.compile(r"^Search$", re.I)),
        page.locator("button").filter(has_text=re.compile(r"^Search$", re.I)).first,
        page.locator("input[value='Search']").first,
    ]:
        try:
            candidate.click(timeout=5000, force=True)
            return True
        except Exception:
            continue
    return False


def wa_name_fallback_result_link(page, org: Organization):
    name_tokens = re.findall(r"[A-Za-z0-9]+", org.organization_name or "")
    if len(name_tokens) == 1 and 2 <= len(name_tokens[0]) <= 3:
        return None
    switch_to_name_mode(page)
    if not fill_name_and_search(page, org.organization_name):
        return None
    safe_wait_for_network_idle(page, timeout=8000)
    time.sleep(1)
    found = wait_for_result_link_or_no_value(page, org.organization_name, timeout_seconds=18, require_search_response=True)
    return None if found == "NO_VALUE" else found


def scroll_to_results(page) -> None:
    for _ in range(3):
        try:
            page.locator("text=SEARCH RESULTS").first.scroll_into_view_if_needed(timeout=3000)
            time.sleep(1)
            return
        except Exception:
            try:
                page.mouse.wheel(0, 1200)
            except Exception:
                pass
            time.sleep(1)


def latest_date_ordinal_from_text(value: str) -> int:
    dates = []
    for match in re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", value or ""):
        parsed = parse_date(match)
        if parsed:
            dates.append(parsed.toordinal())
    return max(dates) if dates else 0


def wa_row_status_priority(value: str) -> int:
    text = normalize_spaces(value).upper()
    if re.search(r"\b(ACTIVE|CURRENT|YES)\b", text):
        return 4
    if re.search(r"\b(PENDING|MERGED)\b", text):
        return 3
    if re.search(r"\bDELINQUENT\b", text):
        return 2
    if re.search(r"\b(INVOLUNTARILY\s+CLOSED|CLOSED|WITHDRAWN|TERMINATED|DISSOLVED|REVOKED|CANCEL(?:ED|LED)|NO)\b", text):
        return 1
    return 0


def install_wa_search_tracker(page) -> None:
    page.evaluate(
        f"""
        () => {{
          if (window.__ceWaSearchTrackerInstalled) return;
          window.__ceWaSearchTrackerInstalled = true;
          window.__ceWaSearch = {{
            pending: 0,
            started: 0,
            completed: 0,
            failed: 0,
            lastStatus: 0,
            lastText: "",
            lastError: "",
            lastFinishedAt: 0
          }};
          const fragment = {WA_SEARCH_API_FRAGMENT!r};
          const matches = (url) => String(url || "").indexOf(fragment) !== -1;
          const originalOpen = XMLHttpRequest.prototype.open;
          const originalSend = XMLHttpRequest.prototype.send;
          XMLHttpRequest.prototype.open = function(method, url) {{
            this.__ceWaUrl = String(url || "");
            return originalOpen.apply(this, arguments);
          }};
          XMLHttpRequest.prototype.send = function(body) {{
            const isWaSearch = matches(this.__ceWaUrl);
            if (isWaSearch) {{
              const tracker = window.__ceWaSearch;
              tracker.pending += 1;
              tracker.started += 1;
              this.addEventListener("loadend", function() {{
                tracker.pending = Math.max(0, tracker.pending - 1);
                tracker.completed += 1;
                tracker.lastStatus = this.status || 0;
                tracker.lastText = String(this.responseText || "").slice(0, 200000);
                tracker.lastFinishedAt = Date.now();
              }}, {{ once: true }});
              this.addEventListener("error", function() {{
                tracker.failed += 1;
                tracker.lastError = "xhr error";
              }}, {{ once: true }});
              this.addEventListener("timeout", function() {{
                tracker.failed += 1;
                tracker.lastError = "xhr timeout";
              }}, {{ once: true }});
              this.addEventListener("abort", function() {{
                tracker.failed += 1;
                tracker.lastError = "xhr abort";
              }}, {{ once: true }});
            }}
            return originalSend.apply(this, arguments);
          }};
        }}
        """
    )


def wa_search_tracker_state(page) -> dict:
    try:
        state = page.evaluate(
            """
            () => {
              const tracker = window.__ceWaSearch || {};
              return {
                pending: tracker.pending || 0,
                started: tracker.started || 0,
                completed: tracker.completed || 0,
                failed: tracker.failed || 0,
                lastStatus: tracker.lastStatus || 0,
                lastText: tracker.lastText || "",
                lastError: tracker.lastError || "",
                lastFinishedAt: tracker.lastFinishedAt || 0
              };
            }
            """
        )
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def wa_search_response_is_empty(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    try:
        payload = json.loads(text)
    except Exception:
        return bool(re.search(r"No\s+Value\s+Found|records\s+0\s+to\s+0\s+of\s+0|TotalRowCount[\"']?\s*[:=]\s*0", text, re.I))
    if isinstance(payload, list):
        if not payload:
            return True
        for item in payload:
            if isinstance(item, dict):
                criteria = item.get("Criteria") or {}
                try:
                    if int(criteria.get("TotalRowCount", -1)) > 0:
                        return False
                except Exception:
                    pass
        return False
    return False


def find_result_link(page, org_name: str):
    target = normalize_name(org_name)
    target_words = target.split()
    candidates = []
    locator_sets = ["table a", "tbody a", "a"]

    for locator_selector in locator_sets:
        try:
            links = page.locator(locator_selector)
            count = min(links.count(), 150)
        except Exception:
            continue

        for i in range(count):
            link = links.nth(i)
            try:
                if not link.is_visible(timeout=500):
                    continue
            except Exception:
                continue
            try:
                role = (link.get_attribute("role") or "").strip().lower()
                href = (link.get_attribute("href") or "").strip()
                text = normalize_spaces(link.inner_text(timeout=1000))
            except Exception:
                continue
            if not text:
                continue
            upper = text.upper()
            if role == "menuitem":
                continue
            if "RETURN TO HOME" in upper or upper in {"SEARCH", "CLEAR"}:
                continue
            if href.startswith("javascript:__doPostBack") or href == "" or locator_selector != "a":
                priority = 0
                normalized = normalize_name(text)
                row_text = text
                try:
                    row = link.locator("xpath=ancestor::tr[1]")
                    if row.count():
                        row_text = normalize_spaces(row.first.inner_text(timeout=1000))
                except Exception:
                    row_text = text
                row_normalized = normalize_name(row_text)
                if target:
                    if normalized == target or row_normalized == target:
                        priority = 3
                    elif len(target_words) >= 3 and (
                        normalized.startswith(f"{target} ")
                        or row_normalized.startswith(f"{target} ")
                    ):
                        priority = 3
                    elif normalized and (target in normalized or normalized in target):
                        priority = 2
                if priority == 0:
                    priority = 1
                candidates.append((priority, wa_row_status_priority(row_text), latest_date_ordinal_from_text(row_text), i, link))

        if candidates:
            break

    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
    return candidates[0][4]


def wait_for_result_link_or_no_value(page, org_name: str, timeout_seconds: int = 45, require_search_response: bool = False):
    deadline = time.time() + timeout_seconds
    no_value_seen = False
    while time.time() < deadline:
        scroll_to_results(page)
        link = find_result_link(page, org_name)
        if link:
            return link
        try:
            body = page.locator("body").inner_text(timeout=8000)
        except Exception:
            body = ""
        if re.search(r"No Value Found|No records found|No results found|records 0 to 0 of 0", body, re.I):
            if require_search_response:
                tracker = wa_search_tracker_state(page)
                if tracker.get("completed") and not tracker.get("pending"):
                    status = int(tracker.get("lastStatus") or 0)
                    if 200 <= status < 300 and wa_search_response_is_empty(tracker.get("lastText") or ""):
                        return "NO_VALUE"
                    if status >= 400 or tracker.get("failed"):
                        return None
                time.sleep(2)
                continue
            if not no_value_seen:
                deadline = min(deadline, time.time() + 8)
            no_value_seen = True
        time.sleep(2)
    return "NO_VALUE" if no_value_seen else None


def search_wa(org: Organization, show_process: bool = False) -> SearchResult:
    result = SearchResult(
        organization_name=org.organization_name,
        ein=org.ein,
        state="WA",
        status=STATUS_UNKNOWN,
        raw_status_text="",
        source_url=WA_SEARCH_URL,
        source_note=(
            "Washington uses the detail page reached from a FEIN search result. "
            "Top-level status is classified from the Renewal Date."
        ),
    )
    with sync_playwright() as p:
        browser, context = launch_context(p, show_process)
        page = context.new_page()
        try:
            page.goto(WA_SEARCH_URL, wait_until="domcontentloaded", timeout=45000)
            safe_wait_for_network_idle(page, timeout=10000)
            time.sleep(1)
            install_wa_search_tracker(page)

            switch_to_fein_mode(page)
            time.sleep(1)

            if not fill_fein_and_search(page, org.ein):
                result.error = "Could not click the Washington Search button."
                return result

            safe_wait_for_network_idle(page, timeout=8000)
            time.sleep(1)

            found = wait_for_result_link_or_no_value(page, org.organization_name, timeout_seconds=22, require_search_response=True)
            if found == "NO_VALUE":
                found = wa_name_fallback_result_link(page, org)
                if not found:
                    result.status = STATUS_NOT_REGISTERED
                    result.raw_status_text = "No Value Found."
                    result.source_note = "Washington FEIN search completed and returned zero result rows; bounded name fallback also found no safe result row."
                    result.success = True
                    return result
                result.source_note = (
                    "Washington FEIN search completed and returned zero result rows; "
                    "CharityClarity then used a bounded organization-name fallback and selected a safe matching result."
                )
            if not found:
                tracker = wa_search_tracker_state(page)
                status = int(tracker.get("lastStatus") or 0)
                if tracker.get("pending"):
                    result.error = "Washington search request did not complete before timeout."
                elif status >= 400:
                    result.error = f"Washington search request failed with HTTP {status}."
                else:
                    result.error = "Could not locate the Washington organization result link after the search completed."
                return result

            try:
                result.matched_registry_name = normalize_spaces(found.inner_text(timeout=1500))
            except Exception:
                result.matched_registry_name = ""
            try:
                found.scroll_into_view_if_needed(timeout=5000)
                time.sleep(1)
            except Exception:
                pass
            found.click(timeout=5000, force=True)

            safe_wait_for_network_idle(page, timeout=10000)
            time.sleep(1)

            detail_text = page.locator("body").inner_text(timeout=15000)
            status_text = extract_label(detail_text, "Status")
            renewal_text = (
                extract_label(detail_text, "Renewal Date")
                or extract_label(detail_text, "Renewal Due Date")
                or extract_label(detail_text, "Renewal")
            )

            renewal_date = parse_date(renewal_text)
            terminal_status = terminal_closed_status_text(detail_text)
            result.status = classify_by_renewal(renewal_date, status_text, detail_text)
            raw_parts = []
            if terminal_status:
                raw_parts.append(f"Registry Status: {terminal_status}")
            if status_text:
                raw_parts.append(f"Status: {status_text}")
            if renewal_text:
                raw_parts.append(f"Renewal Date: {renewal_text}")
            result.raw_status_text = " | ".join(raw_parts) if raw_parts else normalize_spaces(detail_text)[:500]
            result.success = True
            return result
        except Exception as exc:
            result.error = f"WA error: {exc}"
            return result
        finally:
            context.close()
            browser.close()


def find_visible(page, selectors: list[str], timeout: int = 5000):
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            loc.wait_for(state="visible", timeout=timeout)
            return loc
        except Exception:
            continue
    return None


def nm_parse_history_rows(page) -> list[tuple[int, str, str]]:
    history_table = None
    tables = page.locator("table")
    for i in range(min(tables.count(), 40)):
        table = tables.nth(i)
        try:
            text = normalize_spaces(table.inner_text(timeout=1500))
        except Exception:
            continue
        if "Tax Year" in text and "Registration Details" in text and "Status Date" in text:
            history_table = table
            break
    if history_table is None:
        return []

    rows = []
    tr_list = history_table.locator("tr")
    for i in range(min(tr_list.count(), 500)):
        tr = tr_list.nth(i)
        try:
            cells = tr.locator("td")
            if cells.count() < 3:
                continue
            year_text = normalize_spaces(cells.nth(0).inner_text(timeout=800))
            detail_text = normalize_spaces(cells.nth(1).inner_text(timeout=800))
            status_date = normalize_spaces(cells.nth(2).inner_text(timeout=800))
        except Exception:
            continue
        if not year_text or not re.fullmatch(r"\d{4}", year_text):
            continue
        rows.append((int(year_text), detail_text, status_date))
    return rows


def strip_html(value: str) -> str:
    return normalize_spaces(html.unescape(re.sub(r"<[^>]+>", " ", value or "")))


def nm_parse_history_rows_from_html(page_html: str) -> list[tuple[int, str, str]]:
    match = re.search(
        r'<table[^>]+id=["\']MainContent_GridViewStatuses["\'][^>]*>(.*?)</table>',
        page_html or "",
        re.I | re.S,
    )
    if not match:
        return []

    rows: list[tuple[int, str, str]] = []
    for row_html in re.findall(r"<tr\b[^>]*>(.*?)</tr>", match.group(1), re.I | re.S):
        cells = re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row_html, re.I | re.S)
        if len(cells) < 3:
            continue
        year_text = strip_html(cells[0])
        detail_text = strip_html(cells[1])
        status_date = strip_html(cells[2])
        if not re.fullmatch(r"\d{4}", year_text or ""):
            continue
        detail_text = re.sub(r"\s+(\d{10,})\s*$", r" \1", detail_text).strip()
        rows.append((int(year_text), detail_text, status_date))
    return rows


def nm_parse_history_rows_from_text(body_text: str) -> list[tuple[int, str, str]]:
    match = re.search(
        r"Status\s+History.*?Tax\s+Year\s+Registration\s+Details\s+Status\s+Date\s+(.*)",
        body_text or "",
        re.I | re.S,
    )
    if match:
        section = match.group(1)
    else:
        fallback = re.search(r"Status\s+History(.*)", body_text or "", re.I | re.S)
        section = fallback.group(1) if fallback else (body_text or "")
    rows: list[tuple[int, str, str]] = []
    for row in re.finditer(
        r"\b(20\d{2})\s+(.+?)\s+(\d{1,2}/\d{1,2}/\d{4})(?=\s+20\d{2}\s+|$)",
        section,
        re.I | re.S,
    ):
        detail_text = normalize_spaces(row.group(2))
        if not detail_text:
            continue
        rows.append((int(row.group(1)), detail_text, row.group(3)))
    if rows:
        return rows
    # Some NM detail pages now include Registrar Notes before Status History,
    # and the table text can arrive without the exact header spacing. In that
    # case, scan for the repeated tax-year/detail/date row shape directly.
    for row in re.finditer(
        r"\b(20\d{2})\s+"
        r"((?:Tax\s+Year\s+Registration\s+Open|Registration\s+Submitted(?:\s+\d{10,})?|"
        r"Extension\s+(?:Granted|Requested)|Reinstatement\s+Issued|Registration\s+Submission\s+Delinquent))"
        r"\s+(\d{1,2}/\d{1,2}/\d{4})",
        section,
        re.I,
    ):
        rows.append((int(row.group(1)), normalize_spaces(row.group(2)), row.group(3)))
    return rows


def nm_registry_name_from_html(page_html: str) -> str:
    match = re.search(
        r'id=["\']MainContent_FormViewCharityDetail_LabelCharityName["\'][^>]*>(.*?)</span>',
        page_html or "",
        re.I | re.S,
    )
    if not match:
        return ""
    name = strip_html(match.group(1))
    name = re.sub(r"\s*\(\d{2}-\d{7}\)\s*$", "", name).strip()
    return name


def nm_extract_fye_from_html(page_html: str, preferred_year: int | None = None) -> str:
    text = strip_html(page_html)
    candidates = []
    for match in re.finditer(
        r"\b(20\d{2})\s+(\d{1,2}/\d{1,2}/\d{2,4})\s*-\s*(\d{1,2}/\d{1,2}/\d{2,4})",
        text,
        re.I,
    ):
        year = int(match.group(1))
        candidates.append((year, match.group(3)))
    if not candidates:
        return ""
    if preferred_year is not None:
        for year, end_date in candidates:
            if year == preferred_year:
                return end_date
    return max(candidates, key=lambda item: item[0])[1]


def nm_latest_submitted(rows: list[tuple[int, str, str]]):
    submitted = []
    for year, detail, status_date in rows:
        match = re.match(r"^Registration Submitted\s+(\d{10,})$", detail)
        if match:
            submitted.append((year, match.group(1), status_date))
    if not submitted:
        return None
    return max(submitted, key=lambda item: item[0])


def nm_fye_from_tax_year_open(rows: list[tuple[int, str, str]], tax_year: int) -> str:
    for year, detail, status_date in rows:
        if year != tax_year or not detail.startswith("Tax Year Registration Open"):
            continue
        opened = parse_date(status_date)
        if not opened:
            continue
        fye = opened - timedelta(days=1)
        return date(tax_year, fye.month, fye.day).strftime("%m/%d/%Y")
    return ""


def nm_extract_fye(context, reg_number: str) -> tuple[str, str]:
    if not reg_number:
        return "", ""
    helper_code = f"""
from playwright.sync_api import sync_playwright
from pathlib import Path
import tempfile, subprocess, os, re

reg_number = {reg_number!r}
bundled_python = r{str(BUNDLED_PDF_PYTHON)!r}
temp_dir = tempfile.mkdtemp(prefix='nm_pdf_')
pdf_path = str(Path(temp_dir) / f'{{reg_number}}.pdf')

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        with page.expect_download(timeout=45000) as info:
            try:
                page.goto(
                    f'https://secure.nmdoj.gov/coros/getregdoc.aspx?RegNumber={{reg_number}}',
                    wait_until='commit',
                    timeout=45000,
                )
            except Exception as exc:
                if 'Download is starting' not in str(exc):
                    raise
        download = info.value
        download.save_as(pdf_path)
        browser.close()

    parse_code = (
        "import re\\n"
        "from pypdf import PdfReader\\n"
        f"pdf = PdfReader(r'''{{pdf_path}}''')\\n"
        "text='\\\\n'.join((pg.extract_text() or '') for pg in pdf.pages[:5])\\n"
        "m = re.search(r'Tax Year\\\\s+\\\\d{{4}}\\\\s+-\\\\s+fiscal period beginning\\\\s+(\\\\d{{1,2}}/\\\\d{{1,2}}/\\\\d{{2,4}})\\\\s+and ending\\\\s+(\\\\d{{1,2}}/\\\\d{{1,2}}/\\\\d{{2,4}})', text, re.I)\\n"
        "if m:\\n"
        "    print('BEGIN=' + m.group(1))\\n"
        "    print('END=' + m.group(2))\\n"
        "else:\\n"
        "    m2 = re.search(r'ending\\\\s+(\\\\d{{1,2}}/\\\\d{{1,2}}/\\\\d{{2,4}})', text, re.I)\\n"
        "    print('BEGIN=')\\n"
        "    print('END=' + (m2.group(1) if m2 else ''))\\n"
    )
    result = subprocess.run([bundled_python, '-c', parse_code], capture_output=True, text=True)
    print(result.stdout, end='')
finally:
    try:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        if os.path.isdir(temp_dir):
            os.rmdir(temp_dir)
    except Exception:
        pass
"""
    result = subprocess.run([sys.executable, "-c", helper_code], capture_output=True, text=True)
    begin = ""
    end = ""
    for line in (result.stdout or "").splitlines():
        if line.startswith("BEGIN="):
            begin = line.split("=", 1)[1].strip()
        elif line.startswith("END="):
            end = line.split("=", 1)[1].strip()
    return begin, end


def nm_fetch_detail_html(ein: str) -> tuple[str, str]:
    if curl_requests is None:
        return "", "curl_cffi is not installed"
    url = f"https://secure.nmdoj.gov/CharitySearch/CharityDetail.aspx?FEIN={format_ein(ein)}"
    try:
        response = curl_requests.get(
            url,
            impersonate="chrome136",
            timeout=35,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
    except Exception as exc:
        return "", f"NM curl detail fetch failed: {exc}"
    if response.status_code != 200:
        return "", f"NM curl detail fetch returned HTTP {response.status_code}"
    text = response.text or ""
    if re.search(r"\b(?:cloudflare|you have been blocked|just a moment)\b", text, re.I):
        return "", "NM curl detail fetch received a Cloudflare challenge/block page"
    return text, ""


def apply_nm_rows_to_result(
    result: SearchResult,
    rows: list[tuple[int, str, str]],
    fye_text: str = "",
    context=None,
) -> SearchResult:
    latest_tax_year = max(year for year, _, _ in rows)
    latest_year_rows = [(year, detail, status_date) for year, detail, status_date in rows if year == latest_tax_year]

    def row_sort_key(row: tuple[int, str, str]):
        _, detail, status_date = row
        parsed_status_date = parse_date(status_date) or date.min
        if re.search(r"\bdelinquent\b", detail, re.I):
            priority = 4
        elif detail.startswith("Extension Granted"):
            priority = 3
        elif detail.startswith("Registration Submitted"):
            priority = 2
        elif detail.startswith("Tax Year Registration Open"):
            priority = 1
        else:
            priority = 0
        return parsed_status_date, priority

    latest_detail = re.sub(
        r"\s+\d{10,}$",
        "",
        max(latest_year_rows, key=row_sort_key)[1],
    ).strip()

    latest_submitted = nm_latest_submitted(rows)
    if latest_detail.startswith("Tax Year Registration Open"):
        result.status = STATUS_UPCOMING if latest_tax_year >= date.today().year - 1 else STATUS_DELINQUENT
        result.raw_status_text = f"Tax Year {latest_tax_year} | {latest_detail}"
        result.success = True
        return result
    if not latest_submitted:
        if re.search(r"\bdelinquent\b", latest_detail, re.I):
            result.status = STATUS_DELINQUENT
        elif latest_tax_year <= date.today().year - 2:
            result.status = STATUS_DELINQUENT
        else:
            result.status = STATUS_UNKNOWN
        result.raw_status_text = f"Tax Year {latest_tax_year} | {latest_detail}"
        result.success = True
        return result

    _, reg_number, _ = latest_submitted
    history_fye_text = nm_fye_from_tax_year_open(rows, latest_tax_year)
    has_extension = any(detail.startswith("Extension Granted") for _, detail, _ in latest_year_rows)
    if has_extension and history_fye_text:
        fye_text = history_fye_text
    if not fye_text:
        fye_text = history_fye_text
    if not fye_text and context is not None:
        _, fye_text = nm_extract_fye(context, reg_number)
    if not fye_text:
        if latest_detail.startswith("Tax Year Registration Open"):
            result.status = STATUS_UPCOMING if latest_tax_year >= date.today().year - 1 else STATUS_DELINQUENT
        elif re.search(r"\bdelinquent\b", latest_detail, re.I):
            result.status = STATUS_DELINQUENT
        elif latest_tax_year <= date.today().year - 2:
            result.status = STATUS_DELINQUENT
        else:
            result.status = STATUS_UNKNOWN
        result.raw_status_text = f"Tax Year {latest_tax_year} | {latest_detail}"
        result.success = True
        return result

    fye_date = parse_date(fye_text)
    if not fye_date:
        result.status = STATUS_UNKNOWN
        result.raw_status_text = f"Tax Year {latest_tax_year} | {latest_detail}"
        result.success = True
        return result

    cycle_fye = date(latest_tax_year, fye_date.month, fye_date.day)
    due_date = add_months(cycle_fye, 6)
    if has_extension:
        due_date = add_months(due_date, 6)

    today = date.today()
    six_months = today + timedelta(days=183)
    if has_extension and latest_tax_year >= today.year - 1:
        result.status = STATUS_UPCOMING
    elif due_date < today:
        result.status = STATUS_DELINQUENT
    elif due_date <= six_months:
        result.status = STATUS_UPCOMING
    else:
        result.status = STATUS_CURRENT

    result.raw_status_text = (
        f"Tax Year {latest_tax_year} | {latest_detail} | "
        f"FYE: {cycle_fye.strftime('%m/%d/%Y')} | Due: {due_date.strftime('%m/%d/%Y')}"
    )
    result.success = True
    return result


def search_nm(org: Organization, show_process: bool = False) -> SearchResult:
    result = SearchResult(
        organization_name=org.organization_name,
        ein=org.ein,
        state="NM",
        status=STATUS_UNKNOWN,
        raw_status_text="",
        source_url=NM_SEARCH_URL,
        source_note=(
            "New Mexico uses the latest open tax year from Status History, "
            "plus the FYE month/day read from the latest submitted registration PDF."
        ),
    )

    detail_html, fetch_error = nm_fetch_detail_html(org.ein)
    if detail_html:
        body_text = strip_html(detail_html)
        result.matched_registry_name = nm_registry_name_from_html(detail_html)
        if not result.matched_registry_name:
            result.status = STATUS_NOT_REGISTERED
            result.raw_status_text = "No New Mexico charity registration name found for this FEIN."
            result.source_note = (
                "New Mexico returned a FEIN detail shell, but it did not expose a charity name. "
                "CharityClarity requires the official detail page to identify the charity before treating status-history rows as a registered match."
            )
            result.success = True
            return result
        if re.search(r"Charity\s+Registration\s+Status\s+is\s+unknown\.?", body_text, re.I) and "Tax Year" not in body_text:
            result.status = STATUS_NOT_REGISTERED
            result.raw_status_text = "No New Mexico charity registration status-history rows found for this FEIN."
            result.success = True
            return result

        rows = nm_parse_history_rows_from_html(detail_html)
        if not rows:
            rows = nm_parse_history_rows_from_text(body_text)
        if rows:
            latest_submitted = nm_latest_submitted(rows)
            fye_text = nm_extract_fye_from_html(
                detail_html,
                preferred_year=latest_submitted[0] if latest_submitted else None,
            )
            return apply_nm_rows_to_result(result, rows, fye_text=fye_text)

        result.source_note = (
            "New Mexico official detail HTML was retrieved, but status-history rows were not parsed from the HTML. "
            "Playwright fallback was attempted."
        )
    elif fetch_error:
        result.source_note = f"{result.source_note} Official HTML fast path unavailable: {fetch_error}."

    with sync_playwright() as p:
        browser, context = launch_context(p, show_process)
        page = context.new_page()
        try:
            page.goto(f"https://secure.nmdoj.gov/CharitySearch/CharityDetail.aspx?FEIN={format_ein(org.ein)}", wait_until="domcontentloaded", timeout=45000)
            safe_wait_for_network_idle(page, timeout=15000)
            time.sleep(2)

            body = page.locator("body").inner_text(timeout=15000)
            if re.search(r"Charity\s+Registration\s+Status\s+is\s+unknown\.?", body, re.I) and "Tax Year" not in body:
                result.status = STATUS_NOT_REGISTERED
                result.raw_status_text = "No New Mexico charity registration status-history rows found for this FEIN."
                result.success = True
                return result

            rows = nm_parse_history_rows(page)
            if not rows:
                rows = nm_parse_history_rows_from_text(body)
            if not rows:
                result.status = STATUS_UNKNOWN
                result.raw_status_text = "NM detail page reached, but status-history rows were not parsed"
                if re.search(r"\bTax\s+Year\b", body, re.I):
                    result.source_note = (
                        "New Mexico detail lookup exposed tax-year text, but the hosted parser could not read status-history rows. "
                        "CharityClarity does not infer Pending without an explicit registry status."
                    )
                else:
                    result.source_note = (
                        "New Mexico detail lookup did not expose status-history tax-year rows for this FEIN. "
                        "CharityClarity treats that registry response as ambiguous rather than as a confirmed no-record result."
                    )
                result.success = True
                return result

            return apply_nm_rows_to_result(result, rows, context=context)
        except Exception as exc:
            result.error = f"NM error: {exc}"
            return result
        finally:
            context.close()
            browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Washington and New Mexico charity checker.")
    parser.add_argument("--state", required=True, choices=["WA", "NM"], help="State to check")
    parser.add_argument("--name", required=True, help="Organization name")
    parser.add_argument("--ein", required=True, help="EIN / FEIN")
    parser.add_argument("--show-process", action="store_true", help="Show browser while running")
    args = parser.parse_args()

    org = Organization(organization_name=args.name, ein=args.ein)
    if args.state == "WA":
        result = search_wa(org, show_process=args.show_process)
    else:
        result = search_nm(org, show_process=args.show_process)

    print_result(result)
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
