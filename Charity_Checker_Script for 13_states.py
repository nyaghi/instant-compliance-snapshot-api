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
import html
import http.cookiejar
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote, urljoin

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
AK_YEARS_TO_TRY = list(range(date.today().year, date.today().year - 8, -1))
FAST_WAIT_MAX_MS = max(750, min(int(os.environ.get("CE_FAST_WAIT_MAX_MS", "1500")), 2000))
FULL_PAGE_ARTIFACTS = os.environ.get("CE_FULL_PAGE_ARTIFACTS", "0").strip().lower() in {"1", "true", "yes"}
ARTIFACT_SCREENSHOT_TIMEOUT_MS = max(1000, int(os.environ.get("CE_ARTIFACT_SCREENSHOT_TIMEOUT_MS", "10000")))
STATE_RESULT_WAIT_SECONDS = max(3, int(os.environ.get("CE_STATE_RESULT_WAIT_SECONDS", "10")))
MD_FAST_SEARCH_ONLY = os.environ.get("CE_MD_FAST_SEARCH_ONLY", "1").strip().lower() not in {"0", "false", "no"}
MD_FAST_RESULT_WAIT_SECONDS = max(2, min(STATE_RESULT_WAIT_SECONDS, int(os.environ.get("CE_MD_FAST_RESULT_WAIT_SECONDS", "3"))))
MAX_FIXED_SLEEP_SECONDS = max(0.25, float(os.environ.get("CE_MAX_FIXED_SLEEP_SECONDS", "1.5")))
SC_GOTO_TIMEOUT_MS = max(5000, int(os.environ.get("CE_SC_GOTO_TIMEOUT_MS", "12000")))
SC_NETWORK_IDLE_TIMEOUT_MS = max(500, int(os.environ.get("CE_SC_NETWORK_IDLE_TIMEOUT_MS", "1500")))
SC_MAX_GOTO_ATTEMPTS = max(1, int(os.environ.get("CE_SC_MAX_GOTO_ATTEMPTS", "2")))
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
    matched_registry_name: str = ""
    matched_registry_identifier: str = ""
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
    readable = re.sub(r"\s+", " ", text or "")
    if not re.search(r"\b(?:EIN|FEIN|Federal\s+Tax|Tax\s+ID|Employer\s+Identification)\b", readable, re.I):
        return False
    return target not in digits_only(readable)

def reject_wrong_ein_result(result: StateResult, state_name: str) -> StateResult:
    result.raw_status_text = "No matching EIN result"
    result.status = STATUS_NOT_REGISTERED
    result.source_note = f"{state_name} search found a possible name match, but the public record did not match the requested EIN."
    result.success = True
    return result

def extract_registry_identifier_from_text(text: str, requested_ein: str = "") -> str:
    """Best-effort public registry identifier for audit/debug output."""
    readable = re.sub(r"\s+", " ", text or "").strip()
    target_ein = digits_only(requested_ein)
    patterns = [
        r"\b(?:Registration|Registry|License|Certificate|Charity|Public|AG\s+Account)\s*(?:#|No\.?|Number|ID)?\s*[:#]?\s*([A-Z]{0,4}\d{3,}[\w-]*)",
        r"\b(CO\d{2,}|CH\d{2,}|CT\d{2,}|P\d{2,})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, readable, re.I)
        if not match:
            continue
        value = re.sub(r"\s+", "", match.group(1)).strip()
        if value and digits_only(value) != target_ein:
            return value.upper()
    return ""

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

        raw = ""
        try:
            ein_digits = digits_only(org.ein)
            wanted_name = normalize_name(org.organization_name)
            best_row = ("", -999)
            rows = page.locator("tr")
            for i in range(min(rows.count(), 120)):
                row = rows.nth(i)
                try:
                    row_text = re.sub(r"\s+", " ", row.inner_text(timeout=1500)).strip()
                    if not row_text:
                        continue
                    row_digits = digits_only(row_text)
                    if ein_digits and ein_digits not in row_digits:
                        continue
                    row_name = normalize_name(row_text)
                    row_status = ""
                    for status_text in ca_statuses:
                        if status_text.lower() in row_text.lower():
                            row_status = status_text
                            break
                    if not row_status:
                        continue
                    score = 10
                    if re.search(r"\bcharity\s+registration\b", row_text, re.I):
                        score += 6
                    if wanted_name and wanted_name in row_name:
                        score += 4
                    score += active_row_priority(row_text) // 5
                    if re.search(r"\bcharity\s+registration\b", row_text, re.I) and re.search(r"\bcurrent\b", row_text, re.I):
                        score += 4
                    if re.search(r"\b(merged\s+out|withdrawn|dissolved|closed|retired|inactive|terminated|cancelled|canceled)\b", row_text, re.I):
                        score -= 15
                    if score > best_row[1]:
                        best_row = (row_status, score)
                except Exception:
                    continue
            if best_row[0]:
                raw = best_row[0]
        except Exception:
            pass

        try:
            tables = page.locator("table")
            for ti in range(tables.count()):
                if raw:
                    break
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
        registry_name = extract_labeled_value_from_text(body, ["Name"])
        if registry_name:
            result.matched_registry_name = registry_name
        if re.search(r"no records|no results|not found", body, re.I):
            result.raw_status_text = "No record found"
            result.status = STATUS_NOT_REGISTERED
            result.source_note = "Colorado search returned no matching record."
            result.success = True
            return result

        adverse_match = re.search(
            r"\b(revoked|suspended|may\s+not\s+solicit|may\s+not\s+raise\s+funds|may\s+not\s+operate|not\s+authorized\s+to\s+solicit)\b",
            body,
            re.I,
        )
        if adverse_match:
            result.raw_status_text = adverse_match.group(1).strip()
            result.status = "Suspended"
            result.source_note = "Colorado public search shows an adverse solicitation status."
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
        safe_wait_for_network_idle(page, timeout=10000)
        fast_sleep(2)

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

        search_input.click()
        search_input.fill("")
        try:
            search_input.type(query, delay=35)
        except Exception:
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

        safe_wait_for_network_idle(page, timeout=10000)
        fast_sleep(1)

        body = page.locator("body").inner_text(timeout=15000)
        if re.search(r"no results|no records|0 records|no matching|no charity found", body, re.I):
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
        safe_wait_for_network_idle(page, timeout=10000)
        for attempt in range(10):
            fast_sleep(0.75)
            try:
                loading_text = page.locator("body").inner_text(timeout=5000)
            except Exception:
                continue
            if re.search(r"Form[\s-]*PC", loading_text, re.I):
                break
            if attempt >= 5 and re.search(
                r"Annual\s+Filings(?:\s+and\s+Documents)?[\s\S]{0,1200}(?:No documents found|No rows available)",
                loading_text,
                re.I,
            ):
                break

        try:
            page.locator("body").evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except Exception:
            pass
        fast_sleep(1)

        body = page.locator("body").inner_text(timeout=15000)
        m_section = re.search(
            r"Annual Filings(?: and Documents)?(.*?)(?:Charity Registration Documents|Registration Documents|Other Filed Documents|Financial Statements|Additional Documents|$)",
            body,
            re.I | re.S,
        )
        section_text = m_section.group(1) if m_section else ""

        filing_years = []
        for m in re.finditer(r"Form[\s-]*PC[\s\S]{0,140}(20\d{2})", section_text, re.I):
            filing_years.append(int(m.group(1)))
        for m in re.finditer(r"(20\d{2})[\s\S]{0,140}Form[\s-]*PC", section_text, re.I):
            filing_years.append(int(m.group(1)))
        filing_years = sorted(set(filing_years))

        if not filing_years:
            result.raw_status_text = "Annual Filings not visible"
            result.status = STATUS_DELINQUENT
            result.source_note = "Massachusetts public portal showed the organization record, but did not expose a visible Form PC filing year after Get Filings."
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
        name_input.fill(search_name_query_variants(org.organization_name, max_words=5)[0])
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
        if re.search(r"no rows available|no records|no results found|no results|not found|error fetching data", body, re.I) and org.organization_name.strip():
            try:
                name_input.fill("")
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
            except Exception:
                pass
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
        best_status_priority = -999
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
                    status_priority = active_row_priority(row_text)
                    if priority > best_priority or (priority == best_priority and status_priority > best_status_priority):
                        best_priority = priority
                        best_status_priority = status_priority
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
        if re.search(
            r"(?:Registration\s+(?:Status|Type)|Filing\s+Type|Exemption\s+Status|Category)\s*:?\s*Exempt\b|"
            r"\bExempt\s+from\s+(?:charitable\s+)?(?:registration|filing)",
            detail_text,
            re.I,
        ) and not re.search(r"\bnot\s+exempt\b|\bnon[- ]exempt\b", detail_text, re.I):
            result.raw_status_text = "Exempt"
            result.status = "Exempt"
            result.source_note = "New York public registry detail page indicates exempt status for the matched organization."
            result.success = True
            return result
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
            result.status = "Delinquent"
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
            for status_text in ["Exempt", "Compliant", "Active", "Delinquent", "Expired", "Revoked", "Suspended", "Withdrawn"]:
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
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                safe_wait_for_network_idle(page, timeout=5000)
                fast_sleep(0.75)
                last_goto_error = None
                break
            except Exception as e:
                last_goto_error = e
                if goto_attempt == 0:
                    fast_sleep(2)
                    continue
        if last_goto_error:
            raise last_goto_error

        ein_input = None
        for _ in range(3):
            ein_input = find_pa_ein_input(page)
            if ein_input:
                break
            safe_wait_for_network_idle(page, timeout=5000)
            fast_sleep(1)
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
def strip_registry_display_labels(value: str) -> str:
    """Remove registry-only labels before comparing organization names."""
    txt = re.sub(r"^\s*\d+\.\s*", " ", value or "")
    txt = re.sub(r"\s*\(\s*(?:primary\s+name|registration\s+pending)\s*\)\s*", " ", txt, flags=re.I)
    return re.sub(r"\s+", " ", txt).strip()

def normalize_name(value: str) -> str:
    txt = strip_registry_display_labels(value).lower()
    txt = re.sub(r"\b([a-z]+)'s\b", r"\1s", txt)
    txt = re.sub(r"\bu\s*\.?\s*s\.?\b", "us", txt)
    txt = re.sub(r"\bst\.?\b", "saint", txt)
    txt = re.sub(r"\bassoc\.?\b", "association", txt)
    txt = re.sub(r"\bassn\.?\b", "association", txt)
    txt = re.sub(r"\b(the|and|a)\b", " ", txt)
    # Keep substantive words like "foundation" and "fund" in the match key.
    # Dropping them made name-only state searches confuse related but separate entities.
    txt = re.sub(r"\bnon[\s-]*profit\b", " ", txt)
    txt = re.sub(r"\b(inc|incorporated|corp|corporation|llc|ltd)\b", " ", txt)
    txt = re.sub(r"[^a-z0-9]+", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()

def name_match_priority(candidate_name: str, target_name: str) -> int:
    """Score a registry result name without letting weak substring matches win."""
    candidate = normalize_name(candidate_name)
    target = normalize_name(target_name)
    if not candidate or not target:
        return -1
    if candidate == target:
        return 5
    candidate_words = candidate.split()
    target_words = target.split()
    if len(target) <= 3 and len(target_words) == 1:
        # Very short organization names/acronyms must match as their own word.
        # Substring matches made iDE accept IDEALWARE, 864Pride, and
        # AlumniFidelity in name-only registries.
        return -1
    try:
        target_greater_index = target_words.index("greater")
    except ValueError:
        target_greater_index = -1
    try:
        candidate_greater_index = candidate_words.index("greater")
    except ValueError:
        candidate_greater_index = -1
    if (
        target_greater_index >= 1
        and candidate_greater_index >= 1
        and target_words[:target_greater_index + 1] == candidate_words[:candidate_greater_index + 1]
    ):
        target_place = target_words[target_greater_index + 1:]
        candidate_place = candidate_words[candidate_greater_index + 1:]
        if target_place and candidate_place and target_place[0] != candidate_place[0]:
            return -1
    if target_greater_index >= 1 and candidate_greater_index < 0:
        target_prefix = target_words[:target_greater_index]
        if (
            target_prefix
            and candidate_words[:len(target_prefix)] == target_prefix
            and len(candidate_words) > len(target_prefix)
            and candidate_words[len(target_prefix)] != "greater"
        ):
            return -1
    def local_place_tail_mismatch(connector: str = "of") -> bool:
        try:
            target_connector_index = target_words.index(connector)
            candidate_connector_index = candidate_words.index(connector)
        except ValueError:
            return False
        target_prefix = target_words[:target_connector_index]
        candidate_prefix = candidate_words[:candidate_connector_index]
        target_tail = target_words[target_connector_index + 1:]
        candidate_tail = candidate_words[candidate_connector_index + 1:]
        if not target_prefix or target_prefix != candidate_prefix or not target_tail or not candidate_tail:
            return False
        prefix_text = " ".join(target_prefix)
        local_prefixes = {
            "community foundation",
            "united way",
            "ymca",
            "boys girls club",
            "habitat humanity",
            "jewish federation",
        }
        place_indicators = {
            "county", "city", "town", "township", "borough", "parish", "valley",
            "region", "regional", "area", "greater", "north", "south", "east",
            "west", "central", "northern", "southern", "eastern", "western",
            "sarasota", "lorain", "grant", "kansas", "charleston", "richmond",
            "tennessee", "indiana", "seattle", "new", "york",
        }
        prefix_is_local = prefix_text in local_prefixes
        tail_looks_place = bool((set(target_tail) | set(candidate_tail)) & place_indicators)
        return (prefix_is_local or tail_looks_place) and target_tail[0] != candidate_tail[0]
    if local_place_tail_mismatch("of"):
        return -1
    if (
        len(target_words) >= 4
        and len(candidate_words) >= 4
        and target_words[0] in {"center", "centre", "institute", "foundation", "association", "society"}
        and target_words[1] in {"for", "of"}
        and candidate_words[:3] == target_words[:3]
        and candidate_words[3] != target_words[3]
    ):
        return -1
    if candidate.startswith(target) or target.startswith(candidate):
        shorter_words = candidate_words if len(candidate_words) <= len(target_words) else target_words
        if len(shorter_words) >= 4:
            return 4
        # Short prefixes such as "Global Fund" or "Trustees Of" are useful
        # search queries, but not enough by themselves to accept a registry row.
        # Let the more specific entity-word rule below handle safe abbreviations.
    else:
        shorter_words = []
    if shorter_words and len(shorter_words) >= 4:
        return 4
    def remove_terminal_entity_word(value: str) -> str:
        words = value.split()
        if len(words) >= 4 and words[-1] in {"foundation", "fund"}:
            return " ".join(words[:-1])
        return value
    candidate_without_entity = remove_terminal_entity_word(candidate)
    target_without_entity = remove_terminal_entity_word(target)
    if candidate_without_entity and target_without_entity and candidate_without_entity == target_without_entity:
        return 4
    connector_words = {"of", "for", "to", "in", "on", "at", "by"}
    if len(target_words) >= 3 and candidate_words[:3] == target_words[:3]:
        # Do not accept a row solely because it shares a weak prefix ending in
        # a connector ("Allen Institute for ..." matched "Allen Institute for
        # Brain Science"). Require the prefix itself to end on a substantive
        # word, or require another distinctive word beyond the prefix.
        if target_words[2] not in connector_words:
            return 3
        candidate_later = set(candidate_words[3:])
        target_later = set(target_words[3:])
        if candidate_later & target_later:
            return 3
    entity_words = {"foundation", "fund", "association", "society", "institute", "center", "centre", "network", "mission"}
    if (
        len(target_words) >= 3
        and len(candidate_words) >= 3
        and candidate_words[:2] == target_words[:2]
        and target_words[1] not in connector_words
        and candidate_words[-1] == target_words[-1]
        and target_words[-1] in entity_words
    ):
        return 3
    if len(target_words) <= 2 and len(candidate_words) > len(target_words) and target in candidate:
        # Short names are especially prone to false positives in name-only
        # portals. "Allen Institute" is not the same entity as "Allen Institute
        # for Artificial Intelligence"; status should not rescue that mismatch.
        return -1
    if target in candidate:
        return 2
    shared = set(candidate_words) & set(target_words)
    if target_words and target_words[0] in shared and len(shared) >= min(3, len(target_words)):
        return 1
    return -1

def active_row_priority(text: str) -> int:
    """Prefer non-terminal records when duplicate search results match similarly."""
    value = text or ""
    primary_bonus = 15 if re.search(r"\(\s*primary\s+name\s*\)", value, re.I) else 0
    if re.search(r"\bnot\s+registered\b", value, re.I):
        return 5
    if re.search(r"\b(retired|inactive|closed|withdrawn|terminated|cancelled|canceled|dissolved|merged\s+out)\b", value, re.I):
        return 10 + primary_bonus
    if re.search(r"\b(registration\s+pending|pending)\b", value, re.I):
        return 80 + primary_bonus
    if re.search(r"\b(non\W*compliant|delinquent|expired|failed\s+to\s+renew|suspended|revoked|not\s+authorized|may\s+not\s+solicit|may\s+not\s+raise\s+funds|may\s+not\s+operate|cease\s+and\s+desist)\b", value, re.I):
        return 60 + primary_bonus
    if re.search(r"\b(active|current|compliant|good\s+standing|registered)\b", value, re.I):
        return 70 + primary_bonus
    return 40 + primary_bonus

def non_terminal_row_bonus(text: str) -> int:
    """Let credible active-ish duplicate rows beat inactive/closed duplicate rows."""
    value = text or ""
    if re.search(r"\bnot\s+registered\b", value, re.I):
        return 0
    if re.search(r"\b(retired|inactive|closed|withdrawn|terminated|cancelled|canceled|dissolved|merged\s+out)\b", value, re.I):
        return 0
    return 10

def candidate_selection_score(candidate_name: str, target_name: str, row_text: str) -> tuple[int, int]:
    """Choose the best matching entity while preferring non-terminal duplicate rows."""
    name_priority = name_match_priority(candidate_name, target_name)
    # Name-only state portals can return loosely related charities. A shared
    # first word plus a few generic terms is not enough to treat the record as
    # the requested organization.
    if name_priority < 2:
        return (-1, -999)
    # Identity strength must beat status. For example, "Allen Institute" should
    # not lose to "The Allen Institute for Artificial Intelligence" merely
    # because the latter is active and the exact entity is inactive. The
    # non-terminal bonus only breaks ties among similarly strong name matches.
    name_priority = (name_priority * 100) + non_terminal_row_bonus(row_text)
    status_priority = active_row_priority(row_text)
    return (name_priority, status_priority)

def match_target_names(org_or_name) -> list[str]:
    if isinstance(org_or_name, str):
        values = [org_or_name]
    elif isinstance(org_or_name, (list, tuple, set)):
        values = list(org_or_name)
    else:
        values = getattr(org_or_name, "match_target_names", None) or [getattr(org_or_name, "organization_name", "")]
    output = []
    seen = set()
    for value in values:
        value = re.sub(r"\s+", " ", str(value or "").strip())
        key = normalize_name(value)
        if value and key and key not in seen:
            seen.add(key)
            output.append(value)
    return output or [str(org_or_name or "")]

def candidate_selection_score_for_targets(candidate_name: str, target_names, row_text: str) -> tuple[int, int]:
    best = (-1, -999)
    for target_name in match_target_names(target_names):
        score = candidate_selection_score(candidate_name, target_name, row_text)
        if score > best:
            best = score
    return best

def name_match_priority_for_targets(candidate_name: str, target_names) -> int:
    best = -1
    for target_name in match_target_names(target_names):
        best = max(best, name_match_priority(candidate_name, target_name))
    return best

def search_name_query_variants(name: str, max_words: int = 4) -> list[str]:
    raw_cleaned = re.sub(r"\s+", " ", name or "").strip()
    comma_lead_segment = ""
    comma_trailing_segment = ""
    if "," in raw_cleaned:
        comma_parts = [part.strip() for part in re.split(r"\s*,\s*", raw_cleaned, maxsplit=1)]
        if len(comma_parts) == 2:
            comma_lead_segment = re.sub(r"\s+", " ", re.sub(r"[^\w\s']", " ", comma_parts[0])).strip()
            comma_trailing_segment = re.sub(r"\s+", " ", re.sub(r"[^\w\s']", " ", comma_parts[1])).strip()
            if len(comma_lead_segment.split()) < 2:
                comma_lead_segment = ""
            if len(comma_trailing_segment.split()) < 2:
                comma_trailing_segment = ""
    cleaned = raw_cleaned
    cleaned = re.sub(r"\s*,\s*", " ", cleaned)
    normalized_cleaned = normalize_name(cleaned)
    if len(normalized_cleaned) <= 3 and len(normalized_cleaned.split()) == 1:
        return [cleaned]
    lead_segment = ""
    trailing_segment = ""
    if re.search(r"/|\\", cleaned):
        lead_segment = re.split(r"\s*(?:/|\\)\s*", cleaned, maxsplit=1)[0].strip()
        trailing_segment = re.split(r"\s*(?:/|\\)\s*", cleaned, maxsplit=1)[1].strip()
        lead_segment = re.sub(r"\s+", " ", re.sub(r"[^\w\s']", " ", lead_segment)).strip()
        trailing_segment = re.sub(r"\s+", " ", re.sub(r"[^\w\s']", " ", trailing_segment)).strip()
        if len(lead_segment.split()) < 2:
            lead_segment = ""
        if len(trailing_segment.split()) < 2:
            trailing_segment = ""
    without_leading_article = re.sub(r"^(?:the|a|an)\s+", "", cleaned, flags=re.I).strip()
    comma_lead_without_article = re.sub(r"^(?:the|a|an)\s+", "", comma_lead_segment, flags=re.I).strip()
    ampersand_variant = ""
    if re.search(r"\band\b", without_leading_article or cleaned, re.I):
        ampersand_variant = re.sub(r"\band\b", "&", without_leading_article or cleaned, flags=re.I)
        ampersand_variant = re.sub(r"\s+", " ", ampersand_variant).strip()
    without_trailing_the = ""
    trailing_the_query = ""
    us_prefixed_variants = []
    if re.match(r"^us\s+", cleaned, re.I):
        us_prefixed_variants.append(re.sub(r"^us\s+", "U.S. ", cleaned, flags=re.I))
        us_prefixed_variants.append(re.sub(r"^us\s+", "United States ", cleaned, flags=re.I))
    elif re.match(r"^u\.?\s*s\.?\s+", cleaned, re.I):
        us_prefixed_variants.append(re.sub(r"^u\.?\s*s\.?\s+", "US ", cleaned, flags=re.I))
        us_prefixed_variants.append(re.sub(r"^u\.?\s*s\.?\s+", "United States ", cleaned, flags=re.I))
    if re.search(r"(?:,\s*the|\s+the)\s*$", name or "", re.I) and not re.match(r"^the\s+", cleaned, re.I):
        without_trailing_the = re.sub(r"\s+\bthe\b\.?\s*$", "", cleaned, flags=re.I).strip()
        trailing_the_words = re.sub(r"[^\w\s']", " ", without_trailing_the).strip()
        trailing_the_words = re.sub(r"\s+", " ", trailing_the_words)
        trailing_the_query = " ".join(trailing_the_words.split()[:max_words]) if trailing_the_words else ""
    without_leading_acronym = re.sub(r"^[A-Z]{2,8}\s*[-/\\]\s*", "", cleaned).strip()
    if without_leading_acronym == cleaned:
        without_leading_acronym = ""
    hyphen_as_space = re.sub(r"[-\u2010-\u2015]+", " ", cleaned).strip()
    hyphen_as_space = re.sub(r"\s+", " ", hyphen_as_space)
    if hyphen_as_space == cleaned:
        hyphen_as_space = ""
    slash_as_space = re.sub(r"\s*(?:/|\\)\s*", " ", cleaned).strip()
    slash_as_space = re.sub(r"\s+", " ", slash_as_space)
    if slash_as_space == cleaned:
        slash_as_space = ""
    possessive_removed = re.sub(r"\b([A-Za-z]+)'s\b", r"\1s", cleaned, flags=re.I).strip()
    if possessive_removed == cleaned:
        possessive_removed = ""
    possessive_root_prefix = ""
    possessive_root_match = re.match(r"^(.+?\b[A-Za-z]+)'s\b", cleaned, re.I)
    if possessive_root_match:
        possessive_root_words = re.sub(r"[^\w\s]", " ", possessive_root_match.group(1)).split()
        if len(possessive_root_words) >= 2:
            possessive_root_prefix = " ".join(possessive_root_words[:3])
    hyphen_tail_prefix = ""
    if "-" in cleaned:
        tail = re.split(r"\s*-\s*", cleaned, maxsplit=1)[1].strip()
        tail_words = re.sub(r"[^\w\s']", " ", tail).split()
        if len(tail_words) >= 2:
            hyphen_tail_prefix = " ".join(tail_words[:3])
    saint_expanded = re.sub(r"\bSt\.?\s+", "Saint ", cleaned, flags=re.I).strip()
    if saint_expanded == cleaned:
        saint_expanded = ""
    saint_abbreviated = re.sub(r"\bSaint\s+", "St. ", cleaned, flags=re.I).strip()
    if saint_abbreviated == cleaned:
        saint_abbreviated = ""
    no_suffix = re.sub(
        r"\s+\b(the|inc\.?|incorporated|corp\.?|corporation|llc|ltd\.?|limited)\b\.?\s*$",
        "",
        cleaned,
        flags=re.I,
    ).strip()
    no_punct_full = re.sub(r"[^\w\s']", " ", cleaned).strip()
    no_punct_full = re.sub(r"\s+", " ", no_punct_full)
    us_word_variants = []
    for us_source in [cleaned, without_leading_article]:
        if re.search(r"\bu\.?\s*s\.?(?=\W|$)", us_source or "", re.I):
            compact = re.sub(r"\bu\.?\s*s\.?(?=\W|$)", "US", us_source, flags=re.I).strip()
            expanded = re.sub(r"\bu\.?\s*s\.?(?=\W|$)", "United States", us_source, flags=re.I).strip()
            us_word_variants.extend([
                compact,
                expanded,
                re.sub(r"^(?:the|a|an)\s+", "", compact, flags=re.I).strip(),
                re.sub(r"^(?:the|a|an)\s+", "", expanded, flags=re.I).strip(),
            ])
    no_punct = re.sub(r"[^\w\s']", " ", no_suffix or cleaned).strip()
    no_punct = re.sub(r"\s+", " ", no_punct)
    display_source = re.sub(r"[^\w\s]", " ", cleaned).strip()
    display_source = re.sub(r"\s+", " ", display_source)
    display_words = [word for word in display_source.split() if word.lower() != "s"]
    display_short_prefix = " ".join(display_words[:2]) if len(display_words) >= 2 else ""
    words = no_punct.split()
    prefix = " ".join(words[:max_words]) if words else no_punct
    hyphenated_word_pairs = []
    if "-" not in cleaned and 2 <= len(words) <= 8:
        for idx in range(len(words) - 1):
            pair_variant = words[:]
            pair_variant[idx] = f"{pair_variant[idx]}-{pair_variant[idx + 1]}"
            del pair_variant[idx + 1]
            hyphenated_word_pairs.append(" ".join(pair_variant))
    normalized_words = normalize_name(cleaned).split()
    short_distinctive_prefix = " ".join(normalized_words[:2]) if len(normalized_words) >= 2 else ""
    ms_expanded = ""
    if re.search(r"\bMS\s+Society\b", cleaned, re.I):
        ms_expanded = re.sub(r"\bMS\s+Society\b", "Multiple Sclerosis Society", cleaned, flags=re.I)
    childrens_hospital_foundation = ""
    childrens_hospital_foundation_possessive = ""
    childrens_match = re.match(r"^(.+?\bchildren'?s?)\s+foundation\b", cleaned, re.I)
    if childrens_match:
        childrens_prefix_original = childrens_match.group(1).strip()
        childrens_prefix = re.sub(r"\b([A-Za-z]+)'s\b", r"\1s", childrens_prefix_original, flags=re.I)
        childrens_hospital_foundation = f"{childrens_prefix} Hospital Foundation"
        childrens_hospital_foundation_possessive = f"{childrens_prefix_original} Hospital Foundation"
    with_leading_the = "" if re.match(r"^the\s+", cleaned, re.I) else f"The {cleaned}"
    suffix_base = no_suffix or cleaned
    legal_suffix_variants = []
    if suffix_base and not re.search(r"\b(inc\.?|incorporated|corp\.?|corporation|llc|ltd\.?|limited)\s*$", suffix_base, re.I):
        legal_suffix_variants = [
            f"{suffix_base} Inc",
            f"{suffix_base} Inc.",
            f"{suffix_base}, Inc",
            f"{suffix_base}, Inc.",
        ]
    variants = [
        possessive_removed,
        cleaned,
        without_leading_article if without_leading_article.lower() != cleaned.lower() else "",
        comma_lead_without_article if comma_lead_without_article.lower() != comma_lead_segment.lower() else "",
        comma_lead_segment,
        comma_trailing_segment,
        trailing_segment,
        lead_segment,
        *us_prefixed_variants,
        *us_word_variants,
        ampersand_variant,
        childrens_hospital_foundation,
        childrens_hospital_foundation_possessive,
        saint_expanded,
        saint_abbreviated,
        no_suffix,
        hyphen_as_space,
        no_punct_full,
        no_punct,
        slash_as_space,
        *legal_suffix_variants,
        *hyphenated_word_pairs,
        ms_expanded,
        with_leading_the,
        without_leading_acronym,
        possessive_root_prefix,
        hyphen_tail_prefix,
        prefix,
        trailing_the_query,
        without_trailing_the,
        display_short_prefix,
        short_distinctive_prefix,
    ]
    output = []
    seen = set()
    for variant in variants:
        key = variant.lower()
        if variant and key not in seen:
            seen.add(key)
            output.append(variant)
    return output or [cleaned]

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

def click_va_organization_link(page, org_name: str, target_names=None):
    links = page.locator('a[href*="act=2"][href*="sysorgno"]')
    candidates = []
    try:
        count = min(links.count(), 100)
        for i in range(count):
            link = links.nth(i)
            try:
                txt = re.sub(r"\s+", " ", link.inner_text(timeout=1000)).strip()
                priority = name_match_priority_for_targets(txt, target_names or org_name)
                if priority >= 0:
                    row_text = txt
                    try:
                        row_text = re.sub(r"\s+", " ", link.locator("xpath=ancestor::tr[1]").inner_text(timeout=1000)).strip()
                    except Exception:
                        pass
                    score = candidate_selection_score_for_targets(txt, target_names or org_name, row_text)
                    if score[0] >= 0:
                        href = ""
                        try:
                            href = link.get_attribute("href") or ""
                        except Exception:
                            href = ""
                        id_match = re.search(r"sysorgno=([^&]+)", href, re.I)
                        identifier = urllib.parse.unquote(id_match.group(1)).strip() if id_match else ""
                        candidates.append((score[0], score[1], link, txt, identifier, row_text))
            except Exception:
                continue
    except Exception:
        pass
    if candidates:
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        selected = candidates[0]
        selected[2].click(timeout=5000)
        return {
            "name": selected[3],
            "identifier": selected[4],
            "row_text": selected[5],
        }
    return None

def va_search_results_show_pending(page, org_name: str, target_names=None) -> bool:
    links = page.locator('a[href*="act=2"][href*="sysorgno"]')
    candidates = []
    try:
        count = min(links.count(), 100)
        for i in range(count):
            link = links.nth(i)
            try:
                txt = re.sub(r"\s+", " ", link.inner_text(timeout=1000)).strip()
                row_text = txt
                try:
                    row_text = re.sub(r"\s+", " ", link.locator("xpath=ancestor::tr[1]").inner_text(timeout=1000)).strip()
                except Exception:
                    pass
                score = candidate_selection_score_for_targets(txt, target_names or org_name, row_text)
                if score[0] >= 0:
                    candidates.append((score[0], score[1], bool(re.search(r"\bregistration\s+pending\b", row_text, re.I))))
            except Exception:
                continue
    except Exception:
        pass
    if not candidates:
        return False
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2]

def search_va(page, org: Organization) -> StateResult:
    url = "https://cos.vdacs.virginia.gov/cgi-bin/char_search.cgi"
    result = StateResult(org.organization_name, org.ein, "VA", STATUS_UNKNOWN, url)
    try:
        target_names = match_target_names(org)
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        fast_sleep(0.75)

        selected_search_row_pending = False
        clicked_match = False
        for query_index, query in enumerate(search_name_query_variants(org.organization_name, max_words=5)[:6]):
            if query_index:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                fast_sleep(0.5)

            name_input = find_va_name_input(page)
            if not name_input:
                result.error = "Could not find VA organization name input"
                return result
            name_input.fill("")
            name_input.fill(query)

            if not click_va_search_button(page):
                result.error = "Could not click VA Search button"
                return result

            page.wait_for_load_state("domcontentloaded", timeout=15000)
            fast_sleep(0.75)

            body = page.locator("body").inner_text(timeout=8000)
            if re.search(r"\bNo record found\b", body, re.I):
                continue

            selected_search_row_pending = va_search_results_show_pending(page, org.organization_name, target_names)

            selected_va_match = click_va_organization_link(page, org.organization_name, target_names)
            if selected_va_match:
                result.matched_registry_name = selected_va_match.get("name", "")
                result.matched_registry_identifier = selected_va_match.get("identifier", "")
                clicked_match = True
                break

        if not clicked_match:
            result.raw_status_text = "No record found"
            result.status = STATUS_NOT_REGISTERED
            result.source_note = "Virginia search returned no matching organization link."
            result.success = True
            return result

        page.wait_for_load_state("domcontentloaded", timeout=15000)
        fast_sleep(0.75)

        detail_text_for_status = page.locator("body").inner_text(timeout=8000)
        if not result.matched_registry_name:
            result.matched_registry_name = extract_labeled_value_from_text(detail_text_for_status, ["Primary Name", "Name"])
        if not result.matched_registry_identifier:
            result.matched_registry_identifier = extract_registry_identifier_from_text(detail_text_for_status, org.ein)
        if selected_search_row_pending or re.search(r"\bregistration\s+pending\b", detail_text_for_status, re.I):
            result.raw_status_text = "Registration Pending"
            result.status = "Pending"
            result.source_note = "Virginia public registry shows Registration Pending for the matched organization, which CharityClarity treats as a trumping state-provided status."
            result.success = True
            return result
        if re.search(r"not\s+authorized\s+to\s+solicit|may\s+not\s+(?:solicit|raise\s+funds|operate)|revoked|suspended", detail_text_for_status or "", re.I):
            result.raw_status_text = (
                extract_labeled_value(page, ["Registration Filing Status"])
                or extract_labeled_value_from_text(detail_text_for_status, ["Registration Filing Status"])
                or "Not authorized to solicit"
            )
            result.status = "Suspended"
            result.source_note = "Virginia public registry shows a restricted solicitation status, which takes priority over date-based filing interpretation."
            result.success = True
            return result

        registration_status = extract_labeled_value(page, ["Registration Filing Status"])
        if re.search(r"not\s+authorized\s+to\s+solicit|may\s+not\s+(?:solicit|raise\s+funds|operate)|revoked|suspended", registration_status or "", re.I):
            result.raw_status_text = registration_status
            result.status = "Suspended"
            result.source_note = "Virginia public registry shows a restricted solicitation status, which takes priority over date-based filing interpretation."
            result.success = True
            return result

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
                    status_match = re.search(
                        r"Registration\s+Status[^A-Za-z0-9]{0,80}"
                        r"(Current|Delinquent|Expired|Active|Inactive|Closed|Revoked|Suspended|Withdrawn|Retired|Terminated|Cancelled|Canceled)",
                        body,
                        re.I,
                    )
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
        target_names = match_target_names(org)
        last_goto_error = None
        for goto_attempt in range(SC_MAX_GOTO_ATTEMPTS):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=SC_GOTO_TIMEOUT_MS)
                safe_wait_for_network_idle(page, timeout=SC_NETWORK_IDLE_TIMEOUT_MS)
                fast_sleep(0.5)
                last_goto_error = None
                break
            except Exception as e:
                last_goto_error = e
                if goto_attempt + 1 < SC_MAX_GOTO_ATTEMPTS:
                    fast_sleep(1)
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

        clicked_result = False
        links = page.locator("a[href*='CharityInfo']")
        candidates = []
        try:
            count = min(links.count(), 100)
            for i in range(count):
                link = links.nth(i)
                try:
                    txt = re.sub(r"\s+", " ", link.inner_text(timeout=1000)).strip()
                    priority = name_match_priority_for_targets(txt, target_names)
                    if priority >= 0:
                        row_text = txt
                        try:
                            row_text = re.sub(r"\s+", " ", link.locator("xpath=ancestor::tr[1]").inner_text(timeout=1000)).strip()
                        except Exception:
                            pass
                        score = candidate_selection_score_for_targets(txt, target_names, row_text)
                        if score[0] >= 0:
                            href = ""
                            try:
                                href = link.get_attribute("href") or ""
                            except Exception:
                                href = ""
                            identifier = extract_registry_identifier_from_text(f"{href} {row_text}", org.ein)
                            candidates.append((score[0], score[1], link, txt, identifier, row_text))
                except Exception:
                    continue
        except Exception:
            pass
        if not clicked_result and candidates:
            candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
            selected_sc_match = candidates[0]
            result.matched_registry_name = selected_sc_match[3]
            result.matched_registry_identifier = selected_sc_match[4]
            candidates[0][2].click(timeout=5000)
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
        if not result.matched_registry_name:
            result.matched_registry_name = extract_labeled_value_from_text(detail_text, ["Organization", "Charity Name", "Name"])
        if not result.matched_registry_identifier:
            result.matched_registry_identifier = extract_registry_identifier_from_text(detail_text, org.ein)
        status_text = extract_labeled_value(page, ["Status", "Registration Status"]) or extract_labeled_value_from_text(detail_text, ["Status", "Registration Status"])
        if re.search(r"\b(suspended|revoked|not\s+authorized|may\s+not\s+solicit|may\s+not\s+raise\s+funds|may\s+not\s+operate)\b", status_text or "", re.I):
            result.raw_status_text = status_text
            result.status = "Suspended"
            result.source_note = "South Carolina public registry shows a restricted solicitation status, which takes priority over date-based filing interpretation."
            result.success = True
            return result
        if re.search(r"\bexpired\b", status_text or "", re.I):
            result.raw_status_text = status_text
            result.status = STATUS_DELINQUENT
            result.source_note = "South Carolina public registry shows an expired registration status, which CharityClarity treats as Delinquent."
            result.success = True
            return result
        if re.search(r"\b(terminated|withdrawn|cancelled|canceled|closed)\b", status_text or "", re.I):
            result.raw_status_text = status_text
            result.status = "Closed / Withdrawn / Canceled"
            result.source_note = "South Carolina public registry shows a terminal registration status."
            result.success = True
            return result

        m = re.search(r"Due Date:\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})", detail_text, re.I)
        due_raw = m.group(1).strip() if m else extract_labeled_value_from_text(detail_text, ["Due Date"])
        due_date = parse_date_value(due_raw)
        if due_date:
            result.raw_status_text = due_raw
            result.status = status_from_due_date(due_date)
            result.source_note = "South Carolina uses the Due Date shown in the Next Report section."
            result.success = True
            return result

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
        target_names = match_target_names(org)
        def me_query_variants(name: str) -> list[str]:
            cleaned = re.sub(r"\s+", " ", name or "").strip()
            cleaned = re.sub(r"\s*,?\s+", " ", cleaned)
            us_prefixed_variants = []
            if re.match(r"^us\s+", cleaned, re.I):
                us_prefixed_variants.append(re.sub(r"^us\s+", "U.S. ", cleaned, flags=re.I))
                us_prefixed_variants.append(re.sub(r"^us\s+", "United States ", cleaned, flags=re.I))
            elif re.match(r"^u\.?\s*s\.?\s+", cleaned, re.I):
                us_prefixed_variants.append(re.sub(r"^u\.?\s*s\.?\s+", "US ", cleaned, flags=re.I))
                us_prefixed_variants.append(re.sub(r"^u\.?\s*s\.?\s+", "United States ", cleaned, flags=re.I))
            cleaned_no_punctuation = re.sub(r"[^\w\s]", " ", cleaned).strip()
            cleaned_no_punctuation = re.sub(r"\s+", " ", cleaned_no_punctuation)
            legal_suffix_clean = cleaned_no_punctuation
            for _ in range(4):
                next_value = re.sub(
                    r"\s+\b(the|incorporated|inc|corp|corporation|llc|ltd|limited)\b\.?\s*$",
                    "",
                    legal_suffix_clean,
                    flags=re.I,
                ).strip()
                if next_value == legal_suffix_clean:
                    break
                legal_suffix_clean = next_value
            without_suffix = re.sub(
                r",?\s+(incorporated|inc|the|corp|corporation|ltd|limited)\.?\s*$",
                "",
                cleaned,
                flags=re.I,
            ).strip()
            institute_plural = re.sub(r"\bInstitute\s+of\b", "Institutes of", cleaned, flags=re.I).strip()
            institute_singular = re.sub(r"\bInstitutes\s+of\b", "Institute of", cleaned, flags=re.I).strip()
            variants = [*search_name_query_variants(cleaned, max_words=5), *us_prefixed_variants, legal_suffix_clean, without_suffix, cleaned_no_punctuation, cleaned, institute_plural, institute_singular]
            seen = set()
            output = []
            for variant in variants:
                key = variant.lower()
                if variant and key not in seen:
                    seen.add(key)
                    output.append(variant)
            return (output or [cleaned])[:5]

        def run_me_direct_search(query: str) -> tuple[str, list[dict[str, str]], urllib.request.OpenerDirector]:
            cookie_jar = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
            opener.addheaders = [("User-Agent", "Mozilla/5.0 CharityClarity/1.0")]
            response = opener.open(url, timeout=20)
            html_text = response.read().decode("utf-8", "replace")
            fields: dict[str, str] = {}
            for hidden in re.finditer(r'<input[^>]+type="hidden"[^>]*>', html_text, re.I):
                tag = hidden.group(0)
                name_match = re.search(r'name="([^"]+)"', tag, re.I)
                value_match = re.search(r'value="([^"]*)"', tag, re.I)
                if name_match:
                    fields[html.unescape(name_match.group(1))] = html.unescape(value_match.group(1) if value_match else "")
            fields.update({
                "ctl00$ctl00$mainContent$mainContent$scRegulator": "4076",
                "ctl00$ctl00$mainContent$mainContent$scCompanyName": (query or ""),
                "ctl00$ctl00$mainContent$mainContent$ctl24": "BW",
                "ctl00$ctl00$mainContent$mainContent$btnSearch": "Search",
            })
            encoded = urllib.parse.urlencode(fields).encode("utf-8")
            request = urllib.request.Request(
                "https://www.pfr.maine.gov/almsonline/almsquery/SearchCompany.aspx?AspxAutoDetectCookieSupport=1",
                data=encoded,
                method="POST",
            )
            request.add_header("Content-Type", "application/x-www-form-urlencoded")
            posted = opener.open(request, timeout=25)
            result_html = posted.read().decode("utf-8", "replace")
            rows: list[dict[str, str]] = []
            for match in re.finditer(
                r'<tr[^>]*>\s*<td[^>]*>\s*<a\s+href="(?P<href>ShowDetail\.aspx[^"]+)"[^>]*>(?P<name>.*?)</a>\s*</td>\s*'
                r'<td[^>]*>(?P<number>.*?)</td>\s*<td[^>]*>(?P<location>.*?)</td>\s*'
                r'<td[^>]*>(?P<profession>.*?)</td>\s*<td[^>]*>(?P<status>.*?)</td>',
                result_html,
                re.I | re.S,
            ):
                rows.append({
                    "href": html.unescape(match.group("href")),
                    "name": re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", match.group("name")))).strip(),
                    "number": re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", match.group("number")))).strip(),
                    "location": re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", match.group("location")))).strip(),
                    "profession": re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", match.group("profession")))).strip(),
                    "status": re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", match.group("status")))).strip(),
                })
            readable = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", result_html))).strip()
            return readable, rows, opener

        def direct_name_priority(row_name: str) -> int:
            return name_match_priority_for_targets(row_name, target_names)

        def direct_status_priority(status_text: str) -> int:
            return active_row_priority(status_text)

        direct_body = ""
        direct_rows: list[dict[str, str]] = []
        direct_opener = None
        best_row = None
        best_score = (-999, -1)
        best_opener = None
        for query in me_query_variants(org.organization_name):
            try:
                direct_body, direct_rows, direct_opener = run_me_direct_search(query)
            except Exception:
                direct_body, direct_rows, direct_opener = "", [], None
            if not direct_rows:
                if direct_body and re.search(r"\b0\s+records?\s+found\b|no records|no results", direct_body, re.I):
                    continue
                continue
            for row in direct_rows:
                row_text = " ".join(row.get(key, "") for key in ["name", "number", "location", "profession", "status"])
                row_score = candidate_selection_score_for_targets(row.get("name", ""), target_names, row_text)
                if row_score[0] < 0:
                    continue
                if row_score > best_score:
                    best_score = row_score
                    best_row = row
                    best_opener = direct_opener
            if best_row and best_opener:
                break

        if best_row and best_opener:
            detail_url = urljoin("https://www.pfr.maine.gov/ALMSOnline/ALMSQuery/", best_row.get("href", ""))
            detail_text = ""
            try:
                detail_response = best_opener.open(detail_url, timeout=15)
                detail_html = detail_response.read().decode("utf-8", "replace")
                detail_text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", detail_html))).strip()
            except Exception:
                detail_text = ""
            status_match = re.search(r"\bStatus:\s*(.+?)\s+Expiration\s+Date:", detail_text, re.I)
            expiration_match = re.search(r"\bExpiration\s+Date:\s*(\d{1,2}/\d{1,2}/\d{4})", detail_text, re.I)
            status_text = (status_match.group(1).strip() if status_match else "") or best_row.get("status", "")
            expiration_text = expiration_match.group(1).strip() if expiration_match else ""
            result.source_url = detail_url or url
            result.matched_registry_name = best_row.get("name", "")
            result.matched_registry_identifier = best_row.get("number", "")
            result.status = status_text or best_row.get("status") or STATUS_UNKNOWN
            result.raw_status_text = "; ".join(
                part for part in [result.status, f"Expiration Date: {expiration_text}" if expiration_text else ""] if part
            )
            if re.search(r"\bACTIVE\b", result.raw_status_text, re.I) and expiration_text:
                result.source_note = "Maine uses the Status and Expiration Date shown on the public detail page."
            else:
                result.source_note = "Maine uses the Status shown on the matched public registry result."
            result.success = True
            return result
        elif direct_body and re.search(r"\b0\s+records?\s+found\b|no records|no results", direct_body, re.I):
            result.raw_status_text = "No record found"
            result.status = STATUS_NOT_REGISTERED
            result.source_note = "Maine search returned no matching organization result."
            result.success = True
            return result

        def run_me_search(query: str) -> str:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            safe_wait_for_network_idle(page, timeout=3000)
            fast_sleep(0.4)

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
                raise RuntimeError("Could not find ME Regulator dropdown")
            try:
                regulator.select_option(label="CHARITABLE SOLICITATION")
            except Exception:
                regulator.select_option(label="ALL")
            fast_sleep(0.3)

            for label in ["Begins with", "Begins With"]:
                try:
                    page.get_by_label(re.compile(label, re.I)).check(timeout=1500)
                    break
                except Exception:
                    pass
            try:
                page.evaluate(
                    """
                    () => {
                        const labels = Array.from(document.querySelectorAll('label'));
                        for (const label of labels) {
                            if (/begins\\s+with/i.test(label.innerText || label.textContent || '')) {
                                const input = label.control || document.getElementById(label.getAttribute('for') || '');
                                if (input && input.type === 'radio') {
                                    input.checked = true;
                                    input.dispatchEvent(new Event('change', { bubbles: true }));
                                    return true;
                                }
                            }
                        }
                        const radios = Array.from(document.querySelectorAll('input[type="radio"]'));
                        for (const radio of radios) {
                            const text = ((radio.parentElement && radio.parentElement.innerText) || '').trim();
                            if (/begins\\s+with/i.test(text)) {
                                radio.checked = true;
                                radio.dispatchEvent(new Event('change', { bubbles: true }));
                                return true;
                            }
                        }
                        return false;
                    }
                    """
                )
            except Exception:
                pass

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
                raise RuntimeError("Could not find ME Company Name input")
            name_input.click(timeout=3000)
            name_input.fill("")
            name_input.fill(query)
            fast_sleep(0.3)

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
                raise RuntimeError("Could not find ME Search button")
            search_button.click(timeout=3000, no_wait_after=True)
            fast_sleep(1)
            safe_wait_for_network_idle(page, timeout=2000)
            try:
                return page.locator("body").inner_text(timeout=6000)
            except Exception:
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=6000)
                    fast_sleep(1)
                    return page.locator("body").inner_text(timeout=6000)
                except Exception:
                    return ""

        body = ""
        found_positive_result = False
        for query in me_query_variants(org.organization_name):
            body = run_me_search(query)
            no_match = re.search(r"0 records found|no records|no results|no companies found|no data", body, re.I)
            found_positive_result = bool(re.search(r"\b[1-9]\d*\s+records?\s+found\b|Search\s+Result", body, re.I))
            try:
                found_positive_result = found_positive_result or page.locator("a[href*='ShowDetail.aspx'], a[href*='ShowDetail']").count() > 0
            except Exception:
                pass
            if found_positive_result:
                break

        if not found_positive_result or re.search(r"0 records found|no records|no results|no companies found|no data", body, re.I):
            result.raw_status_text = "No record found"
            result.status = STATUS_NOT_REGISTERED
            result.source_note = "Maine search returned no matching organization result."
            result.success = True
            return result

        target_exact = re.sub(r"\s+", " ", (org.organization_name or "").strip()).upper()
        target_normalized = normalize_name(target_names[0])

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
                    name_priority = name_match_priority_for_targets(link_text or row_text, target_names)
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
                    status_priority = active_row_priority(row_status)
                    row_score = (name_priority, status_priority)
                    if row_score > best_table_score:
                        best_table_score = row_score
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
                        priority = name_match_priority_for_targets(txt, target_names)
                        if priority < 0:
                            continue
                        status_priority = 0
                        row_text = txt
                        try:
                            row_text = re.sub(r"\s+", " ", link.locator("xpath=ancestor::tr[1]").inner_text(timeout=1500)).strip()
                        except Exception:
                            row_text = txt
                        candidate_score = candidate_selection_score_for_targets(txt, target_names, row_text)
                        if candidate_score[0] < 0:
                            continue
                        priority, status_priority = candidate_score
                        if (
                            priority > best_priority
                            or (priority == best_priority and status_priority > best_status_priority)
                        ):
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
        if best_row_text:
            try:
                result.matched_registry_name = re.sub(r"\s+", " ", best_link.inner_text(timeout=1000)).strip()
            except Exception:
                result.matched_registry_name = ""
            number_match = re.search(r"\b(CO\d+)\b", best_row_text, re.I)
            if number_match:
                result.matched_registry_identifier = number_match.group(1).upper()

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
                    best_status_priority = -999
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
                                    priority = name_match_priority_for_targets(txt, target_names)
                                    if priority < 0:
                                        continue
                                    row_text = txt
                                    try:
                                        row_text = re.sub(r"\s+", " ", link.locator("xpath=ancestor::tr[1]").inner_text(timeout=1000)).strip()
                                    except Exception:
                                        pass
                                    status_priority = active_row_priority(row_text)
                                    if priority > best_priority or (priority == best_priority and status_priority > best_status_priority):
                                        best_priority = priority
                                        best_status_priority = status_priority
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
        target_names = match_target_names(org)
        last_goto_error = None
        for goto_attempt in range(2):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                safe_wait_for_network_idle(page, timeout=3000)
                fast_sleep(0.75)
                last_goto_error = None
                break
            except Exception as e:
                last_goto_error = e
                if goto_attempt == 0:
                    fast_sleep(2)
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
        search_input.fill(search_name_query_variants(org.organization_name, max_words=5)[0])
        fast_sleep(0.5)

        search_button = None
        for sel in ['button[aria-label="Execute search"]', 'button[aria-label*="Execute search"]']:
            try:
                loc = page.locator(sel).first
                loc.wait_for(state="visible", timeout=6000)
                search_button = loc
                break
            except Exception:
                continue
        if not search_button:
            result.error = "Could not find ND search button"
            return result
        search_button.click(timeout=5000)
        fast_sleep(2)
        safe_wait_for_network_idle(page, timeout=5000)
        fast_sleep(0.5)

        body = page.locator("body").inner_text(timeout=5000)
        if re.search(r"Results:\s*0\b|No results|No matching", body, re.I):
            # Do not stop on the first no-result response. North Dakota's name
            # search can miss punctuation/possessive variants that a later safe
            # query variant finds.
            body = ""

        best_button = None
        best_priority = -1
        best_status_score = -999
        best_match_name = ""
        best_match_identifier = ""
        best_match_row_text = ""
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
                        priority, status_score = candidate_selection_score_for_targets(name_text, target_names, combined_txt)
                        if (
                            priority >= 0
                            and (
                                priority > best_priority
                                or (priority == best_priority and status_score > best_status_score)
                            )
                        ):
                            best_priority = priority
                            best_status_score = status_score
                            best_button = item
                            best_match_name = name_text
                            best_match_row_text = combined_txt
                            best_match_identifier = extract_registry_identifier_from_text(combined_txt, org.ein)
                    except Exception:
                        continue
            except Exception:
                continue

        if not best_button or best_priority < 0:
            try:
                rows = page.locator("tr")
                count = min(rows.count(), 100)
                for i in range(count):
                    row = rows.nth(i)
                    try:
                        row_txt = re.sub(r"\s+", " ", row.inner_text(timeout=1000)).strip()
                        if not row_txt or re.search(r"\bForm\s+Info\b.*\bSOS\s+Control\b", row_txt, re.I):
                            continue
                        cells = row.locator("td")
                        if cells.count() < 2:
                            continue
                        name_text = re.sub(r"\s+", " ", cells.nth(0).inner_text(timeout=1000)).strip()
                        if not name_text or text_has_wrong_ein_match(row_txt, org.ein):
                            continue
                        priority, status_score = candidate_selection_score_for_targets(name_text, target_names, row_txt)
                        if (
                            priority >= 0
                            and (
                                priority > best_priority
                                or (priority == best_priority and status_score > best_status_score)
                            )
                        ):
                            click_target = row.locator('div.interactive-cell-button, div[role="button"], a, button').first
                            if click_target.count() == 0:
                                click_target = cells.nth(0)
                            best_priority = priority
                            best_status_score = status_score
                            best_button = click_target
                            best_match_name = name_text
                            best_match_row_text = row_txt
                            best_match_identifier = extract_registry_identifier_from_text(row_txt, org.ein)
                    except Exception:
                        continue
            except Exception:
                pass

        if not best_button or best_priority < 0:
            # If the first formal name query does not produce an acceptable row,
            # try the safe query variants. Candidate acceptance still uses the
            # full target-name set, so broad queries cannot be accepted unless
            # the returned row itself is a credible match.
            for query in search_name_query_variants(org.organization_name, max_words=5)[1:5]:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=12000)
                    safe_wait_for_network_idle(page, timeout=2500)
                    fast_sleep(0.5)
                    search_input = find_visible_input(page, [
                        'input[placeholder*="Search by name"]',
                        'input[aria-label*="Search by name"]',
                        'input[type="text"]',
                    ])
                    if not search_input:
                        continue
                    search_input.click(timeout=5000)
                    search_input.fill("")
                    search_input.fill(query)
                    fast_sleep(0.4)
                    search_button = None
                    for sel in ['button[aria-label="Execute search"]', 'button[aria-label*="Execute search"]']:
                        try:
                            loc = page.locator(sel).first
                            loc.wait_for(state="visible", timeout=3000)
                            search_button = loc
                            break
                        except Exception:
                            continue
                    if not search_button:
                        continue
                    search_button.click(timeout=5000)
                    fast_sleep(3)
                    safe_wait_for_network_idle(page, timeout=2500)
                    fast_sleep(0.25)
                    body = page.locator("body").inner_text(timeout=4000)
                    if re.search(r"Results:\s*0\b|No results|No matching", body, re.I):
                        continue
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
                                    priority, status_score = candidate_selection_score_for_targets(name_text, target_names, combined_txt)
                                    if (
                                        priority >= 0
                                        and (
                                            priority > best_priority
                                            or (priority == best_priority and status_score > best_status_score)
                                        )
                                    ):
                                        best_priority = priority
                                        best_status_score = status_score
                                        best_button = item
                                        best_match_name = name_text
                                        best_match_row_text = combined_txt
                                        best_match_identifier = extract_registry_identifier_from_text(combined_txt, org.ein)
                                except Exception:
                                    continue
                        except Exception:
                            continue
                    if not best_button or best_priority < 0:
                        try:
                            rows = page.locator("tr")
                            count = min(rows.count(), 100)
                            for i in range(count):
                                row = rows.nth(i)
                                try:
                                    row_txt = re.sub(r"\s+", " ", row.inner_text(timeout=1000)).strip()
                                    if not row_txt or re.search(r"\bForm\s+Info\b.*\bSOS\s+Control\b", row_txt, re.I):
                                        continue
                                    cells = row.locator("td")
                                    if cells.count() < 2:
                                        continue
                                    name_text = re.sub(r"\s+", " ", cells.nth(0).inner_text(timeout=1000)).strip()
                                    if not name_text or text_has_wrong_ein_match(row_txt, org.ein):
                                        continue
                                    priority, status_score = candidate_selection_score_for_targets(name_text, target_names, row_txt)
                                    if (
                                        priority >= 0
                                        and (
                                            priority > best_priority
                                            or (priority == best_priority and status_score > best_status_score)
                                        )
                                    ):
                                        click_target = row.locator('div.interactive-cell-button, div[role="button"], a, button').first
                                        if click_target.count() == 0:
                                            click_target = cells.nth(0)
                                        best_priority = priority
                                        best_status_score = status_score
                                        best_button = click_target
                                        best_match_name = name_text
                                        best_match_row_text = row_txt
                                        best_match_identifier = extract_registry_identifier_from_text(row_txt, org.ein)
                                except Exception:
                                    continue
                        except Exception:
                            pass
                    if best_button and best_priority >= 0:
                        break
                except Exception:
                    continue

        if not best_button or best_priority < 0:
            result.raw_status_text = "No matching organization result"
            result.status = STATUS_NOT_REGISTERED
            result.source_note = "North Dakota search results did not contain a matching organization entry."
            result.success = True
            return result

        result.matched_registry_name = best_match_name
        result.matched_registry_identifier = best_match_identifier
        best_button.click(timeout=5000)
        try:
            page.get_by_text("Registration Date", exact=True).wait_for(timeout=8000)
        except Exception:
            fast_sleep(2)
        safe_wait_for_network_idle(page, timeout=5000)
        fast_sleep(0.5)

        detail_text = page.locator("body").inner_text(timeout=8000)
        if text_has_wrong_ein_match(detail_text, org.ein):
            return reject_wrong_ein_result(result, "North Dakota")
        if not result.matched_registry_name:
            result.matched_registry_name = extract_labeled_value_from_text(detail_text, ["Organization Name", "Charity Name", "Name"])
        if not result.matched_registry_identifier:
            result.matched_registry_identifier = extract_registry_identifier_from_text(f"{best_match_row_text} {detail_text}", org.ein)
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
