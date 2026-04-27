from __future__ import annotations

import calendar
import csv
import hashlib
import importlib.util
import html
import io
import json
import os
import re
import secrets
import smtplib
import sys
import time
import traceback
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse
import urllib.request

from PIL import Image, ImageDraw, ImageFont
try:
    from pypdf import PdfReader, PdfWriter
except Exception:
    PdfReader = None
    PdfWriter = None

BASE_DIR = Path(__file__).resolve().parent
def first_existing_path(*paths: str) -> Path:
    for path in paths:
        candidate = Path(path)
        if candidate.exists():
            return candidate
    return Path(paths[0])


CHECKER_PATH = Path(os.environ["CE_CHECKER_PATH"]) if os.environ.get("CE_CHECKER_PATH") else first_existing_path(
    str(BASE_DIR / "Charity_Checker_Script for 13_states.py"),
    r"C:\Users\nyagh\Downloads\Charity_Checker_Script for 13_states.py",
)
CHARITY_OR_PATH = Path(os.environ["CE_CHARITY_OR_PATH"]) if os.environ.get("CE_CHARITY_OR_PATH") else first_existing_path(
    str(BASE_DIR / "Charity_OR.txt"),
    r"C:\Users\nyagh\OneDrive\Desktop\Compliance Express\Charity_OR.txt",
)
LOG_PATH = Path(os.environ.get("CE_LOG_PATH", str(BASE_DIR / "registry_snapshot_server.log")))
LEAD_LOG_PATH = Path(__file__).with_name("registry_snapshot_leads.csv")
PIN_LOG_PATH = Path(__file__).with_name("registry_snapshot_passcodes.log")
ARTIFACTS_DIR = Path(os.environ.get("CE_ARTIFACTS_DIR", str(BASE_DIR / "artifacts")))
HOST = os.environ.get("HOST") or ("0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
PORT = int(os.environ.get("PORT", "8765"))
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", f"http://127.0.0.1:{PORT}").rstrip("/")
APP_VERSION = "2026.04.27.5"
SUPPORTED_STATES = ["AK", "CA", "CO", "HI", "MA", "MD", "ME", "ND", "NJ", "NY", "PA", "SC", "VA"]
EXTENSION_SCENARIO_STATES = {"CA", "CT", "HI", "KY", "MA", "MD", "NY", "OH", "PA"}
MAX_STATES_PER_SNAPSHOT = 3
MAX_EXTERNAL_EXEMPT_ORGS = 3
DOMAIN_LIMIT_DAYS = 7
ADMIN_PASSCODE = "8977"
PIN_EXPIRY_SECONDS = 10 * 60
PIN_MAX_ATTEMPTS = 5
VERIFICATION_TOKEN_SECONDS = 60 * 60
EXEMPT_EMAIL_DOMAIN = "compliance-express.com"
EXEMPT_EMAIL_ADDRESSES = {"nyaghi17@gmail.com"}
DOMAIN_LIMIT_PATH = Path(__file__).with_name("registry_snapshot_domain_limits.json")
PIN_STORE: dict[str, dict] = {}
VERIFICATION_TOKENS: dict[str, dict] = {}
ORG_NAME_CACHE: dict[str, str] = {}
FISCAL_YEAR_END_OVERRIDES = {
    "208428450": (6, 30),
    "546053660": (6, 30),
}


def load_checker():
    spec = importlib.util.spec_from_file_location("charity_state_checker_v9", CHECKER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load checker from {CHECKER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = load_checker()


def artifact_safe_name(org_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", org_name).strip("_")[:80] or "registry_snapshot"


def evidence_pdf_path(state: str, org_name: str) -> Path:
    return ARTIFACTS_DIR / state.upper() / f"{artifact_safe_name(org_name)}.pdf"


def evidence_png_path(state: str, org_name: str) -> Path:
    return ARTIFACTS_DIR / state.upper() / f"{artifact_safe_name(org_name)}.png"


def ak_registration_pdf_path(org_name: str) -> Path:
    return ARTIFACTS_DIR / "AK" / f"{artifact_safe_name(org_name)}_registration.pdf"


def evidence_url(state: str, org_name: str) -> str:
    return f"{PUBLIC_BASE_URL}/evidence/{state.upper()}/{artifact_safe_name(org_name)}.pdf"


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = str(text or "").split()
    if not words:
        return [""]
    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "arialbd.ttf" if bold else "arial.ttf",
        "Calibri.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def evidence_summary_image(result, body: str, status: str, comments: str) -> Image.Image:
    width, height = 1400, 1800
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = load_font(42, bold=True)
    section_font = load_font(22, bold=True)
    label_font = load_font(19, bold=True)
    text_font = load_font(19)
    small_font = load_font(16)
    navy = "#0B2A5B"
    red = "#C62828"
    slate = "#334155"
    light = "#EEF2F7"

    y = 70
    draw.text((70, y), "Compliance", fill=navy, font=title_font)
    draw.text((320, y), "Express", fill=red, font=title_font)
    draw.text((70, y + 68), "Instant Compliance Snapshot Evidence", fill=navy, font=section_font)
    draw.line((70, y + 110, width - 70, y + 110), fill=red, width=5)
    y += 155

    context = filing_context(result, body)
    fiscal_end = context.get("fiscal_end")
    fiscal_end_text = f"{fiscal_end[0]}/{fiscal_end[1]}" if fiscal_end else "Not identified"
    due_date = context.get("due_date")
    rows = [
        ("Organization", result.organization_name),
        ("EIN", result.ein),
        ("State", result.state),
        ("Source URL", result.source_url),
        ("Raw Registry Status", result.raw_status_text or "Not shown"),
        ("Source Note", result.source_note or "Not provided"),
        ("CE Status", status),
        ("CE Comment", comments),
        ("Most Recent Fiscal/Filing Year Read", context.get("represented_year") or "Not identified"),
        ("Fiscal Year End Used", fiscal_end_text),
        ("Calculated Due Date Used", format_date(due_date) if due_date else "Not identified"),
    ]

    draw.rounded_rectangle((60, y, width - 60, y + 1040), radius=24, fill="#F8FAFC", outline="#CBD5E1", width=2)
    y += 36
    draw.text((90, y), "Status Basis", fill=navy, font=section_font)
    y += 56
    for label, value in rows:
        draw.rectangle((90, y, width - 90, y + 1), fill=light)
        y += 18
        draw.text((95, y), label.upper(), fill=red, font=label_font)
        y += 30
        for line in wrap_text(draw, str(value), text_font, width - 190):
            draw.text((95, y), line, fill=slate, font=text_font)
            y += 28
        y += 20

    draw.text((90, height - 190), "The captured public registry page follows this summary page.", fill=navy, font=section_font)
    draw.text(
        (90, height - 140),
        "This snapshot is based on public registry information available at the time of lookup and is not legal advice.",
        fill=slate,
        font=small_font,
    )
    return image


def screenshot_to_pdf(state: str, org_name: str, result=None, body: str = "", status: str = "", comments: str = "") -> str | None:
    png_path = evidence_png_path(state, org_name)
    pdf_path = evidence_pdf_path(state, org_name)
    if not png_path.exists():
        return None

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(png_path) as image:
        if image.mode in {"RGBA", "P"}:
            image = image.convert("RGB")
        if image.width > 1400:
            ratio = 1400 / image.width
            image = image.resize((1400, max(1, int(image.height * ratio))), Image.Resampling.LANCZOS)
        output_buffer = io.BytesIO()
        if result is not None:
            summary = evidence_summary_image(result, body, status, comments)
            summary.save(output_buffer, "PDF", resolution=144.0, save_all=True, append_images=[image])
        else:
            image.save(output_buffer, "PDF", resolution=144.0)

    ak_pdf = ak_registration_pdf_path(org_name)
    if state.upper() == "AK" and ak_pdf.exists() and PdfReader is not None and PdfWriter is not None:
        output_buffer.seek(0)
        writer = PdfWriter()
        for source in [output_buffer, ak_pdf]:
            reader = PdfReader(source)
            for page in reader.pages:
                writer.add_page(page)
        with pdf_path.open("wb") as f:
            writer.write(f)
    else:
        pdf_path.write_bytes(output_buffer.getvalue())
    return evidence_url(state, org_name)


def save_focused_viewport_artifact(page, state: str, org_name: str) -> None:
    state_dir = ARTIFACTS_DIR / state.upper()
    state_dir.mkdir(parents=True, exist_ok=True)
    safe_name = artifact_safe_name(org_name)
    try:
        (state_dir / f"{safe_name}.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
    try:
        page.screenshot(path=str(state_dir / f"{safe_name}.png"), full_page=False)
    except Exception:
        pass


def log_error(message: str) -> None:
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
        f.write(traceback.format_exc())
        f.write("\n")


def append_lead_log(email: str, results: list[dict]) -> None:
    if not email or not results:
        return
    LEAD_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "checked_at",
        "email",
        "domain",
        "organization_name",
        "ein",
        "state",
        "status",
        "comments",
        "evidence_url",
        "source_url",
    ]
    write_header = not LEAD_LOG_PATH.exists() or LEAD_LOG_PATH.stat().st_size == 0
    checked_at = datetime.now().isoformat(timespec="seconds")
    domain = email_domain(email)
    with LEAD_LOG_PATH.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        for result in results:
            writer.writerow({
                "checked_at": checked_at,
                "email": email.strip(),
                "domain": domain,
                "organization_name": result.get("organization_name", ""),
                "ein": result.get("ein", ""),
                "state": result.get("state", ""),
                "status": result.get("status", ""),
                "comments": result.get("comments", ""),
                "evidence_url": result.get("evidence_url", ""),
                "source_url": result.get("source_url", ""),
            })


def email_domain(email_address: str) -> str:
    parts = (email_address or "").strip().lower().split("@")
    return parts[1] if len(parts) == 2 and parts[1] else ""


def normalize_email(email_address: str) -> str:
    return (email_address or "").strip().lower()


def valid_email(email_address: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalize_email(email_address)))


def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


def cleanup_verification_state() -> None:
    now = time.time()
    for email_key in list(PIN_STORE):
        if PIN_STORE[email_key].get("expires_at", 0) < now:
            PIN_STORE.pop(email_key, None)
    for token in list(VERIFICATION_TOKENS):
        if VERIFICATION_TOKENS[token].get("expires_at", 0) < now:
            VERIFICATION_TOKENS.pop(token, None)


def send_pin_email(email_address: str, pin: str) -> str:
    smtp_host = os.environ.get("CE_SMTP_HOST", "").strip()
    smtp_port = int(os.environ.get("CE_SMTP_PORT", "587") or "587")
    smtp_user = os.environ.get("CE_SMTP_USER", "").strip()
    smtp_password = os.environ.get("CE_SMTP_PASSWORD", "").strip()
    smtp_from = os.environ.get("CE_SMTP_FROM", smtp_user or "no-reply@compliance-express.com").strip()

    if not smtp_host or not smtp_user or not smtp_password:
        PIN_LOG_PATH.write_text("", encoding="utf-8") if not PIN_LOG_PATH.exists() else None
        with PIN_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} | {email_address} | {pin}\n")
        return "dev_log"

    message = EmailMessage()
    message["Subject"] = "Your Compliance Express passcode"
    message["From"] = smtp_from
    message["To"] = email_address
    message.set_content(
        "Your Compliance Express passcode is:\n\n"
        f"{pin}\n\n"
        "This passcode expires in 10 minutes. If you did not request it, you can ignore this email."
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(message)
    return "email"


def create_pin_for_email(email_address: str) -> str:
    cleanup_verification_state()
    pin = f"{secrets.randbelow(1_000_000):06d}"
    PIN_STORE[normalize_email(email_address)] = {
        "pin_hash": hash_pin(pin),
        "expires_at": time.time() + PIN_EXPIRY_SECONDS,
        "attempts": 0,
    }
    return pin


def verify_pin(email_address: str, pin: str) -> str | None:
    cleanup_verification_state()
    email_key = normalize_email(email_address)
    record = PIN_STORE.get(email_key)
    if not record:
        return None
    if record.get("attempts", 0) >= PIN_MAX_ATTEMPTS:
        PIN_STORE.pop(email_key, None)
        return None
    record["attempts"] = record.get("attempts", 0) + 1
    if hash_pin((pin or "").strip()) != record.get("pin_hash"):
        return None
    PIN_STORE.pop(email_key, None)
    token = secrets.token_urlsafe(32)
    VERIFICATION_TOKENS[token] = {
        "email": email_key,
        "expires_at": time.time() + VERIFICATION_TOKEN_SECONDS,
    }
    return token


def is_verified_email_token(email_address: str, token: str) -> bool:
    cleanup_verification_state()
    if not token:
        return False
    record = VERIFICATION_TOKENS.get(token)
    return bool(record and record.get("email") == normalize_email(email_address))


def is_verified_internal_passcode(email_address: str, passcode: str) -> bool:
    return is_exempt_domain(email_domain(email_address)) and (passcode or "").strip() == ADMIN_PASSCODE


def is_exempt_domain(domain: str) -> bool:
    return domain.lower() == EXEMPT_EMAIL_DOMAIN


def is_exempt_email(email: str) -> bool:
    return (email or "").strip().lower() in EXEMPT_EMAIL_ADDRESSES


def is_privileged_request(email: str, domain: str) -> bool:
    return is_exempt_domain(domain) or is_exempt_email(email)


def state_limit_for_request(domain: str) -> int:
    return len(SUPPORTED_STATES) if is_exempt_domain(domain) else MAX_STATES_PER_SNAPSHOT


def org_limit_for_request(email: str, domain: str) -> int:
    if is_exempt_domain(domain):
        return 100
    if is_exempt_email(email):
        return MAX_EXTERNAL_EXEMPT_ORGS
    return 1


def load_domain_limits() -> dict:
    if not DOMAIN_LIMIT_PATH.exists():
        return {}
    try:
        return json.loads(DOMAIN_LIMIT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_domain_limits(limits: dict) -> None:
    DOMAIN_LIMIT_PATH.write_text(json.dumps(limits, indent=2, sort_keys=True), encoding="utf-8")


def domain_is_limited(domain: str) -> bool:
    if not domain or is_exempt_domain(domain):
        return False
    limits = load_domain_limits()
    prior = int(limits.get(domain, 0) or 0)
    if not prior:
        return False
    return int(time.time()) - prior < DOMAIN_LIMIT_DAYS * 24 * 60 * 60


def record_domain_check(domain: str) -> None:
    if not domain or is_exempt_domain(domain):
        return
    limits = load_domain_limits()
    limits[domain] = int(time.time())
    save_domain_limits(limits)


def public_status(result) -> str:
    status = (result.status or "").strip()
    error = (result.error or "").strip().lower()

    if error:
        return "Site Not Reachable"

    normalized = status.lower()
    if normalized == "unknown":
        if (result.raw_status_text or "").strip() and not re.search(r"no matching|no record|not found|no results", result.raw_status_text or "", re.I):
            return "Unknown"
        return "Not Registered" if result.success else "Site Not Reachable"
    if normalized in {"not registered", "not found", "no record", "no record found"}:
        return "Not Registered"
    if normalized in {"current", "active", "good standing", "compliant"}:
        return "Current"
    if "exempt" in normalized:
        return "Exempt"
    if "upcoming" in normalized or "due" in normalized:
        return "Upcoming Filing"
    if any(token in normalized for token in ["delinquent", "non-compliant", "non compliant", "expired", "revoked", "suspended", "overdue", "closed", "inactive"]):
        return "Delinquent"

    return status


def parse_due_date(value: str) -> date | None:
    formats = [
        "%m/%d/%Y",
        "%m/%d/%y",
        "%m-%d-%Y",
        "%m-%d-%y",
        "%Y-%m-%d",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d-%b-%y",
        "%d-%b-%Y",
    ]
    cleaned = value.strip()
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def parse_ce_date(value: str) -> date | None:
    for fmt in ("%d-%b-%y", "%d-%b-%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def fifteenth_day_after_fiscal_year_end(fy_end: date, months_after_end_month: int) -> date:
    month_anchor = date(fy_end.year, fy_end.month, 1)
    return add_months(month_anchor, months_after_end_month).replace(day=15)


def fiscal_period_for_ein(ein: str) -> tuple[date | None, date | None]:
    target = re.sub(r"\D", "", ein or "")
    if not target or not CHARITY_OR_PATH.exists():
        return None, None

    with CHARITY_OR_PATH.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if len(row) < 16:
                continue
            if re.sub(r"\D", "", row[4]) != target:
                continue
            period_start = parse_ce_date(row[14])
            period_end = parse_ce_date(row[15])
            return period_start, period_end
    return None, None


def organization_name_for_ein(ein: str) -> str:
    target = re.sub(r"\D", "", ein or "")
    if not target or not CHARITY_OR_PATH.exists():
        return ""
    with CHARITY_OR_PATH.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if len(row) < 7:
                continue
            if re.sub(r"\D", "", row[4]) == target:
                return (row[6] or "").strip().strip('"')
    return ""


def public_profile_name_for_ein(ein: str) -> str:
    target = re.sub(r"\D", "", ein or "")
    if len(target) != 9:
        return ""
    if target in ORG_NAME_CACHE:
        return ORG_NAME_CACHE[target]
    try:
        url = f"https://projects.propublica.org/nonprofits/api/v2/organizations/{target}.json"
        request = urllib.request.Request(url, headers={"User-Agent": "ComplianceExpressRegistrySnapshot/1.0"})
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
        name = ((payload.get("organization") or {}).get("name") or "").strip()
    except Exception:
        name = ""
    ORG_NAME_CACHE[target] = name
    return name


def resolved_organization_name(ein: str, supplied_name: str = "") -> str:
    supplied_name = (supplied_name or "").strip()
    if supplied_name:
        return supplied_name
    return organization_name_for_ein(ein) or public_profile_name_for_ein(ein)


def format_ein(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 9:
        return f"{digits[:2]}-{digits[2:]}"
    return (value or "").strip()


def fiscal_year_end_for_ein(ein: str) -> tuple[int, int] | None:
    target = re.sub(r"\D", "", ein or "")
    if target in FISCAL_YEAR_END_OVERRIDES:
        return FISCAL_YEAR_END_OVERRIDES[target]
    _, period_end = fiscal_period_for_ein(ein)
    if period_end:
        return period_end.month, period_end.day
    return None


def format_date(value: date) -> str:
    return f"{value.month}/{value.day}/{value.year}"


def filing_due_date(state: str, report_year: int, fiscal_end: tuple[int, int]) -> tuple[date | None, str]:
    fy_end = date(report_year, fiscal_end[0], fiscal_end[1])
    state = state.upper()
    if state == "CA":
        if fiscal_end == (6, 30):
            base_due = date(report_year, 12, 31)
            extended_due = date(report_year + 1, 5, 15)
            effective_due = base_due if base_due >= date.today() else extended_due
            return effective_due, (
                f"California annual filing base due date is {format_date(base_due)}; "
                f"if an extension was applied, the extended due date is {format_date(extended_due)}"
            )
        base_due = add_months(fy_end, 4) + timedelta(days=15)
        extended_due = add_months(base_due, 6)
        effective_due = base_due if base_due >= date.today() else extended_due
        return effective_due, (
            f"California annual filing base due date is {format_date(base_due)}; "
            f"if an extension was applied, the extended due date is {format_date(extended_due)}"
        )
    if state == "MD":
        base_due = add_months(fy_end, 6)
        # Maryland has an automatic extension; for June 30 FYE, 2025 filing is effectively due 5/15/2026.
        if fiscal_end == (6, 30):
            base_due = date(report_year, 12, 31)
            return date(report_year + 1, 5, 15), f"base due {format_date(base_due)}; Maryland automatic extension moves the effective due date to 5/15/{report_year + 1}"
        return base_due, f"based on Maryland's six-month annual filing cycle"
    if state == "MA":
        base_due = fifteenth_day_after_fiscal_year_end(fy_end, 5)
        extended_due = add_months(base_due, 6)
        return extended_due, (
            f"Massachusetts Form PC base due date is {format_date(base_due)}; "
            "registered charities in compliance receive an automatic 6-month extension"
        )
    if state == "NY":
        base_due = fifteenth_day_after_fiscal_year_end(fy_end, 5)
        extended_due = add_months(base_due, 6)
        return extended_due, (
            f"New York annual filing base due date is {format_date(base_due)}; "
            "the public guidance references a 180-day extension of time to file"
        )
    if state == "NJ":
        base_due = add_months(fy_end, 6)
        if fiscal_end == (6, 30):
            base_due = date(report_year, 12, 31)
            return date(report_year + 1, 5, 15), (
                f"New Jersey annual renewal base due date is {format_date(base_due)}; "
                f"if an extension applies, the extended due date is {format_date(date(report_year + 1, 5, 15))}"
            )
        return base_due, "based on New Jersey's six-month annual renewal cycle"
    if state == "PA":
        return add_months(fy_end, 11), "based on Pennsylvania's annual renewal cycle"
    if state == "VA":
        return add_months(fy_end, 4) + timedelta(days=15), "based on Virginia's 4.5-month annual renewal cycle"
    if state == "SC":
        return add_months(fy_end, 4) + timedelta(days=15), "based on South Carolina's 4.5-month annual renewal cycle"
    if state == "CO":
        return add_months(fy_end, 5) + timedelta(days=15), "based on Colorado's annual reporting cycle"
    if state == "HI":
        return add_months(fy_end, 4) + timedelta(days=15), "based on Hawaii's 4.5-month annual filing cycle"
    if state == "ME":
        return add_months(fy_end, 5), "based on Maine's annual filing cycle"
    if state == "ND":
        return date(report_year + 1, 9, 1), "based on North Dakota's annual charitable organization renewal cycle"
    if state == "AK":
        return date(report_year + 1, 9, 1), "based on Alaska's annual charitable registration cycle"
    return None, "state due-date rule is not encoded"


def filing_due_date_options(state: str, report_year: int, fiscal_end: tuple[int, int]) -> dict:
    state = state.upper()
    fy_end = date(report_year, fiscal_end[0], fiscal_end[1])
    if state == "CA":
        base_due = date(report_year, 12, 31) if fiscal_end == (6, 30) else add_months(fy_end, 4) + timedelta(days=15)
    elif state == "MD":
        base_due = add_months(fy_end, 6)
    elif state in {"MA", "NY", "HI", "SC"}:
        base_due = fifteenth_day_after_fiscal_year_end(fy_end, 5)
    elif state == "PA":
        base_due = add_months(fy_end, 11)
    elif state == "NJ":
        base_due = date(report_year, 12, 31) if fiscal_end == (6, 30) else add_months(fy_end, 6)
    else:
        due_date, rule_note = filing_due_date(state, report_year, fiscal_end)
        return {
            "base_due": due_date,
            "effective_due": due_date,
            "extended_due": None,
            "uses_extension_assumption": False,
            "rule_note": rule_note,
        }

    extended_due = add_months(base_due, 6) if state in EXTENSION_SCENARIO_STATES else None
    effective_due = base_due
    if state == "MD":
        rule_note = "Maryland has an automatic extension process; CE Status is based on the base due date"
    elif extended_due:
        rule_note = "CE Status is based on the base due date; extension impact is shown as a scenario"
    else:
        rule_note = filing_due_date(state, report_year, fiscal_end)[1]
    return {
        "base_due": base_due,
        "effective_due": effective_due,
        "extended_due": extended_due,
        "uses_extension_scenario": bool(extended_due),
        "uses_extension_assumption": False,
        "rule_note": rule_note,
    }


def latest_year_from_text(body: str, state: str) -> int | None:
    if state == "HI":
        tab_years = [
            int(match.group(1))
            for match in re.finditer(r"<li[^>]*>\s*<a[^>]*>\s*(20\d{2})\s*</a>", body or "", re.I)
        ]
        if tab_years:
            return max(tab_years)
    readable_body = html.unescape(re.sub(r"<[^>]+>", " ", body))
    patterns = [
        r"Most\s+Recent\s+Fiscal\s+Year\s*:?\s*(20\d{2})",
        r"Last\s+Year\s+Represented\s*:?\s*(20\d{2})",
        r"Year\s+Represented\s*:?\s*(20\d{2})",
        r"Latest\s+FYE\s*:?\s*(20\d{2})",
        r"Fiscal\s+Year\s*:?\s*(20\d{2})",
        r"Registration\s+Year\s*:?\s*(20\d{2})",
        r"\b(20\d{2})\s+annual\s+(?:report|filing)\b",
        r"\b(20\d{2})\s+registration\b",
        r"Accounting\s+Period\s+End\s+Date\s*:?\s*\d{1,2}[/-]\d{1,2}[/-](20\d{2})",
        r"Period\s+End(?:ing)?\s*:?\s*\d{1,2}[/-]\d{1,2}[/-](20\d{2})",
    ]
    years = []
    for pattern in patterns:
        for match in re.finditer(pattern, readable_body, re.I):
            years.append(int(match.group(1)))
    if state == "MA":
        for match in re.finditer(r"Form[\s-]*PC[^0-9]{0,80}(20\d{2})", readable_body, re.I):
            years.append(int(match.group(1)))
    if state == "HI":
        doc_match = re.search(r"\bDocuments\b([\s\S]{0,2500})", readable_body, re.I)
        if doc_match:
            for match in re.finditer(r"\b(20\d{2})\b", doc_match.group(1)):
                years.append(int(match.group(1)))
    if state == "NJ":
        for pattern in [
            r"(?:Filing|Fiscal|Financial|Renewal|Annual)[^0-9]{0,80}(20\d{2})",
            r"\b(20\d{2})\s+(?:annual|renewal|filing)",
        ]:
            for match in re.finditer(pattern, readable_body, re.I):
                years.append(int(match.group(1)))
    if state == "NY":
        ny_annual_match = re.search(r"Annual\s+filing\s+documents([\s\S]{0,5000}?)(?:Registration\s+documents|$)", readable_body, re.I)
        if ny_annual_match:
            ny_years = [
                int(match.group(1))
                for match in re.finditer(r"\b\d{1,2}[/-]\d{1,2}[/-](20\d{2})\b", ny_annual_match.group(1))
            ]
            if ny_years:
                return max(ny_years)
    return max(years) if years else None


def filing_context(result, body: str) -> dict:
    latest_year = latest_year_from_text(body, result.state)
    if latest_year is None and re.search(r"registration\s+found|year\s+represented|latest|most\s+recent|filing\s+year", result.raw_status_text or "", re.I):
        year_match = re.search(r"(20\d{2})", result.raw_status_text or "")
        latest_year = int(year_match.group(1)) if year_match else None
    period_start, period_end = fiscal_period_for_ein(result.ein)
    if latest_year is None and period_end:
        latest_year = period_end.year
    registry_fiscal_end = fiscal_year_end_from_body(body)
    fiscal_end = registry_fiscal_end or fiscal_year_end_for_ein(result.ein)

    if latest_year is None or fiscal_end is None:
        return {
            "represented_year": latest_year,
            "fiscal_end": fiscal_end,
            "next_report_year": None,
            "due_date": None,
            "comment": "Annual filing due date could not be determined from the available instant compliance snapshot."
        }

    next_report_year = latest_year + 1
    due_options = filing_due_date_options(result.state, next_report_year, fiscal_end)
    due_date = due_options["effective_due"]
    rule_note = due_options["rule_note"]
    comment = (
        f"{next_report_year} annual filing is due {format_date(due_date)} "
        f"based on a {fiscal_end[0]}/{fiscal_end[1]} fiscal year end; {rule_note}."
    )
    return {
        "represented_year": latest_year,
        "fiscal_end": fiscal_end,
        "next_report_year": next_report_year,
        "due_date": due_date,
        "base_due_date": due_options["base_due"],
        "extended_due_date": due_options["extended_due"],
        "uses_extension_assumption": due_options["uses_extension_assumption"],
        "uses_extension_scenario": due_options.get("uses_extension_scenario", False),
        "comment": comment
    }


def stale_represented_year_is_delinquent(represented_year: int | None) -> bool:
    return bool(represented_year and represented_year <= date.today().year - 2)


def md_financial_body(page) -> str:
    pieces = []
    try:
        pieces.append(page.locator("body").inner_text(timeout=5000))
    except Exception:
        pass
    for label in ["Financial Information", "Financial Informati"]:
        try:
            page.get_by_role("button", name=re.compile(label, re.I)).click(timeout=5000)
            time.sleep(3)
            break
        except Exception:
            continue
    try:
        page.locator("body").evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
    except Exception:
        pass
    try:
        pieces.append(page.locator("body").inner_text(timeout=8000))
    except Exception:
        pass
    try:
        page.get_by_text(re.compile(r"Most\s+Recent\s+Fiscal\s+Year|Year\s+Represented", re.I)).first.scroll_into_view_if_needed(timeout=5000)
        page.locator("body").evaluate("window.scrollBy(0, -140)")
        time.sleep(1)
    except Exception:
        pass
    try:
        pieces.append(page.content())
    except Exception:
        pass
    return "\n".join(pieces)


def md_detail_body(page) -> str:
    pieces = []
    try:
        pieces.append(page.locator("body").inner_text(timeout=5000))
    except Exception:
        pass
    for label in ["General Information", "General Informati"]:
        try:
            page.get_by_role("button", name=re.compile(label, re.I)).click(timeout=5000)
            time.sleep(2)
            break
        except Exception:
            continue
    try:
        pieces.append(page.locator("body").inner_text(timeout=8000))
    except Exception:
        pass
    pieces.append(md_financial_body(page))
    return "\n".join(piece for piece in pieces if piece)


def md_no_results_body(page) -> str:
    pieces = []
    try:
        pieces.append(page.locator("body").inner_text(timeout=5000))
    except Exception:
        pass
    for pattern in [
        r"No\s+results\s+found",
        r"\b0\s+records\b",
        r"You'?ve\s+reached\s+the\s+end\s+of\s+the\s+list",
    ]:
        try:
            page.get_by_text(re.compile(pattern, re.I)).last.scroll_into_view_if_needed(timeout=5000)
            page.locator("body").evaluate("window.scrollBy(0, -160)")
            time.sleep(1)
            break
        except Exception:
            continue
    try:
        pieces.append(page.locator("body").inner_text(timeout=5000))
        pieces.append(page.content())
    except Exception:
        pass
    return "\n".join(pieces)


def registry_page_body(page) -> str:
    pieces = []
    try:
        pieces.append(page.locator("body").inner_text(timeout=8000))
    except Exception:
        pass
    try:
        pieces.append(page.content())
    except Exception:
        pass
    return "\n".join(pieces)


def scroll_to_latest_year_evidence(page, state: str, body: str) -> bool:
    latest_year = latest_year_from_text(body, state)
    if latest_year is None:
        return False
    patterns = [
        rf"Accounting\s+Period\s+End\s+Date\s*:?\s*\d{{1,2}}[/-]\d{{1,2}}[/-]{latest_year}",
        rf"Period\s+End(?:ing)?\s*:?\s*\d{{1,2}}[/-]\d{{1,2}}[/-]{latest_year}",
        rf"Year\s+Represented\s*:?\s*{latest_year}",
        rf"\b{latest_year}\b",
    ]
    for pattern in patterns:
        try:
            page.get_by_text(re.compile(pattern, re.I)).last.scroll_into_view_if_needed(timeout=5000)
            page.locator("body").evaluate("window.scrollBy(0, -180)")
            time.sleep(1)
            return True
        except Exception:
            continue
    return False


def extract_ak_signature_date(pdf_text: str) -> str:
    match = re.search(r"Signature[\s\S]{0,800}?\bDate\s*:?\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})", pdf_text or "", re.I)
    return match.group(1).strip() if match else ""


def fetch_ak_registration_pdf(page, context, print_link: dict, org_name: str) -> tuple[str, str]:
    popup = None
    pdf_url = ""
    try:
        print_locator = page.locator("a[data-linkid^='Dq-t']").first
        try:
            with page.expect_download(timeout=12000) as download_info:
                print_locator.click(timeout=5000, force=True)
                page.keyboard.press("Enter")
            download = download_info.value
            path = ak_registration_pdf_path(org_name)
            path.parent.mkdir(parents=True, exist_ok=True)
            download.save_as(str(path))
            if PdfReader is not None:
                reader = PdfReader(path)
                pdf_text = "\n".join(pdf_page.extract_text() or "" for pdf_page in reader.pages)
                return pdf_text, download.url or ""
            return "", download.url or ""
        except Exception:
            pass
        try:
            with page.expect_popup(timeout=15000) as popup_info:
                try:
                    print_locator.click(timeout=5000, force=True)
                    page.keyboard.press("Enter")
                except Exception:
                    page.mouse.click(print_link["x"], print_link["y"])
                    page.keyboard.press("Enter")
            popup = popup_info.value
            popup.wait_for_load_state("domcontentloaded", timeout=20000)
            pdf_url = popup.url
            try:
                popup.keyboard.press("End")
                time.sleep(2)
                popup.mouse.wheel(0, 8000)
                time.sleep(2)
                popup.screenshot(path=str(evidence_png_path("AK", org_name)), full_page=False)
            except Exception:
                pass
        except Exception:
            page.mouse.click(print_link["x"], print_link["y"])
            time.sleep(5)
            pdf_url = page.url
            try:
                page.keyboard.press("End")
                time.sleep(2)
                page.mouse.wheel(0, 8000)
                time.sleep(2)
                page.screenshot(path=str(evidence_png_path("AK", org_name)), full_page=False)
            except Exception:
                pass
        if not pdf_url:
            return "", ""
        response = context.request.get(pdf_url, timeout=60000)
        pdf_bytes = response.body()
        if not pdf_bytes.startswith(b"%PDF"):
            return "", pdf_url
        path = ak_registration_pdf_path(org_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pdf_bytes)
        if PdfReader is None:
            return "", pdf_url
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pdf_text = "\n".join(pdf_page.extract_text() or "" for pdf_page in reader.pages)
        return pdf_text, pdf_url
    except Exception:
        return "", pdf_url
    finally:
        if popup:
            try:
                popup.close()
            except Exception:
                pass


def search_ak_with_registration_evidence(browser, org, artifact_name: str) -> tuple[object, str]:
    result = checker.StateResult(org.organization_name, org.ein, "AK", checker.STATUS_UNKNOWN, checker.AK_SEARCH_URL)
    if len(re.sub(r"\D", "", org.ein or "")) != 9:
        result.error = "AK search requires 9-digit EIN"
        return result, ""
    years_to_try = getattr(checker, "AK_YEARS_TO_TRY", [date.today().year, date.today().year - 1])
    for idx, year in enumerate(years_to_try):
        ak_context = browser.new_context(viewport={"width": 1365, "height": 900}, accept_downloads=True)
        ak_page = ak_context.new_page()
        try:
            if not checker.open_ak_public_search(ak_page):
                result.error = "Could not open Alaska Public Search form"
                return result, ""
            checker.fill_ak_search_form(ak_page, org, year)
            print_link = checker.find_ak_print_link(ak_page, org)
            if not print_link:
                if idx == len(years_to_try) - 1:
                    checker.save_artifacts(ak_page, ARTIFACTS_DIR, "AK", artifact_name)
                continue
            checker.save_artifacts(ak_page, ARTIFACTS_DIR, "AK", artifact_name)
            pdf_text, pdf_url = fetch_ak_registration_pdf(ak_page, ak_context, print_link, artifact_name)
            accounting_year_end = checker.extract_ak_accounting_end_year(pdf_text) if pdf_text else None
            result.status, result.raw_status_text, result.source_note = checker.classify_ak_registration_year(year, accounting_year_end)
            signature_date = extract_ak_signature_date(pdf_text)
            if signature_date:
                result.source_note = f"{result.source_note}; print registration signature date {signature_date}"
            if pdf_url:
                result.source_url = pdf_url
            result.success = True
            return result, "\n".join([registry_page_body(ak_page), pdf_text])
        except Exception as e:
            result.error = f"AK error: {e}"
            return result, ""
        finally:
            ak_context.close()
    checked_years = ", ".join(str(year) for year in years_to_try)
    result.raw_status_text = f"No Alaska registration found for checked years {checked_years}"
    result.status = "Not registered"
    result.source_note = f"No Alaska registration found in public search for years {checked_years}"
    result.success = True
    return result, ""


def ca_detail_body(page, org) -> str:
    pieces = [registry_page_body(page)]
    try:
        detail_links = page.locator('a[href*="Details.aspx"]')
        link_count = detail_links.count()
        target_href = ""
        ein_digits = re.sub(r"\D", "", org.ein or "")
        for i in range(min(link_count, 20)):
            link = detail_links.nth(i)
            try:
                row_text = ""
                row = link.locator("xpath=ancestor::tr[1]")
                if row.count():
                    row_text = row.first.inner_text(timeout=1500)
                href = link.get_attribute("href", timeout=1500) or ""
                if ein_digits and ein_digits in re.sub(r"\D", "", row_text):
                    target_href = href
                    break
                if not target_href:
                    target_href = href
            except Exception:
                continue
        if target_href:
            page.goto(urljoin(page.url, target_href), wait_until="domcontentloaded", timeout=45000)
            checker.safe_wait_for_network_idle(page, timeout=20000)
            time.sleep(2)
    except Exception:
        pass

    for text in ["Annual Renewal Data", "Renewal Data", "Annual Filings"]:
        try:
            page.get_by_text(re.compile(text, re.I)).first.scroll_into_view_if_needed(timeout=4000)
            page.locator("body").evaluate("window.scrollBy(0, -80)")
            time.sleep(1)
            break
        except Exception:
            continue
    try:
        current_body = registry_page_body(page)
        if not scroll_to_latest_year_evidence(page, "CA", current_body):
            page.locator("body").evaluate("window.scrollTo(0, Math.max(0, document.body.scrollHeight * 0.28))")
            time.sleep(1)
    except Exception:
        pass
    pieces.append(registry_page_body(page))
    return "\n".join(piece for piece in pieces if piece)


def me_detail_body(page, org) -> str:
    pieces = [registry_page_body(page)]
    target_name = getattr(checker, "normalize_name", lambda value: re.sub(r"\s+", " ", (value or "").lower()).strip())(
        org.organization_name
    )

    def current_text() -> str:
        try:
            return page.locator("body").inner_text(timeout=8000)
        except Exception:
            return ""

    def detail_visible(text: str) -> bool:
        return bool(
            re.search(r"\bLicense\s+Number\b", text, re.I)
            and re.search(r"\bStatus\b", text, re.I)
        )

    body_text = current_text()
    if not detail_visible(body_text):
        best_href = ""
        best_score = -1
        try:
            links = page.locator("a[href*='ShowDetail.aspx']")
            for i in range(min(links.count(), 80)):
                link = links.nth(i)
                try:
                    link_text = re.sub(r"\s+", " ", link.inner_text(timeout=1500)).strip()
                    link_name = getattr(checker, "normalize_name", lambda value: re.sub(r"\s+", " ", (value or "").lower()).strip())(
                        link_text
                    )
                    score = -1
                    if link_name == target_name:
                        score = 3
                    elif target_name and (target_name in link_name or link_name in target_name):
                        score = 2
                    elif link_text:
                        score = 1
                    if score > best_score:
                        best_score = score
                        best_href = (link.get_attribute("href") or "").strip()
                except Exception:
                    continue
        except Exception:
            pass
        if best_href:
            try:
                page.goto(urljoin(page.url, best_href), wait_until="domcontentloaded", timeout=60000)
                checker.safe_wait_for_network_idle(page, timeout=20000)
                time.sleep(2)
            except Exception:
                pass

    try:
        page.get_by_text(re.compile(r"License\s+Number|Expiration\s+Date|Status", re.I)).first.scroll_into_view_if_needed(timeout=5000)
        page.locator("body").evaluate("window.scrollBy(0, -160)")
        time.sleep(1)
    except Exception:
        try:
            page.locator("a[href*='ShowDetail.aspx']").first.scroll_into_view_if_needed(timeout=3000)
            page.locator("body").evaluate("window.scrollBy(0, -120)")
            time.sleep(1)
        except Exception:
            pass

    pieces.append(registry_page_body(page))
    return "\n".join(piece for piece in pieces if piece)


def hi_detail_body(page) -> str:
    pieces = [registry_page_body(page)]
    try:
        page.get_by_text(re.compile(r"\bDocuments\b", re.I)).first.scroll_into_view_if_needed(timeout=5000)
        page.locator("body").evaluate("window.scrollBy(0, -120)")
        time.sleep(1)
    except Exception:
        try:
            page.locator("body").evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)
        except Exception:
            pass
    pieces.append(registry_page_body(page))
    return "\n".join(piece for piece in pieces if piece)


def search_hi_precise(page, org):
    url = "https://charity.ehawaii.gov/charity/new-search.html"
    result = checker.StateResult(org.organization_name, org.ein, "HI", checker.STATUS_UNKNOWN, url)
    try:
        ein_digits = re.sub(r"\D", "", org.ein or "")
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        checker.safe_wait_for_network_idle(page, timeout=20000)
        time.sleep(3)
        try:
            page.locator("#nameFilter").select_option(label="Contains...")
        except Exception:
            pass
        name_input = checker.find_visible_input(page, ["#name", 'input[name="name"]', 'input[id="name"]'])
        fein_input = checker.find_visible_input(page, ["#fein", 'input[name="fein"]', 'input[id="fein"]'])
        if not name_input or not fein_input:
            result.error = "Could not find HI search fields"
            return result
        name_input.fill("")
        name_input.fill(org.organization_name)
        fein_input.fill("")
        if ein_digits:
            fein_input.fill(ein_digits)
        clicked = False
        for sel in ["#trigger-organization-search", 'button[id="trigger-organization-search"]', 'button[type="submit"]', "button"]:
            try:
                buttons = page.locator(sel)
                for i in range(min(buttons.count(), 10)):
                    button = buttons.nth(i)
                    try:
                        text = re.sub(r"\s+", " ", button.inner_text(timeout=1000)).strip()
                    except Exception:
                        text = (button.get_attribute("value") or "").strip()
                    if button.is_visible(timeout=750) and re.search(r"\bSearch\b", text, re.I):
                        button.click(timeout=5000)
                        clicked = True
                        break
                if clicked:
                    break
            except Exception:
                continue
        if not clicked:
            result.error = "Could not click HI Search button"
            return result
        checker.safe_wait_for_network_idle(page, timeout=30000)
        time.sleep(3)
        body = page.locator("body").inner_text(timeout=15000)
        if re.search(r"no results|no records|0 results|showing 0 to 0 of 0 entries|no data available in table|not registered in our system", body, re.I):
            result.raw_status_text = "No record found"
            result.status = "Not registered"
            result.source_note = "Hawaii search returned no matching organization result."
            result.success = True
            return result
        wanted = checker.normalize_name(org.organization_name)
        clicked_result = False
        for selector in ["#searchOrgTable tbody tr", "#searchResultTable tbody tr", "table tbody tr", "a[href]"]:
            try:
                rows = page.locator(selector)
                for i in range(min(rows.count(), 100)):
                    row = rows.nth(i)
                    try:
                        if not row.is_visible(timeout=750):
                            continue
                        row_text = re.sub(r"\s+", " ", row.inner_text(timeout=1500)).strip()
                        if not row_text or re.search(r"no data available", row_text, re.I):
                            continue
                        if ein_digits and ein_digits not in re.sub(r"\D", "", row_text) and wanted not in checker.normalize_name(row_text):
                            continue
                        links = row.locator("a[href]")
                        if selector == "a[href]":
                            row.click(timeout=5000)
                        elif links.count():
                            links.first.click(timeout=5000)
                        else:
                            row.click(timeout=5000)
                        clicked_result = True
                        break
                    except Exception:
                        continue
                if clicked_result:
                    break
            except Exception:
                continue
        if not clicked_result:
            result.raw_status_text = "No matching organization result"
            result.status = "Not registered"
            result.source_note = "Hawaii search results did not contain a matching organization row."
            result.success = True
            return result
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        checker.safe_wait_for_network_idle(page, timeout=20000)
        time.sleep(2)
        detail_text = page.locator("body").inner_text(timeout=12000)
        status_text = checker.extract_labeled_value(page, ["Registration Status", "Status"]) or checker.extract_labeled_value_from_text(detail_text, ["Registration Status", "Status"])
        result.raw_status_text = status_text
        result.status = status_text if status_text else checker.STATUS_UNKNOWN
        result.source_note = "Registration status and filings from Hawaii detail page."
        result.success = True
        return result
    except Exception as e:
        result.error = f"HI error: {e}"
        return result


def enrich_me_result_from_body(result, body: str) -> None:
    readable = html.unescape(re.sub(r"<[^>]+>", " ", body or ""))
    readable = re.sub(r"\s+", " ", readable).strip()
    if re.search(r"0 records found|no records|no results|no companies found|no data", readable, re.I):
        result.raw_status_text = "No record found"
        result.status = "Not Registered"
        result.source_note = "Maine search returned no matching organization result."
        result.error = ""
        result.success = True
        return

    status_text = ""
    if re.search(r"\bLicense\s+Number\b", readable, re.I):
        status_match = re.search(r"\bStatus\s*:?\s*([A-Za-z][A-Za-z /-]+?)\s+Expiration\s+Date\s*:?\s*([0-9/.-]+)", readable, re.I)
        if status_match:
            status_text = status_match.group(1).strip()
            expiration_text = status_match.group(2).strip()
        else:
            status_text = checker.extract_labeled_value_from_text(readable, ["Status", "Registration Status"])
            expiration_text = checker.extract_labeled_value_from_text(readable, ["Expiration Date", "Expiration"])
        if expiration_text and expiration_text not in status_text:
            status_text = f"{status_text}; expiration date {expiration_text}".strip("; ")
    if not status_text and re.search(r"\bCHARITABLE\s+ORGANIZATION\b[\s\S]{0,80}\bACTIVE\b", readable, re.I):
        status_text = "Active"
    if not status_text and re.search(r"\bACTIVE\b", readable, re.I) and re.search(r"ShowDetail\.aspx|Licensees|CHARITABLE", body or "", re.I):
        status_text = "Active"

    if status_text:
        result.raw_status_text = status_text
        result.status = status_text
        result.source_note = "Maine public registry record or search result status."
        result.error = ""
        result.success = True


def nj_detail_body(page, org) -> str:
    pieces = [registry_page_body(page)]
    ein_digits = re.sub(r"\D", "", org.ein or "")
    normalize_name = getattr(checker, "normalize_name", lambda value: re.sub(r"\s+", " ", (value or "").lower()).strip())
    wanted_name = normalize_name(org.organization_name)
    clicked = False

    for selector in ["button.ms-Link", "button[role='link']", "[data-automation-key='name'] button"]:
        try:
            buttons = page.locator(selector)
            for i in range(min(buttons.count(), 20)):
                button = buttons.nth(i)
                try:
                    row = button.locator("xpath=ancestor::*[@role='row'][1]")
                    row_text = re.sub(r"\s+", " ", row.inner_text(timeout=1500)).strip() if row.count() else ""
                    button_text = re.sub(r"\s+", " ", button.inner_text(timeout=1500)).strip()
                    haystack = f"{row_text} {button_text}"
                    if ein_digits not in re.sub(r"\D", "", haystack) and wanted_name not in normalize_name(haystack):
                        continue
                    button.click(timeout=5000)
                    clicked = True
                    break
                except Exception:
                    continue
            if clicked:
                break
        except Exception:
            continue

    for selector in ["tbody tr", "tr", "[role='row']", ".card", ".search-result", "a[href]"]:
        if clicked:
            break
        try:
            rows = page.locator(selector)
            for i in range(min(rows.count(), 80)):
                row = rows.nth(i)
                try:
                    if not row.is_visible(timeout=750):
                        continue
                    row_text = re.sub(r"\s+", " ", row.inner_text(timeout=1500)).strip()
                    row_digits = re.sub(r"\D", "", row_text)
                    row_name = normalize_name(row_text)
                    if ein_digits not in row_digits and wanted_name not in row_name:
                        continue
                    links = row.locator("a[href]")
                    if selector == "a[href]":
                        row.click(timeout=5000)
                    elif links.count():
                        links.first.click(timeout=5000)
                    else:
                        row.click(timeout=5000)
                    clicked = True
                    break
                except Exception:
                    continue
            if clicked:
                break
        except Exception:
            continue

    if clicked:
        try:
            checker.safe_wait_for_network_idle(page, timeout=20000)
        except Exception:
            pass
        time.sleep(3)
        for label in ["Filings", "Annual Filings", "Financial", "Documents", "View Details"]:
            try:
                page.get_by_text(re.compile(label, re.I)).first.click(timeout=3000)
                time.sleep(2)
                break
            except Exception:
                continue
        try:
            page.locator("body").evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)
        except Exception:
            pass
        for selector in ["[role='dialog']", ".ms-Dialog-main", ".ms-Modal-scrollableContent", ".ms-Panel-scrollableContent", ".modal-content"]:
            try:
                containers = page.locator(selector)
                for i in range(min(containers.count(), 5)):
                    container = containers.nth(i)
                    try:
                        if not container.is_visible(timeout=750):
                            continue
                        container.evaluate("el => { el.scrollTop = el.scrollHeight; }")
                        time.sleep(1)
                    except Exception:
                        continue
            except Exception:
                continue
        try:
            page.get_by_text(re.compile(r"20\d{2}|Filing|Annual|Renewal|Financial", re.I)).last.scroll_into_view_if_needed(timeout=5000)
            page.locator("body").evaluate("window.scrollBy(0, -140)")
            time.sleep(1)
        except Exception:
            pass
        pieces.append(registry_page_body(page))

    return "\n".join(piece for piece in pieces if piece)


def md_filing_context(result, body: str) -> dict:
    return filing_context(result, body)


def fiscal_year_end_from_body(body: str) -> tuple[int, int] | None:
    readable_body = html.unescape(re.sub(r"<[^>]+>", " ", body))
    patterns = [
        r"(?:Fiscal\s+Year\s+End|FYE|Fiscal\s+Period\s+End|Period\s+End(?:ing)?|End\s+Date)[\s\S]{0,140}?([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})",
        r"(?:Fiscal\s+Year\s+End|FYE|Fiscal\s+Period\s+End|Period\s+End(?:ing)?|End\s+Date)[\s\S]{0,140}?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"(?:Fiscal\s+Year\s+End|FYE|Fiscal\s+Period\s+End|Period\s+End(?:ing)?|End\s+Date)\s*:?\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})",
        r"(?:Fiscal\s+Year\s+End|FYE|Fiscal\s+Period\s+End|Period\s+End(?:ing)?|End\s+Date)\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s*(?:-|to|through)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"\b[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}\s*(?:-|to|through)\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, readable_body, re.I):
            parsed = parse_due_date(match.group(1))
            if parsed:
                return parsed.month, parsed.day
    return None


def combined_result_text(result, body: str) -> str:
    return " ".join([
        result.status or "",
        result.raw_status_text or "",
        result.source_note or "",
        result.error or "",
        body or "",
    ])


def indicates_exempt_registration(text: str) -> bool:
    return any(
        re.search(pattern, text or "", re.I)
        for pattern in [
            r"\bregistration\s+type\b[\s\S]{0,120}\bexempt\b",
            r"\bregistration\s+filing\s+status\b[\s\S]{0,160}\bexempt\b",
            r"\bexempt\s+registration\b",
            r"\bexempt\s+from\s+(charitable\s+|annual\s+)?registration\b",
        ]
    )


def md_detail_page_matched(result, text: str) -> bool:
    readable = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    readable = re.sub(r"\s+", " ", readable)
    if not re.search(r"SOS\s+Charity\s+Organization\s+Record|Charity\s+Name|Registration\s+Status", readable, re.I):
        return False
    if re.search(r"SoS\s+Charities\s+-\s+Public\s+Registry[\s\S]{0,600}No\s+results\s+found", readable, re.I):
        return False
    if re.search(r"SOS\s+Charity\s+Organization\s+Record\s+for", readable, re.I):
        return True
    ein_digits = re.sub(r"\D", "", result.ein or "")
    normalize = getattr(checker, "normalize_name", lambda value: re.sub(r"\s+", " ", (value or "").lower()).strip())
    name = normalize(result.organization_name)
    return bool(
        (ein_digits and ein_digits in re.sub(r"\D", "", readable))
        or (name and name in normalize(readable))
    )


def status_from_calendar_date(value: date) -> str:
    today = date.today()
    upcoming_cutoff = today + timedelta(days=183)
    if value < today:
        return "Delinquent"
    if value <= upcoming_cutoff:
        return "Upcoming Filing"
    return "Current"


def labeled_due_dates_from_text(text: str) -> list[date]:
    dates = []
    due_patterns = [
        r"(?:due date|renewal due|filing due|annual report due|registration expires|registration expiration|expiration date|expires on|expires)\s*:?\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})",
        r"(?:due date|renewal due|filing due|annual report due|registration expires|registration expiration|expiration date|expires on|expires)\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})",
    ]
    for pattern in due_patterns:
        for match in re.finditer(pattern, text or "", re.I):
            parsed = parse_due_date(match.group(1))
            if parsed:
                dates.append(parsed)
    return dates


def explicit_registry_date(result, body: str) -> date | None:
    text = combined_result_text(result, body)
    focused = " ".join([result.raw_status_text or "", result.source_note or ""])
    raw_date = parse_due_date(result.raw_status_text or "")
    if raw_date and re.fullmatch(r"\s*(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}-[A-Za-z]{3}-\d{2,4})\s*", result.raw_status_text or ""):
        return raw_date
    patterns = [
        rf"(?:expires|expiration date|registration expires|automatic extension)\s*:?\s*([A-Za-z]{{3,9}}\s+\d{{1,2}},\s+\d{{4}})",
        rf"(?:expires|expiration date|registration expires|automatic extension)\s*:?\s*(\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{4}})",
        r"^\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})\s*$",
    ]
    for source in [focused, text]:
        for pattern in patterns:
            for match in re.finditer(pattern, source or "", re.I):
                parsed = parse_due_date(match.group(1))
                if parsed:
                    return parsed
    return None


NO_ORGANIZATION_RECORD_PATTERN = (
    r"no matching|no match|no record found|no records found|no records|not found|"
    r"no results found|0 records|0 results|showing 0 to 0 of 0 entries|"
    r"no data available in table|not registered in our system"
)


def result_indicates_no_record(result) -> bool:
    return public_status(result) == "Not Registered" or bool(re.search(NO_ORGANIZATION_RECORD_PATTERN, " ".join([
        result.status or "",
        result.raw_status_text or "",
        result.source_note or "",
    ]), re.I))


def body_indicates_no_organization_record(body: str) -> bool:
    readable = html.unescape(re.sub(r"<[^>]+>", " ", body or ""))
    readable = re.sub(r"\s+", " ", readable)
    return bool(re.search(NO_ORGANIZATION_RECORD_PATTERN, readable, re.I))


def organization_record_confirmed(result, body: str) -> bool:
    if result_indicates_no_record(result):
        return False
    readable = html.unescape(re.sub(r"<[^>]+>", " ", body or ""))
    readable = re.sub(r"\s+", " ", readable)
    if not readable:
        return False
    ein_digits = re.sub(r"\D", "", result.ein or "")
    body_digits = re.sub(r"\D", "", readable)
    normalize = getattr(checker, "normalize_name", lambda value: re.sub(r"\s+", " ", (value or "").lower()).strip())
    name = normalize(result.organization_name)
    identity_seen = bool((ein_digits and ein_digits in body_digits) or (name and name in normalize(readable)))
    record_marker_seen = bool(re.search(
        r"AG\s+Account\s+Number|Tax\s+ID|Charity\s+Details|Charity\s+Name|Charity\s+EIN|"
        r"Registration\s+(?:Status|Number|Type)|Organization\s+ID|Organization\s+name|"
        r"Entity\s+Name|Certificate\s+#|Annual\s+Filing",
        readable,
        re.I,
    ))
    return identity_seen and record_marker_seen


def annual_filings_absent(text: str) -> bool:
    readable = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    readable = re.sub(r"\s+", " ", readable)
    annual_section_patterns = [
        r"Annual\s+filing\s+documents[\s\S]{0,500}?No\s+rows\s+available",
        r"Annual\s+filing\s+documents[\s\S]{0,500}?No\s+documents\s+found",
        r"Annual\s+filing\s+documents[\s\S]{0,500}?No\s+results\s+found",
        r"Annual\s+filings?(?:\s+and\s+documents)?[\s\S]{0,500}?No\s+rows\s+available",
        r"Annual\s+filings?(?:\s+and\s+documents)?[\s\S]{0,500}?No\s+documents\s+found",
        r"Annual\s+filings?(?:\s+and\s+documents)?[\s\S]{0,500}?No\s+results\s+found",
        r"Annual\s+renewal\s+data[\s\S]{0,500}?No\s+rows\s+available",
        r"Annual\s+renewal\s+data[\s\S]{0,500}?No\s+documents\s+found",
        r"Annual\s+renewal\s+data[\s\S]{0,500}?No\s+results\s+found",
    ]
    return any(re.search(pattern, readable, re.I) for pattern in annual_section_patterns)


def source_note_for_result(result) -> str:
    state = (result.state or "").upper()
    if state == "MA":
        return (
            "Massachusetts public portal exposes Annual Filings only. Fiscal year end is not always visible in the portal, "
            "so the filing year should be interpreted against the organization's confirmed fiscal year end and any applicable extension window."
        )
    return result.source_note or ""


def true_status_from_body(result, body: str) -> str:
    base_status = public_status(result)
    normalized = base_status.lower()
    state = (result.state or "").upper()
    combined = combined_result_text(result, body)
    combined_lower = combined.lower()

    if "site not reachable" in normalized:
        return base_status
    if (result.status or "").strip().lower() in {"closed", "inactive"} or (result.raw_status_text or "").strip().lower() in {"closed", "inactive"}:
        return "Delinquent"

    context = filing_context(result, body)
    due_date = context["due_date"]
    represented_year = context["represented_year"]
    registry_date = explicit_registry_date(result, body)
    use_registry_date = bool(
        registry_date
        and (
            state in {"AK", "CO", "PA", "VA"}
            or re.search(r"due date|next report|renewal|expiration|expires|automatic extension", " ".join([result.raw_status_text or "", result.source_note or ""]), re.I)
        )
    )

    if state == "MD" and md_detail_page_matched(result, combined):
        if stale_represented_year_is_delinquent(represented_year):
            return "Delinquent"
        if due_date and represented_year:
            return status_from_calendar_date(due_date)
        if re.search(r"Registration\s+Status\s+Current|Registration\s+Status[^A-Za-z0-9]{0,40}Current", combined, re.I):
            return "Current"

    record_confirmed = organization_record_confirmed(result, combined) or (state == "MD" and md_detail_page_matched(result, combined))

    if result_indicates_no_record(result):
        return "Not Registered"
    if indicates_exempt_registration(combined):
        return "Exempt"
    if annual_filings_absent(combined):
        return "Delinquent" if record_confirmed else "Not Registered"
    if body_indicates_no_organization_record(combined) and not record_confirmed:
        return "Not Registered"
    if record_confirmed and stale_represented_year_is_delinquent(represented_year):
        return "Delinquent"

    if use_registry_date:
        return status_from_calendar_date(registry_date)

    if state in EXTENSION_SCENARIO_STATES and due_date and represented_year and not result_indicates_no_record(result):
        return status_from_calendar_date(due_date)

    if "not registered" in normalized:
        return base_status
    if state == "PA" and re.search(r"no matching|no record|no result|not found|0 results", combined, re.I):
        return "Not Registered"

    if state == "MD" and re.search(r"Registration\s+Status\s+Current|Registration\s+Status[^A-Za-z0-9]{0,40}Current", combined, re.I):
        if due_date and represented_year:
            return status_from_calendar_date(due_date)
        return "Current"

    for due_date in labeled_due_dates_from_text(combined):
        return status_from_calendar_date(due_date)

    if due_date and represented_year:
        return status_from_calendar_date(due_date)

    if state == "NJ" and re.search(r"\b(compliant|current|active)\b", combined, re.I):
        return "Current"

    if "delinquent" in normalized or "non-compliant" in normalized:
        return "Delinquent"

    return "Current" if "current" in normalized else base_status


def md_status_from_body(result, body: str) -> str:
    return true_status_from_body(result, body)


def comments_for_result(result, body: str, public_facing_status: str) -> str:
    normalized_status = public_facing_status.lower()
    state = (result.state or "the selected state").upper()
    context = filing_context(result, body)
    if normalized_status == "site not reachable":
        technical_error = " ".join([result.error or "", result.source_note or "", result.raw_status_text or ""])
        if re.search(r"ERR_NAME_NOT_RESOLVED|remote name could not be resolved|getaddrinfo failed|Name or service not known", technical_error, re.I):
            return "Local DNS/network resolution failed while trying to reach the public registry host. This is usually a local network/DNS issue; rerun the snapshot after the connection stabilizes."
        if re.search(r"timed out|timeout", technical_error, re.I):
            return "The public registry did not respond before the lookup timed out. Rerun the snapshot to confirm whether this was temporary."
        return "Public registry site could not be reached at the time of the snapshot."
    if normalized_status == "not registered":
        return f"The {state} public registry was reachable, but no matching registration record was found for the organization/EIN searched."
    if normalized_status == "exempt":
        return f"The {state} public registry indicates the organization is exempt from charitable registration or annual filing requirements in that state."
    if normalized_status == "delinquent" and re.search(r"\b(closed|inactive)\b", " ".join([result.status or "", result.raw_status_text or ""]), re.I):
        return f"The {state} public registry shows a found organization record with a closed or inactive registration status."
    if normalized_status == "delinquent" and annual_filings_absent(combined_result_text(result, body)):
        return (
            f"The {state} public registry detail page shows the organization record, but the annual filing section shows no annual filings available "
            "and the snapshot does not show an exempt registration status."
        )
    if normalized_status == "delinquent" and stale_represented_year_is_delinquent(context.get("represented_year")) and not context.get("due_date"):
        return (
            f"The {state} public registry detail page shows the organization record and the most recent fiscal/filing year identified is "
            f"{context.get('represented_year')}. The available snapshot did not provide enough fiscal year-end information to calculate a precise due date, "
            "but the filing record appears more than one annual cycle behind."
        )
    registry_date = explicit_registry_date(result, body)
    use_registry_date = bool(
        registry_date
        and (
            state in {"AK", "CO", "PA", "VA"}
            or re.search(r"due date|next report|renewal|expiration|expires|automatic extension", " ".join([result.raw_status_text or "", result.source_note or ""]), re.I)
        )
    )
    if use_registry_date and normalized_status in {"upcoming filing", "current", "delinquent"}:
        descriptor = "expiration or renewal date"
        if state == "AK":
            descriptor = "registration expiration date"
        elif state == "VA":
            descriptor = "registration expiration date"
        elif state == "PA":
            descriptor = "expiration date"
        elif re.search(r"due date|next report", result.source_note or "", re.I):
            descriptor = "due date"
        article = "an" if descriptor[0].lower() in "aeiou" else "a"
        if normalized_status == "upcoming filing":
            return f"The {state} public registry shows {article} {descriptor} of {format_date(registry_date)}, which is within 6 months."
        if normalized_status == "current":
            return f"The {state} public registry shows {article} {descriptor} of {format_date(registry_date)}, which is not within the next 6 months."
        return f"The {state} public registry shows {article} {descriptor} of {format_date(registry_date)}, which is overdue."
    labeled_dates = [] if state == "CA" else labeled_due_dates_from_text(combined_result_text(result, body))
    if labeled_dates and normalized_status in {"upcoming filing", "current", "delinquent"}:
        due_date = labeled_dates[0]
        if normalized_status == "upcoming filing":
            return f"The {state} public registry shows a due or expiration date of {format_date(due_date)}, which is within 6 months."
        if normalized_status == "current":
            return f"The {state} public registry shows a due or expiration date of {format_date(due_date)}, which is not within the next 6 months."
        return f"The {state} public registry shows a due or expiration date of {format_date(due_date)}, which is overdue."
    if result.state in SUPPORTED_STATES:
        if context.get("due_date"):
            if context.get("uses_extension_scenario"):
                base_due = context.get("base_due_date")
                extended_due = context.get("extended_due_date")
                base_status = status_from_calendar_date(base_due) if base_due else "Unknown"
                extended_status = status_from_calendar_date(extended_due) if extended_due else public_facing_status
                filing_name = "annual filing"
                if state == "MA":
                    filing_name = "Form PC"
                elif state == "NY":
                    filing_name = "CHAR500 annual filing"
                elif state == "PA":
                    filing_name = "annual renewal"
                if state == "MD":
                    extension_label = "Maryland automatic extension"
                elif state == "MA":
                    extension_label = "Massachusetts six-month extension"
                else:
                    extension_label = "six-month extension"
                status_sentence = (
                    f"CE Status is {base_status} based on the base due date. "
                    f"If the {extension_label} was granted, the extended deadline would be {format_date(extended_due)} and the status would be {extended_status}."
                )
                return (
                    f"{context['represented_year']} appears to be the most recent {state} filing year identified in the instant compliance snapshot. "
                    f"Based on a {context['fiscal_end'][0]}/{context['fiscal_end'][1]} fiscal year end, the {context['next_report_year']} {filing_name} base due date is {format_date(base_due)}. "
                    f"{status_sentence}"
                )
            if state == "MA":
                fiscal_end = context["fiscal_end"]
                report_year = context["next_report_year"]
                fy_end = date(report_year, fiscal_end[0], fiscal_end[1])
                base_due = fifteenth_day_after_fiscal_year_end(fy_end, 5)
                extended_due = add_months(base_due, 6)
                return (
                    f"{context['represented_year']} Form PC appears to be the most recent annual charity filing on record. "
                    f"Based on a {fiscal_end[0]}/{fiscal_end[1]} fiscal year end, the {report_year} Form PC base due date is {format_date(base_due)}. "
                    f"If the organization remains registered and in compliance, Massachusetts generally allows a 6 month extension, "
                    f"making the extended deadline {format_date(extended_due)}."
                )
            if state == "NY":
                fiscal_end = context["fiscal_end"]
                report_year = context["next_report_year"]
                fy_end = date(report_year, fiscal_end[0], fiscal_end[1])
                base_due = fifteenth_day_after_fiscal_year_end(fy_end, 5)
                extended_due = add_months(base_due, 6)
                return (
                    f"{context['represented_year']} appears to be the most recent New York annual filing on record. "
                    f"Based on a {fiscal_end[0]}/{fiscal_end[1]} fiscal year end, the {report_year} CHAR500 annual filing base due date is {format_date(base_due)}. "
                    f"If an extension applies, the extended deadline is approximately {format_date(extended_due)}."
                )
            return context["comment"]
    if normalized_status == "upcoming filing":
        return "A filing or renewal appears to be due soon based on the instant compliance snapshot."
    if normalized_status == "current":
        return "No delinquency was identified in the instant compliance snapshot."
    if "delinquent" in normalized_status or "non-compliant" in normalized_status:
        return "The instant compliance snapshot indicates a delinquency."
    return "Review the instant compliance snapshot for additional details."


def run_state_lookup(organization_name: str, ein: str, state: str) -> dict:
    artifact_name = organization_name or f"EIN {format_ein(ein)}"
    lookup_name = "" if state == "NY" else organization_name
    org = checker.Organization(organization_name=lookup_name, ein=ein)
    body = ""
    proof_url = None

    with checker.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = None
        page = None
        try:
            if state == "AK":
                result, body = search_ak_with_registration_evidence(browser, org, artifact_name)
                proof_url = screenshot_to_pdf(state, artifact_name)
            else:
                context = browser.new_context()
                page = context.new_page()
            if state == "AK":
                pass
            elif state == "CA":
                result = checker.search_ca(page, org)
                if public_status(result) != "Not Registered":
                    body = ca_detail_body(page, org)
            elif state == "MA":
                result = checker.search_ma(page, org)
            elif state == "MD":
                result = checker.search_md(page, org)
                md_body = registry_page_body(page)
                if md_detail_page_matched(result, md_body):
                    result.status = result.raw_status_text if result.raw_status_text and result.raw_status_text != "No matching EIN result" else checker.STATUS_UNKNOWN
                    result.raw_status_text = result.raw_status_text if result.raw_status_text != "No matching EIN result" else "Maryland detail record found"
                    result.source_note = "Maryland detail page was reached from the public registry search."
                    result.success = True
                    body = md_detail_body(page)
                elif public_status(result) != "Not Registered":
                    body = md_detail_body(page)
                else:
                    body = md_no_results_body(page)
            elif state == "CO":
                result = checker.search_co(page, org)
            elif state == "NY":
                result = checker.search_ny(page, org)
            elif state == "NJ":
                result = checker.search_nj(page, org)
                if public_status(result) != "Not Registered":
                    body = nj_detail_body(page, org)
            elif state == "PA":
                result = checker.search_pa(page, org)
            elif state == "VA":
                result = checker.search_va(page, org)
            elif state == "SC":
                result = checker.search_sc(page, org)
            elif state == "HI":
                result = search_hi_precise(page, org)
                if public_status(result) != "Not Registered":
                    body = hi_detail_body(page)
            elif state == "ME":
                result = checker.search_me(page, org)
                body = me_detail_body(page, org)
                enrich_me_result_from_body(result, body)
            elif state == "ND":
                result = checker.search_nd(page, org)
            else:
                raise ValueError(f"Unsupported state: {state}")
            if page:
                if not body:
                    body = registry_page_body(page)
                checker.save_artifacts(
                    page,
                    ARTIFACTS_DIR,
                    state,
                    artifact_name,
                )
                if state in {"CA", "MD", "ME"}:
                    save_focused_viewport_artifact(page, state, artifact_name)
                proof_url = screenshot_to_pdf(state, artifact_name)
        finally:
            if context:
                context.close()
            browser.close()

    result.source_note = source_note_for_result(result)
    data = checker.asdict(result)
    if organization_name:
        data["organization_name"] = organization_name
        result.organization_name = organization_name
    elif not (data.get("organization_name") or "").strip():
        data["organization_name"] = "Organization not identified"
        result.organization_name = data["organization_name"]
    data["status"] = true_status_from_body(result, body)
    data["comments"] = comments_for_result(result, body, data["status"])
    proof_url = screenshot_to_pdf(state, artifact_name, result, body, data["status"], data["comments"]) or proof_url
    if proof_url:
        data["evidence_url"] = proof_url
    data["checked_at_epoch"] = int(time.time())
    data["app_version"] = APP_VERSION
    return data


def normalize_organization_requests(payload: dict, privileged: bool) -> list[dict]:
    organization_name = (payload.get("organization_name") or "").strip()
    raw_organizations = payload.get("organizations")
    organizations = []

    if isinstance(raw_organizations, list):
        for item in raw_organizations:
            if not isinstance(item, dict):
                continue
            ein = format_ein(item.get("ein") or "")
            if len(re.sub(r"\D", "", ein)) != 9:
                continue
            name = resolved_organization_name(ein, item.get("organization_name") or organization_name)
            organizations.append({"organization_name": name, "ein": ein})
    else:
        ein = format_ein(payload.get("ein") or "")
        if len(re.sub(r"\D", "", ein)) == 9:
            name = resolved_organization_name(ein, organization_name)
            organizations.append({"organization_name": name, "ein": ein})

    deduped = []
    seen = set()
    for org in organizations:
        key = re.sub(r"\D", "", org["ein"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(org)
    return deduped


class RegistrySnapshotHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self._send_json(200, {"ok": True})

    def _send_evidence_pdf(self, include_body: bool = True) -> bool:
        if not self.path.startswith("/evidence/"):
            return False

        try:
            relative_path = unquote(self.path.removeprefix("/evidence/"))
            candidate = (ARTIFACTS_DIR / relative_path).resolve()
            artifacts_root = ARTIFACTS_DIR.resolve()
            if artifacts_root not in candidate.parents or candidate.suffix.lower() != ".pdf" or not candidate.exists():
                self._send_json(404, {"error": "Evidence PDF not found."})
                return True
            body = candidate.read_bytes()
            start = 0
            end = len(body) - 1
            range_header = self.headers.get("Range", "")
            if range_header.startswith("bytes="):
                requested = range_header.removeprefix("bytes=").split("-", 1)
                try:
                    if requested[0]:
                        start = int(requested[0])
                    if len(requested) > 1 and requested[1]:
                        end = int(requested[1])
                except ValueError:
                    start = 0
                    end = len(body) - 1
                start = max(0, min(start, len(body) - 1))
                end = max(start, min(end, len(body) - 1))
                chunk = body[start:end + 1]
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(body)}")
            else:
                chunk = body
                self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Disposition", f'inline; filename="{candidate.name}"')
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(chunk)))
            self.end_headers()
            if include_body:
                self.wfile.write(chunk)
            return True
        except BrokenPipeError:
            return True
        except BaseException as exc:
            log_error(f"Evidence PDF response failed: {exc}")
            self._send_json(500, {"error": "Evidence PDF could not be served."})
            return True

    def _send_lead_log(self, include_body: bool = True) -> bool:
        parsed = urlparse(self.path)
        if parsed.path != "/admin/leads.csv":
            return False

        query = parse_qs(parsed.query)
        email = normalize_email((query.get("email") or [""])[0])
        passcode = (query.get("passcode") or [""])[0]
        if not is_verified_internal_passcode(email, passcode):
            self._send_json(403, {"error": "Verified Compliance Express email required."})
            return True

        if LEAD_LOG_PATH.exists():
            body = LEAD_LOG_PATH.read_bytes()
        else:
            body = b"checked_at,email,domain,organization_name,ein,state,status,comments,evidence_url,source_url\r\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="registry_snapshot_leads.csv"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)
        return True

    def do_HEAD(self) -> None:
        if self._send_lead_log(include_body=False):
            return

        if self._send_evidence_pdf(include_body=False):
            return

        if self.path in {"/", "/registry-snapshot", "/registry-snapshot/", "/api/check"}:
            page_path = Path(__file__).with_name("registry-snapshot-index.html")
            body = page_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return

        self._send_json(404, {"error": "Open http://127.0.0.1:8765/ to use the registry snapshot page."})

    def do_GET(self) -> None:
        if self._send_lead_log(include_body=True):
            return

        if self._send_evidence_pdf(include_body=True):
            return

        if self.path in {"/", "/registry-snapshot", "/registry-snapshot/", "/api/check"}:
            page_path = Path(__file__).with_name("registry-snapshot-index.html")
            body = page_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self._send_json(404, {"error": "Open http://127.0.0.1:8765/ to use the registry snapshot page."})

    def do_POST(self) -> None:
        if self.path != "/api/check":
            self._send_json(404, {"error": "Not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            email = normalize_email(payload.get("email") or "")

            requested_states = payload.get("states")
            state = (payload.get("state") or "").strip().upper()
            domain = email_domain(email)
            admin_passcode = (payload.get("admin_passcode") or "").strip()
            if is_exempt_domain(domain) and admin_passcode != ADMIN_PASSCODE:
                self._send_json(401, {"error": "Enter the Compliance Express passcode to use internal features."})
                return
            privileged = is_privileged_request(email, domain)
            organizations = normalize_organization_requests(payload, privileged)

            if isinstance(requested_states, list):
                states = []
                for item in requested_states:
                    state_code = str(item or "").strip().upper()
                    if state_code and state_code not in states:
                        states.append(state_code)
            else:
                states = [state] if state else []
            states = sorted(states)

            if not organizations or not states or any(st not in set(SUPPORTED_STATES) for st in states):
                self._send_json(400, {"error": f"Enter a valid 9-digit EIN and select 1 to {MAX_STATES_PER_SNAPSHOT} supported states."})
                return

            state_limit = state_limit_for_request(domain)
            org_limit = org_limit_for_request(email, domain)
            if len(states) > state_limit:
                self._send_json(400, {"error": f"Select up to {state_limit} states."})
                return
            if len(organizations) > org_limit:
                self._send_json(400, {"error": f"This email can submit up to {org_limit} organization{'s' if org_limit != 1 else ''} at a time."})
                return

            is_batch = isinstance(requested_states, list)
            if is_batch and not privileged and domain_is_limited(domain):
                self._send_json(429, {"error": "A complimentary snapshot was already requested for this email domain."})
                return

            results = [
                run_state_lookup(org["organization_name"], org["ein"], st)
                for org in organizations
                for st in states
            ]
            append_lead_log(email, results)
            if is_batch:
                if not privileged:
                    record_domain_check(domain)
                self._send_json(200, {"results": results, "checked_at_epoch": int(time.time())})
            else:
                self._send_json(200, results[0])
        except BaseException as exc:
            log_error(f"POST /api/check failed: {exc}")
            self._send_json(500, {"error": str(exc)})

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), RegistrySnapshotHandler)
    print(f"Registry snapshot server running at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
