#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except Exception:
    print("Install Playwright first: py -m pip install playwright && py -m playwright install", file=sys.stderr)
    raise

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

STATUS_NOT_REGISTERED = "Not registered"
STATUS_CURRENT = "Current"
STATUS_UPCOMING = "Upcoming Filing"
STATUS_DELINQUENT = "Delinquent/Non-compliant"
STATUS_UNKNOWN = "Unknown"

AK_SEARCH_URL = "https://online-registrations-law.alaska.gov/TLP/WebDoc/?link=PubQry"
AK_YEARS_TO_TRY = [2026, 2025, 2024, 2023]
FAST_WAIT_MAX_MS = max(750, min(int(os.environ.get("CE_FAST_WAIT_MAX_MS", "1500")), 2000))
FULL_PAGE_ARTIFACTS = os.environ.get("CE_FULL_PAGE_ARTIFACTS", "0").strip().lower() in {"1", "true", "yes"}
ARTIFACT_SCREENSHOT_TIMEOUT_MS = max(1000, int(os.environ.get("CE_ARTIFACT_SCREENSHOT_TIMEOUT_MS", "10000")))
STATE_RESULT_WAIT_SECONDS = max(3, int(os.environ.get("CE_STATE_RESULT_WAIT_SECONDS", "10")))
MD_FAST_SEARCH_ONLY = os.environ.get("CE_MD_FAST_SEARCH_ONLY", "1").strip().lower() not in {"0", "false", "no"}
MD_FAST_RESULT_WAIT_SECONDS = max(2, min(STATE_RESULT_WAIT_SECONDS, int(os.environ.get("CE_MD_FAST_RESULT_WAIT_SECONDS", "3"))))
MAX_FIXED_SLEEP_SECONDS = max(0.25, float(os.environ.get("CE_MAX_FIXED_SLEEP_SECONDS", "1.5")))
_REAL_SLEEP = time.sleep


def fast_sleep(seconds: float) -> None:
    """Cap fixed pauses so slow state portals do not make the full snapshot crawl."""
    try:
        amount = max(0.0, float(seconds))
    except Exception:
        amount = 0.0
    _REAL_SLEEP(min(amount, MAX_FIXED_SLEEP_SECONDS))

@dataclass
class Organization:
    organization_name: str
    ein: str = ""
    evidence_mode: bool = False

@dataclass
class StateResult:
    organization_name: str
    ein: str
    state: str
    status: str
    source_url: str
    raw_status_text: str = ""
    source_note: str = ""
    success: bool = False
    error: str = ""

def digits_only(value: str) -> str:
    return re.sub(r"\D", "", value or "")

def text_contains_requested_ein(text: str, ein: str) -> bool:
    target = digits_only(ein)
    return bool(target and target in digits_only(text or ""))

def text_exposes_ein(text: str) -> bool:
    readable = re.sub(r"\s+", " ", text or "")
    return bool(
        re.search(r"\b(?:EIN|FEIN|Federal\s+Tax|Tax\s+ID|Employer\s+Identification)\b", readable, re.I)
        or re.search(r"\b\d{2}[-\s]?\d{7}\b|\b\d{9}\b", readable)
    )

def text_has_wrong_ein_match(text: str, ein: str) -> bool:
    target = digits_only(ein)
    if not target:
        return False
    return text_exposes_ein(text) and target not in digits_only(text or "")

def reject_wrong_ein_result(result: StateResult, state_name: str) -> StateResult:
    result.raw_status_text = "No matching EIN result"
    result.status = STATUS_NOT_REGISTERED
    result.source_note = f"{state_name} search found a possible name match, but the public record did not match the requested EIN."
    result.success = True
    return result

def read_input_csv(path: Path) -> List[Organization]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = {h.lower().strip(): h for h in (reader.fieldnames or [])}
        name_key = None
        for k in ["organization_name", "org_name", "organization", "name"]:
            if k in headers:
                name_key = headers[k]
                break
        if not name_key:
            raise ValueError("Input CSV must contain organization_name (or organization/name) column.")
        ein_key = None
        for k in ["ein", "tax_id", "federal_ein"]:
            if k in headers:
                ein_key = headers[k]
                break
        rows = []
        for row in reader:
            name = (row.get(name_key) or "").strip()
            if not name:
                continue
            ein = (row.get(ein_key) or "").strip() if ein_key else ""
            rows.append(Organization(name, ein))
        return rows

def write_results(prefix: str, results: List[StateResult]) -> None:
    csv_path = Path(f"{prefix}.csv")
    json_path = Path(f"{prefix}.json")
    summary_path = Path(f"{prefix}_summary_table.csv")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["organization_name", "ein", "state", "status", "source_url", "raw_status_text", "source_note", "success", "error"])
        writer.writeheader()
        for r in results:
            writer.writerow(asdict(r))
    with json_path.open("w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in results], f, indent=2)
    summary_rows = []
    summary_index = {}
    state_columns = ["CA", "MA", "MD", "CO", "NY", "NJ", "PA", "VA", "SC", "AK", "HI", "ME", "ND"]
    for r in results:
        key = (r.organization_name, r.ein)
        if key not in summary_index:
            summary_index[key] = {
                "Organization": r.organization_name,
                "EIN": r.ein,
                "CA": "",
                "MA": "",
                "MD": "",
                "CO": "",
                "NY": "",
                "NJ": "",
                "PA": "",
                "VA": "",
                "SC": "",
                "AK": "",
                "HI": "",
                "ME": "",
                "ND": "",
            }
            summary_rows.append(summary_index[key])
        if r.state in state_columns:
            summary_index[key][r.state] = r.status
    with summary_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Organization", "EIN"] + state_columns)
        writer.writeheader()
        writer.writerows(summary_rows)

def save_artifacts(page, artifacts_dir: Path, state: str, org_name: str) -> None:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    state_dir = artifacts_dir / state
    state_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9]+", "_", org_name).strip("_")[:80]
    try:
        (state_dir / f"{safe_name}.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
    try:
        page.screenshot(
            path=str(state_dir / f"{safe_name}.png"),
            full_page=FULL_PAGE_ARTIFACTS,
            timeout=ARTIFACT_SCREENSHOT_TIMEOUT_MS,
        )
    except Exception:
        pass

def safe_wait_for_network_idle(page, timeout: int = 15000) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=min(timeout, FAST_WAIT_MAX_MS))
    except Exception:
        pass

def find_visible_input(page, selectors: List[str]):
    for sel in selectors:
        try:
            loc = page.locator(sel)
            count = loc.count()
            for i in range(count):
                item = loc.nth(i)
                try:
                    typ = (item.get_attribute("type") or "").lower()
                    if typ == "hidden":
                        continue
                    if item.is_visible(timeout=750):
                        return item
                except Exception:
                    continue
        except Exception:
            continue
    return None

def add_months(value: date, months: int) -> date:
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    month_lengths = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    day = min(value.day, month_lengths[month - 1])
    return date(year, month, day)

def parse_date_value(raw: str):
    txt = re.sub(r"\s+", " ", raw or "").strip()
    if not txt:
        return None
    patterns = [
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        r"\b\d{1,2}-\d{1,2}-\d{2,4}\b",
        r"\b[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}\b",
        r"\b\d{1,2}-[A-Za-z]{3,9}-\d{2,4}\b",
        r"\b\d{4}-\d{1,2}-\d{1,2}\b",
    ]
    formats = ["%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y", "%B %d, %Y", "%b %d, %Y", "%d-%b-%y", "%d-%B-%y", "%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d"]
    for pattern in patterns:
        m = re.search(pattern, txt)
        if not m:
            continue
        candidate = m.group(0)
        for fmt in formats:
            try:
                return datetime.strptime(candidate, fmt).date()
            except Exception:
                pass
    return None

def status_from_due_date(due_date: date, as_of: Optional[date] = None) -> str:
    effective_date = as_of or date.today()
    if due_date < effective_date:
        return STATUS_DELINQUENT
    return STATUS_CURRENT

def classify_ma_visible_filing_year(latest_year: int, as_of: Optional[date] = None) -> str:
    effective_date = as_of or date.today()
    current_year = effective_date.year
    if latest_year <= current_year - 3:
        return STATUS_DELINQUENT
    if latest_year == current_year - 2:
        return STATUS_UNKNOWN
    if latest_year >= current_year - 1:
        return STATUS_CURRENT
    return STATUS_UNKNOWN

def extract_labeled_value_from_text(text: str, labels: List[str]) -> str:
    if not text:
        return ""
    normalized = re.sub(r"\r\n?", "\n", text)
    for label in labels:
        pattern = rf"{re.escape(label)}\s*:?\s*([^\n]+)"
        m = re.search(pattern, normalized, re.I)
        if m:
            value = m.group(1).strip()
            if value:
                return value
    lines = [ln.strip() for ln in normalized.splitlines() if ln.strip()]
    for i, line in enumerate(lines):
        for label in labels:
            if re.fullmatch(re.escape(label), line, re.I) and i + 1 < len(lines):
                return lines[i + 1].strip()
    return ""

def extract_labeled_value(page, labels: List[str]) -> str:
    label_pattern = re.compile("|".join(re.escape(label) for label in labels), re.I)
    containers = [
        "tr",
        ".row",
        ".form-group",
        ".field",
        "dl",
        "li",
        "div",
    ]
    for selector in containers:
        try:
            items = page.locator(selector).filter(has_text=label_pattern)
            count = min(items.count(), 25)
            for i in range(count):
                txt = items.nth(i).inner_text(timeout=1500)
                value = extract_labeled_value_from_text(txt, labels)
                if value and not label_pattern.fullmatch(value.strip()):
                    return value
        except Exception:
            continue
    try:
        return extract_labeled_value_from_text(page.locator("body").inner_text(timeout=5000), labels)
    except Exception:
        return ""

def format_ein_with_dash(value: str) -> str:
    digits = digits_only(value)
    if len(digits) == 9:
        return f"{digits[:2]}-{digits[2:]}"
    return (value or "").strip()

def extract_ak_accounting_end_year(pdf_text: str) -> Optional[int]:
    if not pdf_text:
        return None
    patterns = [
        r"Fiscal\s+or\s+Accounting\s+Year:.*?End\s+Date\s*:?[ \t]*[A-Za-z]+\s+\d{1,2},\s*(\d{4})",
        r"Accounting\s+Year:.*?[\-\u2013\u2014]\s*[A-Za-z]+\s+\d{1,2},?\s*(\d{4})",
        r"End\s+Date\s*:?[ \t]*[A-Za-z]+\s+\d{1,2},\s*(\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, pdf_text, flags=re.I | re.S)
        if match:
            try:
                return int(match.group(1))
            except Exception:
                pass
    return None

def classify_ak_registration_year(registration_year: int, accounting_year_end: Optional[int] = None):
    expiration_date = date(registration_year, 9, 1)
    status = status_from_due_date(expiration_date)
    raw_status_text = f"{registration_year} registration found; expires September 1, {registration_year}"
    accounting_note = ""
    if accounting_year_end is not None:
        accounting_note = f"; accounting year in PDF ends {accounting_year_end} and is informational only"

    if status == STATUS_DELINQUENT:
        source_note = (
            f"{registration_year} Alaska registration found; September 1 annual expiration "
            f"has passed as of the run date{accounting_note}"
        )
    else:
        source_note = (
            f"{registration_year} Alaska registration found; September 1 annual expiration "
            f"has not yet passed as of the run date{accounting_note}"
        )
    return status, raw_status_text, source_note

def open_ak_public_search(page) -> bool:
    for _ in range(2):
        try:
            page.goto(AK_SEARCH_URL, wait_until="domcontentloaded", timeout=25000)
            fast_sleep(1.5)
            if page.locator("#Dq-8").count() > 0:
                return True
            try:
                if page.get_by_label(re.compile(r"Submission\s+type", re.I)).first.is_visible(timeout=1500):
                    return True
            except Exception:
                pass
            try:
                if page.get_by_label(re.compile(r"FEIN", re.I)).first.is_visible(timeout=1500):
                    return True
            except Exception:
                pass
            public_search = page.locator("#l_Df-3-1")
            if public_search.count() > 0:
                try:
                    public_search.first.click(timeout=10000, force=True)
                except Exception:
                    pass
                fast_sleep(1.5)
                if page.locator("#Dq-8").count() > 0:
                    return True
            try:
                page.get_by_text(re.compile(r"Public\s+Search", re.I)).first.click(timeout=5000)
                fast_sleep(1.5)
                if page.get_by_label(re.compile(r"FEIN", re.I)).first.is_visible(timeout=1500):
                    return True
            except Exception:
                pass
        except Exception:
            pass
        fast_sleep(1)
    return False

def fill_ak_search_form(page, org: Organization, year: int) -> None:
    submission = page.locator("#Dq-8")
    if submission.count() == 0:
        submission = page.get_by_label(re.compile(r"Submission\s+type", re.I)).first
    submission.wait_for(state="visible", timeout=10000)
    submission.select_option(label="Charitable Organization")
    try:
        submission.dispatch_event("change")
    except Exception:
        pass
    fast_sleep(0.5)
    year_select = page.locator("#Dq-9")
    if year_select.count() == 0:
        year_select = page.get_by_label(re.compile(r"Year", re.I)).first
    year_select.wait_for(state="visible", timeout=8000)
    selected_year = False
    try:
        year_select.select_option(label=str(year))
        selected_year = True
    except Exception:
        try:
            year_select.select_option(value=str(year))
            selected_year = True
        except Exception:
            pass
    if not selected_year:
        try:
            year_select.select_option(index=0)
        except Exception:
            pass
    try:
        year_select.dispatch_event("change")
    except Exception:
        pass
    fast_sleep(0.5)
    name_input = page.locator("#Dq-a")
    if name_input.count() == 0:
        name_input = page.get_by_label(re.compile(r"^Name$", re.I)).first
    try:
        name_input.fill("")
    except Exception:
        pass
    fast_sleep(0.5)
    fein_input = page.locator("#Dq-b")
    if fein_input.count() == 0:
        fein_input = page.get_by_label(re.compile(r"FEIN", re.I)).first
    fein_input.wait_for(state="visible", timeout=8000)
    fein_input.fill("")
    fein_input.type(format_ein_with_dash(org.ein), delay=40)
    try:
        fein_input.dispatch_event("input")
        fein_input.dispatch_event("change")
    except Exception:
        pass
    fast_sleep(0.5)
    search_button = page.locator("#Dq-c")
    if search_button.count() == 0:
        search_button = page.get_by_role("button", name=re.compile(r"^Search$", re.I)).first
    search_button.click(timeout=10000, force=True)
    fast_sleep(2)

def find_ak_print_link(page, org: Organization):
    return page.evaluate(
        """
        ({ organizationName, ein }) => {
            const normalize = (value) => (value || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
            const targetOrg = normalize(organizationName);
            const rows = Array.from(document.querySelectorAll('table.DocTable tbody tr'));

            for (const row of rows) {
                const rowText = (row.innerText || row.textContent || '').trim().replace(/\\s+/g, ' ');
                if (!rowText.includes(ein)) {
                    continue;
                }

                const links = Array.from(row.querySelectorAll('a'));
                for (const link of links) {
                    const text = (link.innerText || link.textContent || '').trim();
                    const rect = link.getBoundingClientRect();
                    const style = window.getComputedStyle(link);
                    const visible = !!(rect.width && rect.height) && style.display !== 'none' && style.visibility !== 'hidden';
                    if (text === 'Print' && visible) {
                        return {
                            found: true,
                            rowText,
                            x: rect.x + rect.width / 2,
                            y: rect.y + rect.height / 2,
                        };
                    }
                }
            }
            return null;
        }
        """,
        {"organizationName": org.organization_name, "ein": format_ein_with_dash(org.ein)},
    )

def read_ak_accounting_year_from_pdf(page, context, print_link) -> Optional[int]:
    if PdfReader is None:
        return None

    popup = None
    pdf_url = ""
    try:
        try:
            with page.expect_popup(timeout=15000) as popup_info:
                page.mouse.click(print_link["x"], print_link["y"])
            popup = popup_info.value
            popup.wait_for_load_state("domcontentloaded", timeout=20000)
            pdf_url = popup.url
        except PlaywrightTimeoutError:
            page.mouse.click(print_link["x"], print_link["y"])
            fast_sleep(5)
            pdf_url = page.url

        if not pdf_url:
            return None

        response = context.request.get(pdf_url, timeout=60000)
        pdf_bytes = response.body()
        if not pdf_bytes.startswith(b"%PDF"):
            return None

        reader = PdfReader(io.BytesIO(pdf_bytes))
        pdf_text = "\n".join(pdf_page.extract_text() or "" for pdf_page in reader.pages)
        return extract_ak_accounting_end_year(pdf_text)
    except Exception:
        return None
    finally:
        if popup:
            try:
                popup.close()
            except Exception:
                pass

def search_ca(page, org: Organization) -> StateResult:
    url = "https://rct.doj.ca.gov/Verification/Web/Search.aspx?facility=Y"
    result = StateResult(org.organization_name, org.ein, "CA", STATUS_UNKNOWN, url)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        safe_wait_for_network_idle(page, timeout=8000)
        fast_sleep(0.75)

        query = digits_only(org.ein) if digits_only(org.ein) else org.organization_name
        filled = False
        for label in [r"FEIN \(numbers only\)", r"FEIN", r"Federal Employer Identification Number"]:
            try:
                page.get_by_label(re.compile(label, re.I)).fill(query, timeout=3000)
                filled = True
                break
            except Exception:
                pass
        if not filled:
            inp = find_visible_input(page, [
                'input[name*="fein" i]',
                'input[id*="fein" i]',
                'input[placeholder*="fein" i]',
                'input[name*="ein" i]',
                'input[id*="ein" i]',
                'input[type="text"]',
                'input[type="search"]',
            ])
            if not inp:
                result.error = "Could not find CA FEIN input"
                return result
            inp.fill(query)

        clicked = False
        for label in ["Search", "Find", "Submit"]:
            try:
                page.get_by_role("button", name=re.compile(label, re.I)).click(timeout=4000)
                clicked = True
                break
            except Exception:
                pass
        if not clicked:
            page.keyboard.press("Enter")

        safe_wait_for_network_idle(page, timeout=8000)
        fast_sleep(0.75)
        body = page.locator("body").inner_text(timeout=10000)
        if re.search(r"no records|no results|not registered", body, re.I):
            result.raw_status_text = "No record found"
            result.status = STATUS_NOT_REGISTERED
            result.source_note = "California Registry Search returned no matching record."
            result.success = True
            return result

        raw = ""
        try:
            tables = page.locator("table")
            for ti in range(tables.count()):
                table_text = tables.nth(ti).inner_text(timeout=2000)
                if "REGISTRY STATUS" not in table_text.upper():
                    continue
                m = re.search(
                    r"REGISTRY STATUS\s+([A-Za-z][A-Za-z /-]+?)(?:\s+(?:RCT NUMBER|REGISTRATION NUMBER|CT\d|[A-Z]{2}\d))",
                    table_text,
                    re.I | re.S,
                )
                if m:
                    raw = re.sub(r"\s+", " ", m.group(1)).strip()
                    break
        except Exception:
            pass

        if not raw:
            ca_statuses = [
                "Not Registered - Cease and Desist Order",
                "Subject to Cease and Desist Order",
                "Delinquent - Late Fees Due",
                "Suspended",
                "Revoked",
                "Withdrawn",
                "Dissolved",
                "Delinquent",
                "Closed - Registration Not Required",
                "Closed",
                "Current - Reporting Incomplete",
                "Current - Awaiting Reporting",
                "Current - Probationary Registration",
                "Current - In Process",
                "Dissolution Waiver Issued",
                "Dissolution Pending",
                "Registered - Corporate Trustee",
                "Exempt - Form 990-PF Required",
                "Exempt - Facility Financing",
                "Not Registered",
                "Exempt - Religious",
                "Exempt",
                "Current",
            ]
            for status_text in ca_statuses:
                if status_text.lower() in body.lower():
                    raw = status_text
                    break

        if not raw:
            result.raw_status_text = "Registry Status not found"
            result.status = STATUS_UNKNOWN
            result.source_note = "California detail page did not expose a recognizable Registry Status."
            result.success = True
            return result

        result.raw_status_text = raw
        result.status = raw
        result.source_note = "California uses the exact Registry Status shown in the Registry Search Tool."
        result.success = True
        return result
    except Exception as e:
        result.error = f"CA error: {e}"
        return result

def search_co(page, org: Organization) -> StateResult:
    url = "https://www.coloradosos.gov/ccsa/pages/search/basic.xhtml"
    result = StateResult(org.organization_name, org.ein, "CO", STATUS_UNKNOWN, url)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        safe_wait_for_network_idle(page, timeout=20000)
        fast_sleep(0.5)

        query = digits_only(org.ein) if digits_only(org.ein) else org.organization_name
        input_box = find_visible_input(page, [
            'input[name*="search" i]',
            'input[id*="search" i]',
            'input[type="text"]',
            'input[type="search"]',
        ])
        if not input_box:
            result.error = "Could not find CO search input"
            return result

        input_box.fill("")
        input_box.fill(query)
        page.keyboard.press("Enter")
        safe_wait_for_network_idle(page, timeout=25000)
        fast_sleep(0.75)

        body = page.locator("body").inner_text(timeout=5000)
        if re.search(r"no records|no results|not found", body, re.I):
            result.raw_status_text = "No record found"
            result.status = STATUS_NOT_REGISTERED
            result.source_note = "Colorado search returned no matching record."
            result.success = True
            return result

        expires_match = re.search(r"Expir(?:es|ed)\s+on[:\s]+(\d{1,2}/\d{1,2}/\d{4})", body, re.I)
        if expires_match:
            expires_on = datetime.strptime(expires_match.group(1), "%m/%d/%Y").date()
            result.raw_status_text = f"Expires on {expires_on.strftime('%m/%d/%Y')}"
            result.status = status_from_due_date(expires_on)
            result.source_note = "Colorado public search exposes an expiration date; status is derived from that date."
            result.success = True
            return result

        status_text = extract_labeled_value_from_text(body, ["Status", "Registration Status"])
        if status_text and not re.fullmatch(r"status", status_text, re.I):
            result.raw_status_text = status_text
            result.status = status_text
            result.source_note = "Colorado uses the exact public status when it is visible."
            result.success = True
            return result

        result.raw_status_text = "Colorado status not found"
        result.status = STATUS_UNKNOWN
        result.source_note = "Colorado public search did not expose a final status or expiration date."
        result.success = True
        return result
    except Exception as e:
        result.error = f"CO error: {e}"
        return result

def search_ma(page, org: Organization) -> StateResult:
    url = "https://masscharities.my.site.com/FilingSearch/s/"
    result = StateResult(org.organization_name, org.ein, "MA", STATUS_UNKNOWN, url)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        safe_wait_for_network_idle(page, timeout=30000)
        fast_sleep(6)

        query = digits_only(org.ein) if digits_only(org.ein) else org.organization_name
        switched = False
        try:
            combo = page.get_by_role("combobox").first
            combo.select_option(label="Employer Identification Number")
            switched = True
        except Exception:
            pass
        if not switched:
            try:
                page.get_by_text(re.compile("Employer Identification Number", re.I)).click(timeout=3000)
            except Exception:
                pass

        search_input = None
        try:
            textboxes = page.get_by_role("textbox")
            for i in range(textboxes.count()):
                tb = textboxes.nth(i)
                try:
                    if not tb.is_visible(timeout=500):
                        continue
                    attrs = " ".join([
                        tb.get_attribute("name") or "",
                        tb.get_attribute("id") or "",
                        tb.get_attribute("placeholder") or "",
                        tb.get_attribute("aria-label") or "",
                    ]).lower()
                    if "ago" in attrs:
                        continue
                    search_input = tb
                    break
                except Exception:
                    continue
        except Exception:
            pass
        if not search_input:
            search_input = find_visible_input(page, [
                'input[placeholder*="Employer Identification Number" i]',
                'input[placeholder*="EIN" i]',
                'input[type="search"]',
                'input[type="text"]',
            ])
        if not search_input:
            result.error = "Could not find MA EIN search input"
            return result

        search_input.fill("")
        search_input.fill(query)

        clicked = False
        for label in ["Search", "Find"]:
            try:
                page.get_by_role("button", name=re.compile(label, re.I)).click(timeout=4000)
                clicked = True
                break
            except Exception:
                pass
        if not clicked:
            page.keyboard.press("Enter")

        safe_wait_for_network_idle(page, timeout=25000)
        fast_sleep(3)

        body = page.locator("body").inner_text(timeout=15000)
        if re.search(r"no results|no records|0 records|no matching", body, re.I):
            result.raw_status_text = "No record found"
            result.status = STATUS_NOT_REGISTERED
            result.source_note = "Massachusetts search returned no matching record."
            result.success = True
            return result

        for label in ["Get filings", "Get Filings"]:
            try:
                page.get_by_role("button", name=re.compile(label, re.I)).click(timeout=4000)
                break
            except Exception:
                pass
            try:
                page.get_by_text(re.compile(label, re.I)).click(timeout=4000)
                break
            except Exception:
                pass
        safe_wait_for_network_idle(page, timeout=25000)
        for _ in range(15):
            fast_sleep(1)
            try:
                loading_text = page.locator("body").inner_text(timeout=5000)
            except Exception:
                continue
            if re.search(r"Form[\s-]*PC|No documents found|No rows available", loading_text, re.I):
                break

        try:
            page.locator("body").evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except Exception:
            pass
        fast_sleep(1)

        body = page.locator("body").inner_text(timeout=15000)
        m_section = re.search(
            r"Annual Filings(?: and Documents)?(.*?)(?:Financial Statements|Additional Documents|$)",
            body,
            re.I | re.S,
        )
        section_text = m_section.group(1) if m_section else body

        filing_years = []
        for m in re.finditer(r"Form[\s-]*PC[\s\S]{0,140}(20\d{2})", section_text, re.I):
            filing_years.append(int(m.group(1)))
        for m in re.finditer(r"(20\d{2})[\s\S]{0,140}Form[\s-]*PC", section_text, re.I):
            filing_years.append(int(m.group(1)))
        filing_years = sorted(set(filing_years))

        if not filing_years:
            result.raw_status_text = "Annual Filings not visible"
            result.status = STATUS_UNKNOWN
            result.source_note = "Massachusetts public portal did not expose a visible filing year after Get Filings."
            result.success = True
            return result

        latest_year = max(filing_years)
        result.raw_status_text = str(latest_year)
        result.status = classify_ma_visible_filing_year(latest_year)
        if result.status == STATUS_UNKNOWN:
            result.source_note = (
                "Massachusetts public portal exposes Annual Filings only; with no visible fiscal year end, "
                "a latest filing year one year behind may still be within the automatic extension window."
            )
        else:
            result.source_note = (
                "Massachusetts uses the latest visible Form PC year from Annual Filings, cross-checked against "
                "the official 4.5-month filing rule and automatic extension guidance."
            )
        result.success = True
        return result
    except Exception as e:
        result.error = f"MA error: {e}"
        return result

def search_ny(page, org: Organization) -> StateResult:
    url = "https://www.charitiesnys.com/RegistrySearch/search_charities.jsp"
    result = StateResult(org.organization_name, org.ein, "NY", STATUS_UNKNOWN, url)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=12000)
        safe_wait_for_network_idle(page, timeout=2500)
        fast_sleep(1)

        ein_digits = digits_only(org.ein)
        formatted_ein = format_ein_with_dash(org.ein) if ein_digits else ""

        name_input = None
        for sel in [
            '#orgName',
            'input[name="orgName"]',
            'input[placeholder*="Organization name" i]',
        ]:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=1000):
                    name_input = loc
                    break
            except Exception:
                continue
        if not name_input:
            name_input = find_visible_input(page, [
                'input[name*="orgname" i]',
                'input[id*="orgname" i]',
                'input[placeholder*="organization" i]',
            ])

        ein_input = None
        for sel in [
            '#ein',
            'input[name="ein"]',
            'input[placeholder="EIN"]',
        ]:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=1000):
                    ein_input = loc
                    break
            except Exception:
                continue
        if not ein_input:
            ein_input = find_visible_input(page, [
                'input[name*="ein" i]',
                'input[id*="ein" i]',
                'input[placeholder*="ein" i]',
            ])

        if not name_input or not ein_input:
            result.error = "Could not find NY organization name and EIN inputs"
            return result

        name_input.fill("")
        name_input.fill(org.organization_name)
        ein_input.fill("")
        if formatted_ein:
            ein_input.fill(formatted_ein)
        else:
            ein_input.fill(org.ein)

        clicked = False
        for label in ["Search", "Find"]:
            try:
                page.get_by_role("button", name=re.compile(label, re.I)).click(timeout=4000)
                clicked = True
                break
            except Exception:
                pass
        if not clicked:
            page.keyboard.press("Enter")

        safe_wait_for_network_idle(page, timeout=25000)
        fast_sleep(3)

        body = page.locator("body").inner_text(timeout=12000)
        if re.search(r"no rows available|no records|no results found|no results|not found", body, re.I):
            result.raw_status_text = "No results found"
            result.status = "Not Found"
            result.source_note = "New York search returned no results found."
            result.success = True
            return result

        wanted_name = normalize_name(org.organization_name)
        clicked_id = False
        best_row = None
        best_priority = -1
        try:
            rows = page.locator("tr")
            count = min(rows.count(), 100)
            for i in range(count):
                row = rows.nth(i)
                try:
                    row_text = re.sub(r"\s+", " ", row.inner_text(timeout=1500)).strip()
                    if not row_text:
                        continue
                    row_digits = digits_only(row_text)
                    if ein_digits and text_exposes_ein(row_text) and ein_digits not in row_digits:
                        continue
                    row_name = normalize_name(row_text)
                    priority = -1
                    if ein_digits and ein_digits in row_digits:
                        priority = 3
                    elif wanted_name and row_name == wanted_name:
                        priority = 2
                    elif wanted_name and (wanted_name in row_name or row_name in wanted_name):
                        priority = 1
                    if priority > best_priority:
                        best_priority = priority
                        best_row = row
                except Exception:
                    continue
        except Exception:
            pass

        if best_row is not None and best_priority >= 0:
            try:
                links = best_row.locator("a")
                for j in range(links.count()):
                    link = links.nth(j)
                    txt = (link.inner_text(timeout=1000) or "").strip()
                    compact_txt = re.sub(r"\s+", "", txt)
                    href = (link.get_attribute("href") or "").strip()
                    if txt and (
                        re.fullmatch(r"\d[\d-]*", compact_txt)
                        or "/RegistrySearch/" in href
                    ):
                        link.click(timeout=5000)
                        clicked_id = True
                        break
            except Exception:
                pass

        if not clicked_id:
            result.raw_status_text = "Detail page not reached"
            result.status = STATUS_UNKNOWN
            result.source_note = "New York detail page was not reached from the Organization ID link."
            result.success = True
            return result

        safe_wait_for_network_idle(page, timeout=25000)
        fast_sleep(3)

        detail_text = page.locator("body").inner_text(timeout=20000)
        if text_has_wrong_ein_match(detail_text, org.ein):
            return reject_wrong_ein_result(result, "New York")
        if re.search(r"no rows available|no records|no results found|search home", detail_text, re.I) and not re.search(r"Annual Filing Documents", detail_text, re.I):
            result.raw_status_text = "Detail page not reached"
            result.status = STATUS_UNKNOWN
            result.source_note = "New York detail page was not reached after clicking the Organization ID."
            result.success = True
            return result

        annual_docs_open = re.search(r"Annual Filing Documents", detail_text, re.I) is not None
        if not annual_docs_open:
            for target in [
                page.get_by_role("button", name=re.compile("Annual Filing Documents", re.I)),
                page.get_by_role("tab", name=re.compile("Annual Filing Documents", re.I)),
                page.get_by_role("link", name=re.compile("Annual Filing Documents", re.I)),
                page.get_by_text(re.compile("^Annual Filing Documents$", re.I)),
            ]:
                try:
                    target.first.click(timeout=5000)
                    annual_docs_open = True
                    break
                except Exception:
                    continue
            if annual_docs_open:
                safe_wait_for_network_idle(page, timeout=15000)
                fast_sleep(2)
                detail_text = page.locator("body").inner_text(timeout=20000)

        if not annual_docs_open and not re.search(r"Annual Filing Documents", detail_text, re.I):
            result.raw_status_text = "Detail page not reached"
            result.status = STATUS_UNKNOWN
            result.source_note = "Annual Filing Documents section was not reached on the New York detail page."
            result.success = True
            return result

        fye_dates = []
        annual_table = None
        try:
            tables = page.locator("table")
            for i in range(min(tables.count(), 20)):
                table = tables.nth(i)
                try:
                    table_text = re.sub(r"\s+", " ", table.inner_text(timeout=2000)).strip()
                    if re.search(r"Fiscal year end", table_text, re.I) and re.search(r"Annual Filing", table_text, re.I):
                        annual_table = table
                        break
                except Exception:
                    continue
        except Exception:
            annual_table = None

        if annual_table is not None:
            try:
                rows = annual_table.locator("tbody tr")
                for i in range(min(rows.count(), 50)):
                    row = rows.nth(i)
                    try:
                        cells = row.locator("td")
                        count = cells.count()
                        for j in range(count):
                            cell_text = re.sub(r"\s+", " ", cells.nth(j).inner_text(timeout=1500)).strip()
                            parsed = parse_date_value(cell_text)
                            if parsed:
                                fye_dates.append(parsed)
                                break
                    except Exception:
                        continue
            except Exception:
                pass

        if not fye_dates:
            section_text = detail_text
            section_match = re.search(
                r"Annual filing documents(.*?)(?:Registration documents|Other filed documents|$)",
                detail_text,
                re.I | re.S,
            )
            if section_match:
                section_text = section_match.group(1)
            for match in re.findall(r"\b\d{1,2}/\d{1,2}/\d{4}\b", section_text):
                parsed = parse_date_value(match)
                if parsed:
                    fye_dates.append(parsed)

        fye_dates = sorted(set(fye_dates))
        if not fye_dates:
            result.raw_status_text = "No filings found"
            result.status = STATUS_UNKNOWN
            result.source_note = "Annual Filing Documents did not expose any Fiscal Year End values."
            result.success = True
            return result

        latest_fye = max(fye_dates)
        due_date = add_months(latest_fye, 6)
        result.status = "Current" if date.today() <= due_date else "Delinquent"
        result.raw_status_text = f"Latest FYE: {latest_fye.isoformat()} | Due: {due_date.isoformat()}"
        result.source_note = "New York status derived from the most recent Fiscal Year End in Annual Filing Documents."
        result.success = True
        return result
    except Exception as e:
        result.error = f"NY error: {e}"
        return result

def search_nj(page, org: Organization) -> StateResult:
    url = "https://charportal.dca.njoag.gov/Charity-Registration/CHR-Public-Search-Page/"
    result = StateResult(org.organization_name, org.ein, "NJ", STATUS_UNKNOWN, url)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        safe_wait_for_network_idle(page, timeout=20000)
        fast_sleep(4)

        query = digits_only(org.ein) if digits_only(org.ein) else org.organization_name
        input_box = find_visible_input(page, [
            "#SearchBox28",
            'input[placeholder="Search"]',
            'input[aria-label*="partial text" i]',
            'input[placeholder*="Search for a Charity" i]',
            'input[name*="search" i]',
            'input[id*="search" i]',
            'input[type="text"]',
            'input[type="search"]',
        ])
        if not input_box:
            result.error = "Could not find NJ search box"
            return result

        input_box.fill("")
        input_box.fill(query)
        page.keyboard.press("Enter")
        safe_wait_for_network_idle(page, timeout=25000)
        fast_sleep(4)

        body = page.locator("body").inner_text(timeout=15000)
        if re.search(r"no records found|no records|no matching", body, re.I):
            result.raw_status_text = "No record found"
            result.status = STATUS_NOT_REGISTERED
            result.source_note = "New Jersey search returned no matching record."
            result.success = True
            return result

        raw = ""
        status_match = re.search(r"Status[:\s]+([A-Za-z][A-Za-z /-]+)", body, re.I)
        if status_match:
            raw = status_match.group(1).strip()
        if not raw:
            for status_text in ["Compliant", "Active", "Delinquent", "Expired", "Revoked", "Suspended", "Withdrawn"]:
                if re.search(rf"\b{re.escape(status_text)}\b", body, re.I):
                    raw = status_text
                    break

        if not raw:
            result.raw_status_text = "Status not found"
            result.status = STATUS_UNKNOWN
            result.source_note = "New Jersey public search did not expose a recognizable status."
            result.success = True
            return result

        result.raw_status_text = raw
        result.status = raw
        result.source_note = "New Jersey uses the exact public Status value."
        result.success = True
        return result
    except Exception as e:
        result.error = f"NJ error: {e}"
        return result

def search_ak(browser, org: Organization, artifacts_dir: Optional[Path] = None) -> StateResult:
    result = StateResult(org.organization_name, org.ein, "AK", STATUS_UNKNOWN, AK_SEARCH_URL)
    if len(digits_only(org.ein)) != 9:
        result.error = "AK search requires 9-digit EIN"
        return result

    for idx, year in enumerate(AK_YEARS_TO_TRY):
        ak_context = browser.new_context(viewport={"width": 1365, "height": 900}, accept_downloads=True)
        ak_page = ak_context.new_page()
        try:
            if not open_ak_public_search(ak_page):
                result.error = "Could not open Alaska Public Search form"
                continue

            fill_ak_search_form(ak_page, org, year)
            print_link = find_ak_print_link(ak_page, org)
            if not print_link:
                if artifacts_dir and idx == len(AK_YEARS_TO_TRY) - 1:
                    save_artifacts(ak_page, artifacts_dir, "AK", org.organization_name)
                continue

            accounting_year_end = read_ak_accounting_year_from_pdf(ak_page, ak_context, print_link)
            result.status, result.raw_status_text, result.source_note = classify_ak_registration_year(
                year,
                accounting_year_end,
            )
            result.success = True
            if artifacts_dir:
                save_artifacts(ak_page, artifacts_dir, "AK", org.organization_name)
            return result
        except Exception as e:
            result.error = f"AK error: {e}"
            continue
        finally:
            ak_context.close()

    if result.error:
        return result

    checked_years = ", ".join(str(year) for year in AK_YEARS_TO_TRY)
    result.raw_status_text = f"No Alaska registration found for checked years {checked_years}"
    result.status = STATUS_NOT_REGISTERED
    result.source_note = f"No Alaska registration found in public search for years {checked_years}"
    result.success = True
    return result

def find_pa_ein_input(page):
    return find_visible_input(page, [
        'input[name="EIN"]',
        'input[ng-model="search.ein"]',
        'input[placeholder*="EIN" i]',
        'input[name*="ein" i]',
        'input[id*="ein" i]',
        'input[name*="fein" i]',
        'input[id*="fein" i]',
        'input[placeholder*="fein" i]',
    ])

def click_pa_search_button(page) -> bool:
    for attempt in range(2):
        safe_wait_for_network_idle(page, timeout=10000)
        fast_sleep(1 + attempt)

        for label in ["Search", "Find", "Submit"]:
            try:
                btn = page.get_by_role("button", name=re.compile(label, re.I)).first
                btn.wait_for(state="visible", timeout=5000)
                btn.scroll_into_view_if_needed(timeout=2000)
                btn.click(timeout=5000)
                return True
            except Exception:
                pass

        for sel in ['button', 'input[type="button"]', 'input[type="submit"]']:
            try:
                buttons = page.locator(sel)
                count = min(buttons.count(), 20)
                for i in range(count):
                    btn = buttons.nth(i)
                    try:
                        if not btn.is_visible(timeout=1000):
                            continue
                        try:
                            text = re.sub(r"\s+", " ", btn.inner_text(timeout=500)).strip()
                        except Exception:
                            text = ""
                        if not text:
                            text = (btn.get_attribute("value") or btn.get_attribute("aria-label") or "").strip()
                        if not re.search(r"search|find|submit", text, re.I):
                            continue
                        btn.scroll_into_view_if_needed(timeout=2000)
                        try:
                            btn.click(timeout=5000)
                        except Exception:
                            if attempt == 1:
                                btn.evaluate("el => el.click()")
                            else:
                                raise
                        return True
                    except Exception:
                        continue
            except Exception:
                continue
    return False

def extract_pa_result_expiration(page, ein: str, organization_name: str = ""):
    safe_wait_for_network_idle(page, timeout=15000)
    fast_sleep(2)
    try:
        page.locator("body").evaluate("window.scrollTo(0, document.body.scrollHeight)")
    except Exception:
        pass
    fast_sleep(1)

    target_name = normalize_name(organization_name)
    candidates = []
    row_selectors = ["tbody tr", "tr", "[role='row']"]
    for selector in row_selectors:
        try:
            rows = page.locator(selector)
            count = min(rows.count(), 100)
            for i in range(count):
                row = rows.nth(i)
                try:
                    if not row.is_visible(timeout=750):
                        continue
                    row_text = row.inner_text(timeout=1500)
                    if ein not in digits_only(row_text):
                        continue
                    cells = row.locator("td")
                    row_name = ""
                    if cells.count() >= 5:
                        try:
                            row_name = cells.nth(0).inner_text(timeout=1500).strip()
                        except Exception:
                            row_name = ""
                        expiration_raw = cells.nth(4).inner_text(timeout=1500).strip()
                    else:
                        expiration_raw = extract_labeled_value_from_text(row_text, ["Expiration Date", "Expiration"])
                    normalized_row_name = normalize_name(row_name or row_text)
                    priority = 0
                    if target_name:
                        if normalized_row_name == target_name:
                            priority = 4
                        elif target_name in normalized_row_name or normalized_row_name in target_name:
                            priority = 3
                        elif all(part in normalized_row_name for part in target_name.split() if len(part) > 2):
                            priority = 2
                    expiration_date = parse_date_value(expiration_raw)
                    # When PA returns several rows for one EIN, prefer the exact/name match first.
                    # If the name is unavailable, prefer a usable future expiration over stale history.
                    date_score = 1 if expiration_date and expiration_date >= date.today() else 0
                    candidates.append((priority, date_score, expiration_date or date.min, row_text, expiration_raw))
                except Exception:
                    continue
        except Exception:
            continue
    if candidates:
        candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return candidates[0][3], candidates[0][4]
    return "", ""
def search_pa(page, org: Organization) -> StateResult:
    url = "https://www.charities.pa.gov/#/page/searchCharities"
    result = StateResult(org.organization_name, org.ein, "PA", STATUS_UNKNOWN, url)
    try:
        ein = digits_only(org.ein)
        if not ein:
            result.error = "PA search requires EIN"
            return result

        last_goto_error = None
        for goto_attempt in range(2):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                safe_wait_for_network_idle(page, timeout=20000)
                fast_sleep(3)
                last_goto_error = None
                break
            except Exception as e:
                last_goto_error = e
                if goto_attempt == 0:
                    fast_sleep(4)
                    continue
        if last_goto_error:
            raise last_goto_error

        ein_input = None
        for _ in range(3):
            ein_input = find_pa_ein_input(page)
            if ein_input:
                break
            safe_wait_for_network_idle(page, timeout=10000)
            fast_sleep(2)
        if not ein_input:
            result.error = "Could not find PA EIN input"
            return result
        ein_input.fill("")
        ein_input.fill(ein)

        if not click_pa_search_button(page):
            result.error = "Could not click PA Search button"
            return result

        row_text, expiration_raw = extract_pa_result_expiration(page, ein, org.organization_name)
        if not row_text:
            formatted_ein = format_ein_with_dash(ein)
            if formatted_ein and formatted_ein != ein:
                retry_input = find_pa_ein_input(page)
                if retry_input:
                    retry_input.fill("")
                    retry_input.fill(formatted_ein)
                    if click_pa_search_button(page):
                        row_text, expiration_raw = extract_pa_result_expiration(page, ein, org.organization_name)
        if not row_text:
            result.raw_status_text = "No matching EIN result"
            result.status = STATUS_NOT_REGISTERED
            result.source_note = "PA search results did not contain a matching EIN row."
            result.success = True
            return result

        if re.search(r"\bexempt\b", row_text or "", re.I):
            result.raw_status_text = "Exempt"
            result.status = "Exempt"
            result.source_note = "Pennsylvania matched result row indicates an exempt registration status."
            result.success = True
            return result

        expiration_date = parse_date_value(expiration_raw)
        if expiration_date:
            result.raw_status_text = expiration_raw
            result.status = status_from_due_date(expiration_date)
            result.source_note = "Pennsylvania uses the Expiration Date & Automatic Extension shown in search results."
            result.success = True
            return result

        status_text = extract_labeled_value_from_text(row_text, ["Status", "Registration Status"])
        if status_text:
            result.raw_status_text = status_text
            result.status = status_text
            result.source_note = "Pennsylvania fallback uses the visible registration text from the matched result row."
            result.success = True
            return result

        result.raw_status_text = expiration_raw or re.sub(r"\s+", " ", row_text).strip()
        result.status = STATUS_UNKNOWN
        result.source_note = "Pennsylvania result row did not expose a usable expiration date or final status."
        result.success = True
        return result
    except Exception as e:
        result.error = f"PA error: {e}"
        return result
def normalize_name(value: str) -> str:
    txt = (value or "").lower()
    txt = re.sub(r"\b(the|and|a)\b", " ", txt)
    txt = re.sub(r"\b(inc|incorporated|corp|corporation|foundation|llc|ltd)\b", " ", txt)
    txt = re.sub(r"[^a-z0-9]+", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()

def find_va_name_input(page):
    try:
        inp = page.get_by_label(re.compile("Organization Name", re.I))
        for i in range(inp.count()):
            item = inp.nth(i)
            try:
                if item.is_visible(timeout=750):
                    return item
            except Exception:
                continue
    except Exception:
        pass
    return find_visible_input(page, [
        "#id_orgname",
        'input[name="orgname"]',
        'input[type="text"]',
    ])

def click_va_search_button(page) -> bool:
    selectors = [
        'input[type="submit"][value="SEARCH"]',
        'input[name="submit"]',
        'button[type="submit"]',
        'input[type="submit"]',
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=1000):
                btn.click(timeout=3000)
                return True
        except Exception:
            continue
    try:
        page.get_by_role("button", name=re.compile("Search", re.I)).click(timeout=3000)
        return True
    except Exception:
        return False

def click_va_organization_link(page, org_name: str) -> bool:
    wanted = normalize_name(org_name)
    links = page.locator('a[href*="act=2"][href*="sysorgno"]')
    candidates = []
    try:
        count = min(links.count(), 100)
        for i in range(count):
            link = links.nth(i)
            try:
                txt = re.sub(r"\s+", " ", link.inner_text(timeout=1000)).strip()
                normalized = normalize_name(txt)
                if normalized == wanted:
                    link.click(timeout=5000)
                    return True
                if wanted and (wanted in normalized or normalized in wanted):
                    score = 2 if normalized.startswith(wanted) or wanted.startswith(normalized) else 1
                    candidates.append((score, link))
            except Exception:
                continue
    except Exception:
        pass
    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        candidates[0][1].click(timeout=5000)
        return True
    return False

def search_va(page, org: Organization) -> StateResult:
    url = "https://cos.vdacs.virginia.gov/cgi-bin/char_search.cgi"
    result = StateResult(org.organization_name, org.ein, "VA", STATUS_UNKNOWN, url)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        fast_sleep(1)

        name_input = find_va_name_input(page)
        if not name_input:
            result.error = "Could not find VA organization name input"
            return result
        name_input.fill("")
        name_input.fill(org.organization_name)

        if not click_va_search_button(page):
            result.error = "Could not click VA Search button"
            return result

        page.wait_for_load_state("load", timeout=30000)
        fast_sleep(1)

        body = page.locator("body").inner_text(timeout=10000)
        if re.search(r"\bNo record found\b", body, re.I):
            result.raw_status_text = "No record found"
            result.status = STATUS_NOT_REGISTERED
            result.source_note = "Virginia search returned no matching organization link."
            result.success = True
            return result

        if not click_va_organization_link(page, org.organization_name):
            result.raw_status_text = "No matching organization link"
            result.status = STATUS_NOT_REGISTERED
            result.source_note = "Virginia search results did not contain a matching organization name link."
            result.success = True
            return result

        page.wait_for_load_state("load", timeout=30000)
        fast_sleep(1)

        extension_raw = extract_labeled_value(page, ["Registration Extended Until"])
        extension_date = parse_date_value(extension_raw)
        if extension_date:
            result.raw_status_text = extension_raw
            result.status = status_from_due_date(extension_date)
            result.source_note = "Virginia uses Registration Extended Until when an extension is shown."
            result.success = True
            return result

        expiration_raw = extract_labeled_value(page, [
            "Current Registration Expires",
            "Registration Expires",
            "Expiration Date",
        ])
        expiration_date = parse_date_value(expiration_raw)
        if expiration_date:
            result.raw_status_text = expiration_raw
            result.status = status_from_due_date(expiration_date)
            result.source_note = "Virginia uses Current Registration Expires when no extension date is shown."
            result.success = True
            return result

        fiscal_year_raw = extract_labeled_value(page, [
            "Fiscal Year End",
            "Fiscal Year Ending",
            "FYE"
        ])
        fiscal_year_end = parse_date_value(fiscal_year_raw)

        if fiscal_year_end:
            due_date = add_months(fiscal_year_end, 5)
            due_date = due_date.replace(day=15)

            result.raw_status_text = due_date.isoformat()
            result.status = status_from_due_date(due_date)
            result.source_note = "Virginia uses the statutory renewal deadline of the 15th day of the fifth month after fiscal year end."
            result.success = True
            return result

        registration_status = extract_labeled_value(page, ["Registration Filing Status"])
        result.raw_status_text = registration_status
        if re.search(r"not\s+authorized\s+to\s+solicit", registration_status or "", re.I):
            result.status = "Suspended"
            result.source_note = "Virginia public registry says the organization is not authorized to solicit in Virginia."
        elif registration_status:
            result.status = STATUS_UNKNOWN
            result.source_note = "Virginia exposed only the informational Registration Filing Status, not a final public compliance status."
        else:
            result.status = STATUS_UNKNOWN
            result.source_note = "Virginia did not expose a final public compliance status."
        result.success = True
        return result

    except Exception as e:
        result.error = f"VA error: {e}"
        return result

def search_md(page, org: Organization) -> StateResult:
    url = "https://onestop.md.gov/list_views/62f3e1797f7e3200016a3dab"
    result = StateResult(org.organization_name, org.ein, "MD", STATUS_UNKNOWN, url)
    try:
        ein = digits_only(org.ein)
        if len(ein) != 9:
            result.error = "MD search requires 9-digit EIN"
            return result
        formatted_ein = f"{ein[:2]}-{ein[2:]}"

        md_ein_filter_id = "a87e8739-62de-600d-728c-6300bf865f9e"
        entries_url = (
            f"{url}/entries?_method=get"
            f"&filter%5B{md_ein_filter_id}%5D={quote(formatted_ein)}"
            f"&filter%5Blimit%5D=20"
            f"&{md_ein_filter_id}={quote(formatted_ein)}"
            "&limit=20&fake=false&forceNewQuery=false&query%5Bpage%5D=1&page=1"
        )
        try:
            page.set_extra_http_headers({
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "text/html, */*; q=0.01",
            })
            page.goto(entries_url, wait_until="domcontentloaded", timeout=20000)
            body = page.locator("body").inner_text(timeout=5000)
            body_digits = digits_only(body)
            if ein in body_digits:
                status_match = re.search(
                    r"Registration Status:.*?var(?:\\u003e|>)\s*([^<\\]+?)\s*(?:\\u003c|<)/var",
                    body,
                    re.I | re.S,
                )
                if not status_match:
                    status_match = re.search(r"Registration\s+Status[^A-Za-z0-9]{0,80}(Current|Delinquent|Expired|Active|Inactive)", body, re.I)
                status_text = status_match.group(1).strip() if status_match else STATUS_UNKNOWN
                result.raw_status_text = status_text
                result.status = status_text
                result.source_note = "Maryland uses the exact Registration Status from an EIN-confirmed public registry entries search."
                result.success = True
                return result
            if re.search(r'"entries"\s*:\s*\[\s*\]|No\s+results\s+found', body, re.I):
                result.raw_status_text = "No record found"
                result.status = STATUS_NOT_REGISTERED
                result.source_note = "Maryland entries search returned no matching EIN record."
                result.success = True
                return result
        except Exception:
            pass

        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        safe_wait_for_network_idle(page, timeout=750)
        fast_sleep(0.25)

        ein_input = None
        for label in ["Search by Charity EIN", "Charity EIN", "EIN"]:
            try:
                loc = page.get_by_label(re.compile(label, re.I))
                count = loc.count()
                for i in range(count):
                    item = loc.nth(i)
                    try:
                        if item.is_visible(timeout=750):
                            ein_input = item
                            break
                    except Exception:
                        continue
                if ein_input:
                    break
            except Exception:
                pass
        if not ein_input:
            ein_input = find_visible_input(page, [
                'input[placeholder*="Search by Charity EIN" i]',
                'input[aria-label*="Search by Charity EIN" i]',
                'input[placeholder*="Charity EIN" i]',
                'input[aria-label*="Charity EIN" i]',
                'input[name*="ein" i]',
                'input[id*="ein" i]',
                'input[type="search"]',
                'input[type="text"]',
            ])
        if not ein_input:
            result.error = "Could not find MD Charity EIN input"
            return result

        def click_md_search(active_input) -> None:
            clicked_search = False
            for sel in [
                'button[type="submit"]',
                'input[type="submit"]',
                'button',
                'input[type="button"]',
            ]:
                try:
                    buttons = page.locator(sel).filter(has_text=re.compile("Search", re.I))
                    count = min(buttons.count(), 10)
                    for i in range(count):
                        btn = buttons.nth(i)
                        if btn.is_visible(timeout=500):
                            btn.click(timeout=3000)
                            clicked_search = True
                            break
                    if clicked_search:
                        break
                except Exception:
                    continue
            if not clicked_search:
                try:
                    page.get_by_role("button", name=re.compile("Search", re.I)).click(timeout=3000)
                    clicked_search = True
                except Exception:
                    pass
            if not clicked_search and active_input is not None:
                try:
                    active_input.press("Enter")
                except Exception:
                    pass
            safe_wait_for_network_idle(page, timeout=500)

        def submit_md_search(search_value: str) -> None:
            ein_input.fill("")
            ein_input.fill(search_value)
            fast_sleep(0.25)
            click_md_search(ein_input)

        def find_md_name_input():
            for label in ["Search by Charity Name", "Charity Name", "Name"]:
                try:
                    loc = page.get_by_label(re.compile(label, re.I))
                    count = loc.count()
                    for i in range(count):
                        item = loc.nth(i)
                        try:
                            if item.is_visible(timeout=500):
                                return item
                        except Exception:
                            continue
                except Exception:
                    pass
            for selector in [
                'input[placeholder*="Charity Name" i]',
                'input[aria-label*="Charity Name" i]',
                'input[placeholder*="Search by Charity Name" i]',
                'input[aria-label*="Search by Charity Name" i]',
                'input[type="search"]',
                'input[type="text"]',
            ]:
                try:
                    inputs = page.locator(selector)
                    count = min(inputs.count(), 8)
                    for i in range(count):
                        item = inputs.nth(i)
                        try:
                            if not item.is_visible(timeout=500):
                                continue
                            placeholder = (item.get_attribute("placeholder") or "").lower()
                            aria = (item.get_attribute("aria-label") or "").lower()
                            if "ein" in placeholder or "ein" in aria:
                                continue
                            return item
                        except Exception:
                            continue
                except Exception:
                    continue
            return None

        def submit_md_name_search(search_value: str) -> None:
            name_input = find_md_name_input()
            if not name_input:
                return
            try:
                ein_input.fill("")
            except Exception:
                pass
            name_input.fill("")
            name_input.fill(search_value)
            fast_sleep(0.25)
            click_md_search(name_input)
            try:
                name_input.press("Enter")
            except Exception:
                pass

        def wait_for_md_match() -> str:
            local_body = ""
            wait_seconds = STATE_RESULT_WAIT_SECONDS if org.evidence_mode else MD_FAST_RESULT_WAIT_SECONDS
            deadline = time.time() + min(wait_seconds, 6)
            while time.time() < deadline:
                local_body = page.locator("body").inner_text(timeout=2500)
                if md_body_has_match(local_body):
                    break
                if md_body_has_record(local_body):
                    fast_sleep(0.25)
                    local_body = page.locator("body").inner_text(timeout=2500)
                    if md_body_has_match(local_body):
                        break
                fast_sleep(0.25)
            return local_body

        def body_says_no_results(text: str) -> bool:
            return bool(re.search(r"no results|no records|not found|0 results", text or "", re.I))

        def body_says_pending_or_error(text: str) -> bool:
            readable = re.sub(r"\s+", " ", text or "")
            return bool(
                re.search(r"loading|please wait|searching|processing", readable, re.I)
                or not readable.strip()
            )

        def md_name_variants(name: str) -> list[str]:
            raw = re.sub(r"\s+", " ", name or "").strip()
            variants = [raw]
            variants.append(re.sub(r",\s*the\s*$", "", raw, flags=re.I).strip())
            variants.append(re.sub(r"^the\s+", "", raw, flags=re.I).strip())
            variants.append(re.sub(r"\bincorporated\b", "inc", raw, flags=re.I).strip())
            variants.append(re.sub(r"\b(the|inc|incorporated|corp|corporation|foundation)\b\.?", " ", raw, flags=re.I).strip())
            variants.append(re.sub(r"[^A-Za-z0-9 ]+", " ", raw).strip())
            seen = set()
            output = []
            for variant in variants:
                normalized = normalize_name(variant)
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    output.append(variant)
            return output

        md_wanted_names = [normalize_name(value) for value in md_name_variants(org.organization_name)]

        def md_body_has_exact_name(text: str) -> bool:
            normalized_text = normalize_name(text)
            return any(name and name in normalized_text for name in md_wanted_names)

        def md_body_has_match(text: str) -> bool:
            if text_contains_requested_ein(text, org.ein) or formatted_ein in (text or ""):
                return True
            if ein:
                return False
            if md_body_has_record(text) and text_exposes_ein(text):
                return False
            if md_body_has_record(text) and wanted_name:
                return md_body_has_exact_name(text)
            return bool(
                wanted_name and md_body_has_exact_name(text)
            )

        def md_body_has_record(text: str) -> bool:
            readable = re.sub(r"\s+", " ", text or "")
            if re.search(r"no results|no records|not found|0 results", readable, re.I):
                return False
            return bool(
                re.search(r"\b1\s+record\b|\b[1-9]\d*\s+records\b", readable, re.I)
                or re.search(r"SOS\s+Charity\s+Organization\s+Record\s+for", readable, re.I)
                or re.search(r"Registration\s+Status\s*:?\s*Current", readable, re.I)
            )

        allow_exact_name_candidate = False

        def md_row_is_candidate(text: str) -> bool:
            row_text = re.sub(r"\s+", " ", text or "").strip()
            if not row_text or re.search(r"Home|Privacy|Accessibility|Log in|Register|Clear all filters", row_text, re.I):
                return False
            row_digits = digits_only(row_text)
            row_name = normalize_name(row_text)
            if ein in row_digits or formatted_ein in row_text:
                return True
            if ein and not allow_exact_name_candidate:
                return False
            if text_exposes_ein(row_text):
                return False
            return bool(any(name and name in row_name for name in md_wanted_names))

        wanted_name = normalize_name(org.organization_name)
        body = ""
        for search_value in [formatted_ein, ein]:
            submit_md_search(search_value)
            body = wait_for_md_match()
            if md_body_has_match(body):
                break

        name_confirmed_search = False
        if not md_body_has_match(body) and org.organization_name and not org.organization_name.lower().startswith("ein "):
            for name_search_value in md_name_variants(org.organization_name):
                submit_md_name_search(name_search_value)
                name_body = wait_for_md_match()
                if md_body_has_match(name_body) or (
                    md_body_has_exact_name(name_body)
                    and not body_says_no_results(name_body)
                    and not body_says_pending_or_error(name_body)
                ):
                    body = name_body
                    name_confirmed_search = True
                    break
                if not ein and not body_says_no_results(name_body) and not body_says_pending_or_error(name_body):
                    body = name_body
                    break
        ein_confirmed_search = bool(ein and md_body_has_match(body))
        allow_exact_name_candidate = bool(not ein_confirmed_search and name_confirmed_search)

        if not md_body_has_match(body) and body_says_no_results(body):
            result.raw_status_text = "No record found"
            result.status = STATUS_NOT_REGISTERED
            result.source_note = "Maryland search returned no matching EIN record."
            result.success = True
            return result

        if MD_FAST_SEARCH_ONLY and not org.evidence_mode and md_body_has_record(body) and text_contains_requested_ein(body, org.ein):
            result.raw_status_text = "Maryland record found"
            result.status = STATUS_UNKNOWN
            result.source_note = "Maryland public search returned a matching record; detailed source evidence is captured on demand when the snapshot PDF is opened."
            result.success = True
            return result

        clicked_result = False
        if md_body_has_record(body):
            fast_result_selectors = []
            if org.organization_name:
                escaped_name = org.organization_name.replace('"', '\\"')
                fast_result_selectors.extend([
                    f'a:has-text("{escaped_name}")',
                ])
            fast_result_selectors.extend([
                f'a:has-text("{formatted_ein}")',
                f'a:has-text("{ein}")',
                "a[href*='sos-charity']",
                "a[href*='SOS']",
            ])
            for selector in fast_result_selectors:
                try:
                    candidate = page.locator(selector).first
                    if candidate.count() > 0 and candidate.is_visible(timeout=500):
                        try:
                            candidate_text = re.sub(r"\s+", " ", candidate.inner_text(timeout=750)).strip()
                        except Exception:
                            candidate_text = ""
                        if candidate_text and not md_row_is_candidate(candidate_text):
                            continue
                        candidate.click(timeout=3000)
                        clicked_result = True
                        break
                except Exception:
                    continue
        row_selectors = [
            "tbody tr",
            "tr",
            "[role='row']",
            "article",
            "li",
            ".card",
            ".list-group-item",
            ".list-view-item",
            ".search-result",
            "a[href]",
        ]
        for selector in row_selectors:
            try:
                rows = page.locator(selector)
                count = min(rows.count(), 25)
                for i in range(count):
                    row = rows.nth(i)
                    try:
                        if not row.is_visible(timeout=250):
                            continue
                        row_text = re.sub(r"\s+", " ", row.inner_text(timeout=750)).strip()
                        if not md_row_is_candidate(row_text):
                            continue
                        if selector == "a[href]":
                            row.click(timeout=3000)
                            clicked_result = True
                        else:
                            links = row.locator("a[href]")
                            if links.count() > 0:
                                links.first.click(timeout=3000)
                                clicked_result = True
                            else:
                                row.click(timeout=3000)
                                clicked_result = True
                        break
                    except Exception:
                        continue
                if clicked_result:
                    break
            except Exception:
                continue
        if not clicked_result and md_body_has_record(body):
            for selector in ["a[href]", "tbody tr", "[role='row']", ".card", ".search-result", ".list-view-item"]:
                try:
                    items = page.locator(selector)
                    count = min(items.count(), 12)
                    for i in range(count):
                        item = items.nth(i)
                        try:
                            if not item.is_visible(timeout=250):
                                continue
                            text = re.sub(r"\s+", " ", item.inner_text(timeout=750)).strip()
                            if not md_row_is_candidate(text):
                                continue
                            links = item.locator("a[href]")
                            if selector == "a[href]":
                                item.click(timeout=3000)
                            elif links.count() > 0:
                                links.first.click(timeout=3000)
                            else:
                                item.click(timeout=3000)
                            clicked_result = True
                            break
                        except Exception:
                            continue
                    if clicked_result:
                        break
                except Exception:
                    continue
        if not clicked_result:
            if md_body_has_record(body):
                if ein:
                    result.raw_status_text = "No matching EIN result"
                    result.status = STATUS_NOT_REGISTERED
                    result.source_note = "Maryland public search returned a record by name, but did not confirm the requested EIN."
                    result.success = True
                    return result
                result.raw_status_text = "Record found; detail page not opened"
                result.status = STATUS_UNKNOWN
                result.source_note = "Maryland public search returned a record for the EIN search, but the detail page could not be opened automatically."
                result.success = True
                return result
            result.raw_status_text = "No matching EIN result"
            result.status = STATUS_NOT_REGISTERED
            result.source_note = "Maryland search results did not contain a matching EIN row."
            result.success = True
            return result

        safe_wait_for_network_idle(page, timeout=1500)
        detail_text = page.locator("body").inner_text(timeout=5000)
        if text_has_wrong_ein_match(detail_text, org.ein):
            return reject_wrong_ein_result(result, "Maryland")
        registration_status = ""
        deadline = time.time() + min(STATE_RESULT_WAIT_SECONDS, 5)
        while time.time() < deadline:
            registration_status = extract_labeled_value(page, ["Registration Status"])
            if registration_status:
                break
            fast_sleep(0.25)
        result.raw_status_text = registration_status
        result.status = registration_status if registration_status else STATUS_UNKNOWN
        if ein_confirmed_search:
            result.source_note = "Maryland uses the exact Registration Status from a detail page reached through an EIN-confirmed public registry search."
        elif name_confirmed_search:
            result.source_note = "Maryland uses the exact Registration Status from a detail page reached through an exact-name public registry search."
        else:
            result.source_note = "Maryland uses the exact Registration Status from the public detail page."
        result.success = True
        return result
    except Exception as e:
        result.error = f"MD error: {e}"
        return result

def search_sc(page, org: Organization) -> StateResult:
    url = "https://search.scsos.com/charities"
    result = StateResult(org.organization_name, org.ein, "SC", STATUS_UNKNOWN, url)
    try:
        last_goto_error = None
        for goto_attempt in range(2):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                safe_wait_for_network_idle(page, timeout=15000)
                fast_sleep(1)
                last_goto_error = None
                break
            except Exception as e:
                last_goto_error = e
                if goto_attempt == 0:
                    fast_sleep(3)
                    continue
        if last_goto_error:
            raise last_goto_error

        name_input = find_visible_input(page, [
            "#MainContent_txt_CharitySearchName",
            'input[name="ctl00$MainContent$txt_CharitySearchName"]',
            'input[type="text"]',
        ])
        if not name_input:
            result.error = "Could not find SC organization name input"
            return result
        name_input.fill("")
        name_input.fill(org.organization_name)

        clicked_search = False
        for sel in [
            "#MainContent_butt_Search",
            'input[name="ctl00$MainContent$butt_Search"]',
            'input[type="submit"][value="Search"]',
            'input[type="submit"]',
        ]:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=1000):
                    btn.click(timeout=5000)
                    clicked_search = True
                    break
            except Exception:
                continue
        if not clicked_search:
            result.error = "Could not click SC Search button"
            return result

        page.wait_for_load_state("domcontentloaded", timeout=10000)
        safe_wait_for_network_idle(page, timeout=5000)
        fast_sleep(0.75)

        body = ""
        deadline = time.time() + STATE_RESULT_WAIT_SECONDS
        while time.time() < deadline:
            body = page.locator("body").inner_text(timeout=5000)
            try:
                if page.locator("a[href*='CharityInfo']").count() > 0:
                    break
            except Exception:
                pass
            if re.search(r"\bNo records?\b|No results|0 results", body, re.I):
                break
            fast_sleep(0.75)

        if re.search(r"\bNo records?\b|No results|0 results", body, re.I):
            result.raw_status_text = "No record found"
            result.status = STATUS_NOT_REGISTERED
            result.source_note = "South Carolina search returned no matching organization result."
            result.success = True
            return result

        wanted = normalize_name(org.organization_name)
        clicked_result = False
        links = page.locator("a[href*='CharityInfo']")
        candidates = []
        try:
            count = min(links.count(), 100)
            for i in range(count):
                link = links.nth(i)
                try:
                    txt = re.sub(r"\s+", " ", link.inner_text(timeout=1000)).strip()
                    normalized = normalize_name(txt)
                    if normalized == wanted:
                        link.click(timeout=5000)
                        clicked_result = True
                        break
                    if wanted and (wanted in normalized or normalized in wanted):
                        score = 2 if normalized.startswith(wanted) or wanted.startswith(normalized) else 1
                        candidates.append((score, link))
                except Exception:
                    continue
        except Exception:
            pass
        if not clicked_result and candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)
            candidates[0][1].click(timeout=5000)
            clicked_result = True
        if not clicked_result:
            result.raw_status_text = "No matching organization result"
            result.status = STATUS_NOT_REGISTERED
            result.source_note = "South Carolina search results did not contain a matching organization link."
            result.success = True
            return result

        page.wait_for_load_state("domcontentloaded", timeout=30000)
        safe_wait_for_network_idle(page, timeout=30000)
        fast_sleep(2)
        try:
            page.locator("body").evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except Exception:
            pass
        fast_sleep(2)

        detail_text = page.locator("body").inner_text(timeout=15000)
        if text_has_wrong_ein_match(detail_text, org.ein):
            return reject_wrong_ein_result(result, "South Carolina")
        m = re.search(r"Due Date:\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})", detail_text, re.I)
        due_raw = m.group(1).strip() if m else extract_labeled_value_from_text(detail_text, ["Due Date"])
        due_date = parse_date_value(due_raw)
        if due_date:
            result.raw_status_text = due_raw
            result.status = status_from_due_date(due_date)
            result.source_note = "South Carolina uses the Due Date shown in the Next Report section."
            result.success = True
            return result

        status_text = extract_labeled_value(page, ["Status", "Registration Status"]) or extract_labeled_value_from_text(detail_text, ["Status", "Registration Status"])
        result.raw_status_text = status_text or "Due Date not found"
        result.status = status_text if status_text else STATUS_UNKNOWN
        result.source_note = "South Carolina fallback uses visible registration status when no Due Date is exposed."
        result.success = True
        return result
    except Exception as e:
        result.error = f"SC error: {e}"
        return result

def search_hi(page, org: Organization) -> StateResult:
    url = "https://charity.ehawaii.gov/charity/new-search.html"
    result = StateResult(org.organization_name, org.ein, "HI", STATUS_UNKNOWN, url)
    try:
        ein_digits = digits_only(org.ein)
        formatted_ein = format_ein_with_dash(org.ein) if ein_digits else ""

        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        safe_wait_for_network_idle(page, timeout=20000)
        fast_sleep(3)

        contains_selected = False
        for sel in ["#nameFilter", 'select[name="nameFilter"]']:
            try:
                dropdown = page.locator(sel).first
                if dropdown.is_visible(timeout=1000):
                    dropdown.select_option(label="Contains...")
                    contains_selected = True
                    break
            except Exception:
                continue
        if not contains_selected:
            result.error = "Could not set HI search dropdown to Contains"
            return result

        name_input = find_visible_input(page, [
            "#name",
            'input[name="name"]',
            'input[id="name"]',
        ])
        if not name_input:
            result.error = "Could not find HI organization name input"
            return result

        fein_input = find_visible_input(page, [
            "#fein",
            'input[name="fein"]',
            'input[id="fein"]',
        ])
        if not fein_input:
            result.error = "Could not find HI FEIN input"
            return result

        name_input.click(timeout=5000)
        name_input.fill("")
        name_input.type(org.organization_name, delay=85)
        fast_sleep(0.5)
        fein_input.click(timeout=5000)
        fein_input.fill("")
        if formatted_ein:
            fein_input.type(formatted_ein, delay=85)
        fast_sleep(0.5)

        clicked_search = False
        for sel in [
            "#trigger-organization-search",
            'button[id="trigger-organization-search"]',
            'button[type="submit"]',
            'button',
            'input[type="submit"]',
            'input[type="button"]',
        ]:
            try:
                buttons = page.locator(sel)
                count = min(buttons.count(), 10)
                for i in range(count):
                    btn = buttons.nth(i)
                    try:
                        text = re.sub(r"\s+", " ", btn.inner_text(timeout=1000)).strip()
                    except Exception:
                        text = (btn.get_attribute("value") or "").strip()
                    if btn.is_visible(timeout=750) and re.search(r"\bSearch\b", text, re.I):
                        btn.click(timeout=5000)
                        clicked_search = True
                        break
                if clicked_search:
                    break
            except Exception:
                continue
        if not clicked_search:
            result.error = "Could not click HI Search button"
            return result

        safe_wait_for_network_idle(page, timeout=30000)
        fast_sleep(3)

        body = page.locator("body").inner_text(timeout=15000)
        if re.search(
            r"no results|no records|0 results|showing 0 to 0 of 0 entries|no data available in table|not registered in our system",
            body,
            re.I,
        ):
            result.raw_status_text = "No record found"
            result.status = STATUS_NOT_REGISTERED
            result.source_note = "Hawaii search returned no matching organization result."
            result.success = True
            return result

        wanted = normalize_name(org.organization_name)
        best_priority = -1
        best_row = None
        best_selector = ""
        best_index = -1
        for selector in ["#searchOrgTable tbody tr", "#searchResultTable tbody tr", "table tbody tr"]:
            try:
                rows = page.locator(selector)
                count = min(rows.count(), 100)
                for i in range(count):
                    row = rows.nth(i)
                    try:
                        if not row.is_visible(timeout=750):
                            continue
                        row_text = re.sub(r"\s+", " ", row.inner_text(timeout=1500)).strip()
                        if not row_text or re.search(r"no data available in table", row_text, re.I):
                            continue
                        row_digits = digits_only(row_text)
                        if ein_digits and ein_digits not in row_digits:
                            continue
                        link_text = ""
                        try:
                            links = row.locator("a[href]")
                            if links.count() > 0:
                                link_text = re.sub(r"\s+", " ", links.first.inner_text(timeout=1000)).strip()
                        except Exception:
                            pass
                        candidate_name = normalize_name(link_text or row_text)
                        priority = -1
                        if ein_digits and ein_digits in row_digits:
                            priority = 3
                        elif wanted and candidate_name == wanted:
                            priority = 2
                        elif wanted and (wanted in candidate_name or candidate_name in wanted or wanted in normalize_name(row_text)):
                            priority = 1
                        if priority > best_priority:
                            best_priority = priority
                            best_row = row
                            best_selector = selector
                            best_index = i
                    except Exception:
                        continue
            except Exception:
                continue

        if best_row is None or best_priority < 0:
            result.raw_status_text = "No matching organization result"
            result.status = STATUS_NOT_REGISTERED
            result.source_note = "Hawaii search results did not contain a matching organization row."
            result.success = True
            return result

        clicked_result = False
        try:
            row = page.locator(best_selector).nth(best_index)
            links = row.locator("a[href]")
            if links.count() > 0:
                links.first.click(timeout=5000)
                clicked_result = True
            else:
                row.click(timeout=5000)
                clicked_result = True
        except Exception:
            pass
        if not clicked_result:
            result.raw_status_text = "No matching organization result"
            result.status = STATUS_NOT_REGISTERED
            result.source_note = "Hawaii search results did not contain a clickable organization row."
            result.success = True
            return result

        page.wait_for_load_state("domcontentloaded", timeout=30000)
        safe_wait_for_network_idle(page, timeout=20000)
        fast_sleep(2)

        detail_text = page.locator("body").inner_text(timeout=12000)
        detail_ein = (
            extract_labeled_value(page, ["FEIN", "Federal Tax ID (EIN)", "Federal Tax ID", "EIN"])
            or extract_labeled_value_from_text(detail_text, ["FEIN", "Federal Tax ID (EIN)", "Federal Tax ID", "EIN"])
        )
        if detail_ein and digits_only(detail_ein) != ein_digits:
            return reject_wrong_ein_result(result, "Hawaii")
        if not detail_ein and not text_contains_requested_ein(detail_text, org.ein):
            return reject_wrong_ein_result(result, "Hawaii")
        status_text = extract_labeled_value(page, ["Registration Status"])
        if not status_text:
            status_text = extract_labeled_value_from_text(detail_text, ["Registration Status"])
        if not status_text:
            status_text = extract_labeled_value(page, ["Status"])
        if not status_text:
            status_text = extract_labeled_value_from_text(detail_text, ["Status"])

        result.raw_status_text = status_text
        result.status = status_text if status_text else STATUS_UNKNOWN
        result.source_note = "Registration status (HI)"
        result.success = True
        return result
    except Exception as e:
        result.error = f"HI error: {e}"
        return result

def search_me(page, org: Organization) -> StateResult:
    url = "https://www.pfr.maine.gov/almsonline/almsquery/SearchCompany.aspx"
    result = StateResult(org.organization_name, org.ein, "ME", STATUS_UNKNOWN, url)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        safe_wait_for_network_idle(page, timeout=5000)
        fast_sleep(1)

        regulator = None
        for sel in ["#scRegulator", 'select[name="ctl00$ctl00$mainContent$mainContent$scRegulator"]']:
            try:
                loc = page.locator(sel).first
                loc.wait_for(state="visible", timeout=3000)
                regulator = loc
                break
            except Exception:
                continue
        if not regulator:
            result.error = "Could not find ME Regulator dropdown"
            return result
        regulator.select_option(label="ALL")
        fast_sleep(1)

        name_input = None
        for sel in ["#scCompanyName", 'input[name="ctl00$ctl00$mainContent$mainContent$scCompanyName"]']:
            try:
                loc = page.locator(sel).first
                loc.wait_for(state="visible", timeout=3000)
                name_input = loc
                break
            except Exception:
                continue
        if not name_input:
            result.error = "Could not find ME Company Name input"
            return result
        name_input.click(timeout=3000)
        name_input.fill("")
        name_input.fill(org.organization_name)
        fast_sleep(1)

        search_button = None
        for sel in ["#btnSearch", 'input[name="ctl00$ctl00$mainContent$mainContent$btnSearch"]', 'input[type="submit"][value="Search"]']:
            try:
                loc = page.locator(sel).first
                loc.wait_for(state="visible", timeout=3000)
                search_button = loc
                break
            except Exception:
                continue
        if not search_button:
            result.error = "Could not find ME Search button"
            return result
        search_button.click(timeout=3000, no_wait_after=True)
        fast_sleep(1.5)
        safe_wait_for_network_idle(page, timeout=2500)
        fast_sleep(0.5)

        body = page.locator("body").inner_text(timeout=4000)
        if re.search(r"0 records found|no records|no results|no companies found|no data", body, re.I):
            result.raw_status_text = "No record found"
            result.status = STATUS_NOT_REGISTERED
            result.source_note = "Maine search returned no matching organization result."
            result.success = True
            return result

        target_exact = re.sub(r"\s+", " ", (org.organization_name or "").strip()).upper()
        target_normalized = normalize_name(org.organization_name)

        best_table_status = ""
        best_table_row = ""
        best_table_score = (-1, -999)
        try:
            rows = page.locator("tr")
            for i in range(min(rows.count(), 100)):
                row = rows.nth(i)
                try:
                    if not row.is_visible(timeout=750):
                        continue
                    row_text = re.sub(r"\s+", " ", row.inner_text(timeout=1500)).strip()
                    if not row_text or re.search(r"\b(Name|Number|Location|Profession|Status)\b", row_text, re.I) and not re.search(r"\b(ACTIVE|FAILED\s+TO\s+RENEW|EXPIRED|REVOKED|SUSPENDED|INACTIVE|CURRENT)\b", row_text, re.I):
                        continue
                    links = row.locator("a[href]")
                    link_text = ""
                    if links.count() > 0:
                        link_text = re.sub(r"\s+", " ", links.first.inner_text(timeout=1000)).strip()
                    row_name_normalized = normalize_name(link_text or row_text)
                    name_priority = -1
                    if link_text.upper() == target_exact:
                        name_priority = 3
                    elif row_name_normalized == target_normalized:
                        name_priority = 2
                    elif target_normalized and (target_normalized in row_name_normalized or row_name_normalized in target_normalized):
                        name_priority = 1
                    if name_priority < 0:
                        continue
                    status_match = re.search(
                        r"\b(ACTIVE|FAILED\s+TO\s+RENEW|EXPIRED|REVOKED|SUSPENDED|INACTIVE|CURRENT)\b",
                        row_text,
                        re.I,
                    )
                    if not status_match:
                        continue
                    row_status = re.sub(r"\s+", " ", status_match.group(1)).strip()
                    status_priority = 0
                    if re.search(r"\bACTIVE\b", row_status, re.I):
                        status_priority = 10
                    elif re.search(r"\b(CURRENT|GOOD\s+STANDING)\b", row_status, re.I):
                        status_priority = 8
                    elif re.search(r"\b(FAILED\s+TO\s+RENEW|EXPIRED|REVOKED|SUSPENDED|INACTIVE)\b", row_status, re.I):
                        status_priority = -10
                    if (name_priority, status_priority) > best_table_score:
                        best_table_score = (name_priority, status_priority)
                        best_table_status = row_status
                        best_table_row = row_text
                except Exception:
                    continue
        except Exception:
            pass
        best_link = None
        best_priority = -1
        best_status_priority = -999
        best_row_text = ""
        for selector in ["a[href*='ShowDetail.aspx']", "a[href]"]:
            try:
                links = page.locator(selector)
                count = min(links.count(), 100)
                for i in range(count):
                    link = links.nth(i)
                    try:
                        if not link.is_visible(timeout=750):
                            continue
                        txt = re.sub(r"\s+", " ", link.inner_text(timeout=1500)).strip()
                        if not txt:
                            continue
                        link_exact = txt.upper()
                        link_normalized = normalize_name(txt)
                        priority = -1
                        if link_exact == target_exact:
                            priority = 3
                        elif link_normalized == target_normalized:
                            priority = 2
                        elif target_normalized and (target_normalized in link_normalized or link_normalized in target_normalized):
                            priority = 1
                        status_priority = 0
                        row_text = txt
                        try:
                            row_text = re.sub(r"\s+", " ", link.locator("xpath=ancestor::tr[1]").inner_text(timeout=1500)).strip()
                            if re.search(r"\bACTIVE\b", row_text, re.I):
                                status_priority = 5
                            elif re.search(r"\b(CURRENT|GOOD\s+STANDING)\b", row_text, re.I):
                                status_priority = 4
                            elif re.search(r"\b(FAILED\s+TO\s+RENEW|EXPIRED|REVOKED|SUSPENDED|INACTIVE)\b", row_text, re.I):
                                status_priority = -5
                        except Exception:
                            status_priority = 0
                        if priority > best_priority or (priority == best_priority and status_priority > best_status_priority):
                            best_priority = priority
                            best_status_priority = status_priority
                            best_link = link
                            best_row_text = row_text
                    except Exception:
                        continue
            except Exception:
                continue

        if not best_link or best_priority < 0:
            result.raw_status_text = "No matching organization result"
            result.status = STATUS_NOT_REGISTERED
            result.source_note = "Maine search results did not contain a matching organization link."
            result.success = True
            return result

        fallback_row_status = ""
        row_status_match = re.search(
            r"\b(ACTIVE|FAILED\s+TO\s+RENEW|EXPIRED|REVOKED|SUSPENDED|INACTIVE|CURRENT)\b",
            best_row_text or "",
            re.I,
        )
        if row_status_match:
            fallback_row_status = re.sub(r"\s+", " ", row_status_match.group(1)).strip()

        try:
            href = (best_link.get_attribute("href") or "").strip()
        except Exception:
            href = ""
        detail_text = ""
        last_detail_error = None
        detail_url = ""
        if href:
            detail_url = href
            if not detail_url.lower().startswith("http"):
                detail_url = "https://www.pfr.maine.gov/ALMSOnline/ALMSQuery/" + detail_url.lstrip("/")

        def me_detail_page_ready() -> bool:
            try:
                rows = page.locator("tr.detail")
                count = min(rows.count(), 50)
                found_license = False
                found_status = False
                for row_idx in range(count):
                    row = rows.nth(row_idx)
                    try:
                        label = re.sub(r"\s+", " ", row.locator("td.label").inner_text(timeout=1000)).strip().lower()
                        if label == "license number":
                            found_license = True
                        elif label == "status":
                            found_status = True
                    except Exception:
                        continue
                if found_license and found_status:
                    return True
            except Exception:
                pass
            try:
                header_text = page.locator("body").inner_text(timeout=5000)
            except Exception:
                return False
            normalized_header = re.sub(r"\s+", " ", header_text)
            if re.search(r"License Number", normalized_header, re.I) and re.search(r"Status", normalized_header, re.I):
                return True
            return False

        for detail_attempt in range(1):
            try:
                if detail_attempt > 0:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    safe_wait_for_network_idle(page, timeout=10000)
                    fast_sleep(1)
                    regulator = None
                    for sel in ["#scRegulator", 'select[name="ctl00$ctl00$mainContent$mainContent$scRegulator"]']:
                        try:
                            loc = page.locator(sel).first
                            loc.wait_for(state="visible", timeout=15000)
                            regulator = loc
                            break
                        except Exception:
                            continue
                    if not regulator:
                        raise RuntimeError("Could not find ME Regulator dropdown after retry.")
                    regulator.select_option(label="ALL")
                    fast_sleep(1)

                    name_input = None
                    for sel in ["#scCompanyName", 'input[name="ctl00$ctl00$mainContent$mainContent$scCompanyName"]']:
                        try:
                            loc = page.locator(sel).first
                            loc.wait_for(state="visible", timeout=15000)
                            name_input = loc
                            break
                        except Exception:
                            continue
                    if not name_input:
                        raise RuntimeError("Could not find ME Company Name input after retry.")
                    name_input.click(timeout=5000)
                    name_input.fill("")
                    name_input.type(org.organization_name, delay=85)
                    fast_sleep(1)

                    search_button = None
                    for sel in ["#btnSearch", 'input[name="ctl00$ctl00$mainContent$mainContent$btnSearch"]', 'input[type="submit"][value="Search"]']:
                        try:
                            loc = page.locator(sel).first
                            loc.wait_for(state="visible", timeout=15000)
                            search_button = loc
                            break
                        except Exception:
                            continue
                    if not search_button:
                        raise RuntimeError("Could not find ME Search button after retry.")
                    search_button.click(timeout=5000, no_wait_after=True)
                    fast_sleep(5)
                    safe_wait_for_network_idle(page, timeout=10000)
                    fast_sleep(1)

                    reacquired_link = None
                    best_priority = -1
                    for selector in ["a[href*='ShowDetail.aspx']", "a[href]"]:
                        try:
                            links = page.locator(selector)
                            count = min(links.count(), 100)
                            for i in range(count):
                                link = links.nth(i)
                                try:
                                    if not link.is_visible(timeout=750):
                                        continue
                                    txt = re.sub(r"\s+", " ", link.inner_text(timeout=1500)).strip()
                                    if not txt:
                                        continue
                                    link_exact = txt.upper()
                                    link_normalized = normalize_name(txt)
                                    priority = -1
                                    if link_exact == target_exact:
                                        priority = 3
                                    elif link_normalized == target_normalized:
                                        priority = 2
                                    elif target_normalized and (target_normalized in link_normalized or link_normalized in target_normalized):
                                        priority = 1
                                    if priority > best_priority:
                                        best_priority = priority
                                        reacquired_link = link
                                except Exception:
                                    continue
                        except Exception:
                            continue
                    if not reacquired_link or best_priority < 0:
                        raise RuntimeError("Could not reacquire ME detail link after retry.")
                    try:
                        href = (reacquired_link.get_attribute("href") or "").strip()
                    except Exception:
                        href = ""
                    detail_url = href
                    if detail_url and not detail_url.lower().startswith("http"):
                        detail_url = "https://www.pfr.maine.gov/ALMSOnline/ALMSQuery/" + detail_url.lstrip("/")
                    best_link = reacquired_link

                if detail_url:
                    page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
                else:
                    best_link.click(timeout=5000, no_wait_after=True)
                    fast_sleep(5)
                safe_wait_for_network_idle(page, timeout=10000)
                fast_sleep(1)
                if not me_detail_page_ready():
                    raise RuntimeError("ME detail page markers not found after navigation.")
                detail_text = page.locator("body").inner_text(timeout=30000)
                last_detail_error = None
                break
            except Exception as e:
                last_detail_error = e
                if detail_attempt == 0:
                    fast_sleep(3)
                    continue
        if last_detail_error:
            raise last_detail_error

        header_match = re.search(
            r"License Number:\s*([A-Za-z0-9-]+)\s+Status:\s*(.+?)\s+Expiration Date:",
            re.sub(r"\s+", " ", detail_text),
            re.I | re.S,
        )
        license_number = ""
        status_text = ""
        if header_match:
            license_number = header_match.group(1).strip()
            status_text = header_match.group(2).strip()
        if not license_number:
            license_number = extract_labeled_value(page, ["License Number"]) or extract_labeled_value_from_text(detail_text, ["License Number"])
        if not status_text:
            status_text = extract_labeled_value_from_text(detail_text, ["Status"])
        if not status_text:
            if fallback_row_status:
                result.raw_status_text = fallback_row_status
                result.status = fallback_row_status
                result.source_note = "Maine uses the Status shown on the matched search result row."
            else:
                result.raw_status_text = "Status not found"
                result.status = STATUS_UNKNOWN
                result.source_note = "Registration status with definition (ME)"
            result.success = True
            return result

        combined_status = status_text
        expiration_text = extract_labeled_value(page, ["Expiration Date", "Expiration"]) or extract_labeled_value_from_text(detail_text, ["Expiration Date", "Expiration"])
        if expiration_text:
            combined_status = f"{combined_status}; expiration date {expiration_text}"

        result.raw_status_text = combined_status
        result.status = status_text
        result.source_note = "Registration status with definition (ME)"
        result.success = True
        return result
    except Exception as e:
        result.error = f"ME error: {e}"
        return result

def search_nd(page, org: Organization) -> StateResult:
    url = "https://firststop.sos.nd.gov/search/charitable"
    result = StateResult(org.organization_name, org.ein, "ND", STATUS_UNKNOWN, url)
    try:
        last_goto_error = None
        for goto_attempt in range(2):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                safe_wait_for_network_idle(page, timeout=20000)
                fast_sleep(3)
                last_goto_error = None
                break
            except Exception as e:
                last_goto_error = e
                if goto_attempt == 0:
                    fast_sleep(4)
                    continue
        if last_goto_error:
            raise last_goto_error

        search_input = find_visible_input(page, [
            'input[placeholder*="Search by name"]',
            'input[aria-label*="Search by name"]',
            'input[type="text"]',
        ])
        if not search_input:
            result.error = "Could not find ND search input"
            return result
        search_input.click(timeout=5000)
        search_input.fill("")
        search_input.type(org.organization_name, delay=85)
        fast_sleep(1)

        search_button = None
        for sel in ['button[aria-label="Execute search"]', 'button[aria-label*="Execute search"]']:
            try:
                loc = page.locator(sel).first
                loc.wait_for(state="visible", timeout=10000)
                search_button = loc
                break
            except Exception:
                continue
        if not search_button:
            result.error = "Could not find ND search button"
            return result
        search_button.click(timeout=5000)
        fast_sleep(6)
        safe_wait_for_network_idle(page, timeout=20000)
        fast_sleep(2)

        body = page.locator("body").inner_text(timeout=15000)
        if re.search(r"Results:\s*0\b|No results|No matching", body, re.I):
            result.raw_status_text = "No record found"
            result.status = STATUS_NOT_REGISTERED
            result.source_note = "North Dakota search returned no matching organization result."
            result.success = True
            return result

        target_exact = re.sub(r"\s+", " ", (org.organization_name or "").strip()).upper()
        target_normalized = normalize_name(org.organization_name)
        best_button = None
        best_priority = -1
        best_status_score = -999
        for selector in ['div.interactive-cell-button', 'div[role="button"]']:
            try:
                items = page.locator(selector)
                count = min(items.count(), 100)
                for i in range(count):
                    item = items.nth(i)
                    try:
                        if not item.is_visible(timeout=750):
                            continue
                        txt = item.inner_text(timeout=1500)
                        row_txt = txt
                        try:
                            row_txt = item.locator("xpath=ancestor::*[self::tr or @role='row' or contains(@class,'row')][1]").inner_text(timeout=1000)
                        except Exception:
                            try:
                                row_txt = item.locator("xpath=ancestor::div[contains(@class,'row')][1]").inner_text(timeout=1000)
                            except Exception:
                                row_txt = txt
                        combined_txt = re.sub(r"\s+", " ", f"{txt} {row_txt}").strip()
                        lines = [re.sub(r"\s+", " ", ln).strip() for ln in txt.splitlines() if ln.strip()]
                        if not lines:
                            continue
                        if text_has_wrong_ein_match(combined_txt, org.ein):
                            continue
                        name_text = lines[0]
                        name_exact = name_text.upper()
                        name_normalized = normalize_name(name_text)
                        priority = -1
                        if name_exact == target_exact:
                            priority = 3
                        elif name_normalized == target_normalized:
                            priority = 2
                        elif target_normalized and (target_normalized in name_normalized or name_normalized in target_normalized):
                            priority = 1
                        status_score = 0
                        if re.search(r"\b(active|current|good standing|registered)\b", combined_txt, re.I):
                            status_score += 5
                        if re.search(r"\b(inactive|closed|expired|failed|failed to renew|revoked|terminated|withdrawn|cancelled|canceled)\b", combined_txt, re.I):
                            status_score -= 8
                        if (priority, status_score) > (best_priority, best_status_score):
                            best_priority = priority
                            best_status_score = status_score
                            best_button = item
                    except Exception:
                        continue
            except Exception:
                continue

        if not best_button or best_priority < 0:
            result.raw_status_text = "No matching organization result"
            result.status = STATUS_NOT_REGISTERED
            result.source_note = "North Dakota search results did not contain a matching organization entry."
            result.success = True
            return result

        best_button.click(timeout=5000)
        try:
            page.get_by_text("Registration Date", exact=True).wait_for(timeout=15000)
        except Exception:
            fast_sleep(4)
        safe_wait_for_network_idle(page, timeout=10000)
        fast_sleep(1)

        detail_text = page.locator("body").inner_text(timeout=15000)
        if text_has_wrong_ein_match(detail_text, org.ein):
            return reject_wrong_ein_result(result, "North Dakota")
        status_text = ""
        try:
            detail_rows = page.locator("tr.detail")
            count = min(detail_rows.count(), 50)
            for i in range(count):
                row = detail_rows.nth(i)
                label_text = re.sub(r"\s+", " ", row.locator("td.label").inner_text(timeout=1500)).strip()
                if label_text.lower() == "status":
                    status_text = re.sub(r"\s+", " ", row.locator("td.value").inner_text(timeout=1500)).strip()
                    break
        except Exception:
            pass
        if not status_text:
            m = re.search(r"Status\s+(.+?)\s+AR Due Date", re.sub(r"\s+", " ", detail_text), re.I)
            if m:
                status_text = m.group(1).strip()
        if not status_text:
            result.raw_status_text = "Status not found"
            result.status = STATUS_UNKNOWN
            result.source_note = "Registration status (ND FirstStop)"
            result.success = True
            return result

        status_text = re.sub(r"\s+", " ", status_text).strip()
        result.raw_status_text = status_text
        result.status = status_text
        result.source_note = "Registration status (ND FirstStop)"
        result.success = True
        return result
    except Exception as e:
        result.error = f"ND error: {e}"
        return result

def main() -> int:
    parser = argparse.ArgumentParser(description="Sequential charity compliance checker for CA, MA, MD, CO, NY, NJ, PA, VA, SC, AK, HI, ME, and ND.")
    parser.add_argument("--input", required=True, help="CSV with organization_name,ein")
    parser.add_argument("--states", default="CA,MA,MD,CO,NY,NJ,PA,VA,SC,AK,HI,ME,ND", help="Comma-separated subset of CA,MA,MD,CO,NY,NJ,PA,VA,SC,AK,HI,ME,ND")
    parser.add_argument("--output-prefix", default=f"charity_status_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}", help="Output file prefix")
    parser.add_argument("--artifacts-dir", default="artifacts", help="Folder for screenshots and HTML")
    parser.add_argument("--headful", action="store_true", help="Show browser")
    parser.add_argument("--show-process", action="store_true", help="Show browser with slower actions for watching the run")
    parser.add_argument("--slow-mo-ms", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if args.show_process:
        args.headful = True
        if args.slow_mo_ms <= 0:
            args.slow_mo_ms = 500

    states = [s.strip().upper() for s in args.states.split(",") if s.strip()]
    for s in states:
        if s not in {"CA", "MA", "MD", "CO", "NY", "NJ", "PA", "VA", "SC", "AK", "HI", "ME", "ND"}:
            raise ValueError("This version supports only CA, MA, MD, CO, NY, NJ, PA, VA, SC, AK, HI, ME, and ND.")

    orgs = read_input_csv(Path(args.input))
    if args.limit > 0:
        orgs = orgs[:args.limit]

    results: List[StateResult] = []
    artifacts_dir = Path(args.artifacts_dir)

    with sync_playwright() as p:
        # Isolate brittle state sites by using a fresh browser session for each org/state pair.
        for org in orgs:
            for st in states:
                print(f"[{st}] Starting {org.organization_name} / {org.ein}", flush=True)
                r = StateResult(org.organization_name, org.ein, st, STATUS_UNKNOWN, "")
                browser = None
                context = None
                page = None
                try:
                    browser = p.chromium.launch(headless=not args.headful, slow_mo=args.slow_mo_ms)
                    if st == "AK":
                        r = search_ak(browser, org, artifacts_dir)
                    else:
                        context = browser.new_context()
                        page = context.new_page()
                        if st == "CA":
                            r = search_ca(page, org)
                        elif st == "MA":
                            r = search_ma(page, org)
                        elif st == "MD":
                            r = search_md(page, org)
                        elif st == "CO":
                            r = search_co(page, org)
                        elif st == "NY":
                            r = search_ny(page, org)
                        elif st == "NJ":
                            r = search_nj(page, org)
                        elif st == "PA":
                            r = search_pa(page, org)
                        elif st == "VA":
                            r = search_va(page, org)
                        elif st == "SC":
                            r = search_sc(page, org)
                        elif st == "HI":
                            r = search_hi(page, org)
                        elif st == "ME":
                            r = search_me(page, org)
                        elif st == "ND":
                            r = search_nd(page, org)
                        else:
                            raise ValueError(f"Unsupported state: {st}")
                        if st == "ND":
                            state_dir = artifacts_dir / st
                            state_dir.mkdir(parents=True, exist_ok=True)
                            safe_name = re.sub(r"[^A-Za-z0-9]+", "_", org.organization_name).strip("_")[:80]
                            try:
                                page.screenshot(path=str(state_dir / f"nd_{safe_name}.png"), full_page=True)
                            except Exception:
                                pass
                        save_artifacts(page, artifacts_dir, st, org.organization_name)
                except Exception as e:
                    if not r.source_url:
                        r.source_url = ""
                    r.error = str(e)
                finally:
                    if context:
                        try:
                            context.close()
                        except Exception:
                            pass
                    if browser:
                        try:
                            browser.close()
                        except Exception:
                            pass
                print(f"[{st}] Result: {r.status} | {r.raw_status_text}", flush=True)
                results.append(r)
                fast_sleep(1.0)

    write_results(args.output_prefix, results)
    print(f"Wrote {len(results)} results to {args.output_prefix}.csv and .json")
    print(f"Summary table saved in: {args.output_prefix}_summary_table.csv")
    print(f"Artifacts saved in: {artifacts_dir.resolve()}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
