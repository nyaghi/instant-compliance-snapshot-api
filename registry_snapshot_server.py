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
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse
import urllib.request

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")

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
PORT = int(os.environ.get("PORT", "8765"))
HOST = os.environ.get("HOST") or ("0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
PUBLIC_BASE_URL = (os.environ.get("PUBLIC_BASE_URL", f"http://127.0.0.1:{PORT}").splitlines()[0]).strip().rstrip("/")
APP_VERSION = "2026.05.07.1"
SUPPORTED_STATES = ["AK", "CA", "CO", "HI", "MA", "MD", "ME", "ND", "NJ", "NY", "PA", "SC", "VA"]
EXTENSION_SCENARIO_STATES = {"CA", "CT", "HI", "KY", "MA", "MD", "NJ", "NY", "OH", "PA"}
MAX_STATES_PER_SNAPSHOT = len(SUPPORTED_STATES)

# Emergency-only override hook. Routine corrections must be implemented as
# generalized lookup/status rules, not EIN-specific adjudications.
ADJUDICATED_STATUS_OVERRIDES = {}
REQUESTED_PARALLEL_LOOKUPS = max(1, int(os.environ.get("CE_MAX_PARALLEL_LOOKUPS", "1")))
ALLOW_PARALLEL_BROWSER_LOOKUPS = os.environ.get("CE_ALLOW_PARALLEL_BROWSER_LOOKUPS", "1").strip().lower() in {"1", "true", "yes"}
MAX_BROWSER_LOOKUPS = max(1, int(os.environ.get("CE_MAX_BROWSER_LOOKUPS", "2")))
MAX_PARALLEL_LOOKUPS = min(REQUESTED_PARALLEL_LOOKUPS, MAX_BROWSER_LOOKUPS) if ALLOW_PARALLEL_BROWSER_LOOKUPS else 1
BLOCK_HEAVY_BROWSER_RESOURCES = os.environ.get("CE_BLOCK_HEAVY_BROWSER_RESOURCES", "1").strip().lower() not in {"0", "false", "no"}
EAGER_EVIDENCE_PDF = os.environ.get("CE_EAGER_EVIDENCE_PDF", "0").strip().lower() in {"1", "true", "yes"}
CAPTURE_EVIDENCE_SCREENSHOTS = os.environ.get("CE_CAPTURE_EVIDENCE_SCREENSHOTS", "0").strip().lower() in {"1", "true", "yes"}
CAPTURE_LIGHTWEIGHT_SOURCE_SNAPSHOT = os.environ.get("CE_CAPTURE_LIGHTWEIGHT_SOURCE_SNAPSHOT", "0").strip().lower() in {"1", "true", "yes"}
ON_DEMAND_EVIDENCE_SCREENSHOT = os.environ.get("CE_ON_DEMAND_EVIDENCE_SCREENSHOT", "1").strip().lower() not in {"0", "false", "no"}
MAX_EXTERNAL_EXEMPT_ORGS = 3
DOMAIN_LIMIT_DAYS = 7
ADMIN_PASSCODE = "8977"
PIN_EXPIRY_SECONDS = 10 * 60
PIN_MAX_ATTEMPTS = 5
VERIFICATION_TOKEN_SECONDS = 60 * 60
EXEMPT_EMAIL_DOMAIN = "compliance-express.com"
EXEMPT_EMAIL_ADDRESSES = {"nyaghi17@gmail.com"}
DOMAIN_LIMIT_PATH = Path(__file__).with_name("registry_snapshot_domain_limits.json")
DEVICE_LIMIT_PATH = Path(__file__).with_name("registry_snapshot_device_limits.json")
PIN_STORE: dict[str, dict] = {}
VERIFICATION_TOKENS: dict[str, dict] = {}
ORG_NAME_CACHE: dict[str, str] = {}
PUBLIC_PROFILE_CACHE: dict[str, dict] = {}
FISCAL_YEAR_END_OVERRIDES = {
    "208428450": (6, 30),
    "546053660": (6, 30),
    "362883000": (3, 31),
    "237222333": (6, 30),
    "141707425": (3, 31),
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


def evidence_metadata_path(state: str, org_name: str) -> Path:
    return ARTIFACTS_DIR / state.upper() / f"{artifact_safe_name(org_name)}.evidence.json"


def ak_registration_pdf_path(org_name: str) -> Path:
    return ARTIFACTS_DIR / "AK" / f"{artifact_safe_name(org_name)}_registration.pdf"


def evidence_url(state: str, org_name: str, ein: str = "") -> str:
    url = f"{PUBLIC_BASE_URL}/evidence/{state.upper()}/{artifact_safe_name(org_name)}.pdf"
    query = []
    if ein:
        query.append(f"ein={quote(format_ein(ein), safe='')}")
    if org_name:
        query.append(f"org={quote(org_name, safe='')}")
    return f"{url}?{'&'.join(query)}" if query else url


def configure_browser_context(context) -> None:
    if not BLOCK_HEAVY_BROWSER_RESOURCES:
        return

    def route_handler(route):
        try:
            if route.request.resource_type in {"image", "media", "font"}:
                route.abort()
                return
        except Exception:
            pass
        route.continue_()

    try:
        context.route("**/*", route_handler)
    except Exception:
        pass


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
    width = 1700
    title_font = load_font(76, bold=True)
    ribbon_font = load_font(42, bold=True)
    section_font = load_font(42, bold=True)
    label_font = load_font(28, bold=True)
    text_font = load_font(34)
    small_font = load_font(27)
    navy = "#0B2A5B"
    red = "#C62828"
    slate = "#334155"
    muted = "#64748B"
    border = "#CBD5E1"
    light = "#F8FAFC"
    pale_blue = "#EEF6FF"

    scratch = Image.new("RGB", (width, 2600), "white")
    draw = ImageDraw.Draw(scratch)

    try:
        context = filing_context(result, body)
    except Exception as exc:
        log_error(f"Could not build filing context for evidence summary: {exc}")
        context = {}
    fiscal_end = context.get("fiscal_end")
    fiscal_end_text = f"{fiscal_end[0]}/{fiscal_end[1]}" if fiscal_end else "Not identified"
    due_date = context.get("due_date")
    base_due = context.get("base_due_date")
    extended_due = context.get("extended_due_date")
    rows = [
        ("Organization", result.organization_name),
        ("EIN", result.ein),
        ("State", result.state),
        ("Interpreted CE Status", status),
        ("CE Comment", comments),
        ("Most Recent Fiscal/Filing Year Read", context.get("represented_year") or "Not identified"),
        ("Fiscal Year End Used", fiscal_end_text),
        ("Base Due Date Used", format_date(base_due or due_date) if (base_due or due_date) else "Not identified"),
        ("Extension Date Scenario", format_date(extended_due) if extended_due else "Not applicable or not identified"),
        ("Raw Registry Status", result.raw_status_text or "Not shown"),
        ("Source Note", result.source_note or "Not provided"),
        ("Source URL", result.source_url),
    ]

    def clamp_lines(lines: list[str], max_lines: int) -> list[str]:
        if len(lines) <= max_lines:
            return lines
        clipped = lines[:max_lines]
        clipped[-1] = clipped[-1].rstrip(" .,:;") + "..."
        return clipped

    wrapped_rows = []
    x_value = 730
    value_width = width - x_value - 130
    for label, value in rows:
        lines = wrap_text(draw, str(value), text_font, value_width)
        max_lines = 10 if label == "CE Comment" else 4 if label in {"Source URL", "Source Note"} else 3
        wrapped_rows.append((label, clamp_lines(lines, max_lines)))

    row_heights = [max(112, 72 + (len(lines) * 46)) for _, lines in wrapped_rows]
    divider_gaps = 20 * max(0, len(row_heights) - 1)
    height = 500 + sum(row_heights) + divider_gaps + 240
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    y = 60
    draw.rounded_rectangle((60, y, width - 60, y + 230), radius=34, fill=pale_blue, outline=border, width=3)
    draw.text((105, y + 40), "Compliance", fill=navy, font=title_font)
    draw.text((520, y + 40), "Express", fill=red, font=title_font)
    draw.rounded_rectangle((105, y + 140, 855, y + 215), radius=0, fill=red, outline="#7F1D1D", width=3)
    draw.text((135, y + 158), "INSTANT COMPLIANCE SNAPSHOT", fill="white", font=ribbon_font)
    y += 280

    draw.text((80, y), "Status Basis", fill=navy, font=section_font)
    draw.text((80, y + 54), "Prepared from public registry information available at the time of lookup.", fill=muted, font=small_font)
    draw.line((80, y + 104, width - 80, y + 104), fill=red, width=6)
    y += 150

    card_top = y
    card_height = 74 + sum(row_heights) + divider_gaps
    draw.rounded_rectangle((70, card_top, width - 70, card_top + card_height), radius=28, fill=light, outline=border, width=3)
    y += 38
    for index, ((label, lines), row_height) in enumerate(zip(wrapped_rows, row_heights)):
        if index:
            draw.line((105, y, width - 105, y), fill="#E2E8F0", width=2)
            y += 20
        draw.text((110, y), label.upper(), fill=red, font=label_font)
        value_y = y
        for line in lines:
            draw.text((x_value, value_y), line, fill=slate, font=text_font)
            value_y += 46
        y += row_height

    footer_y = card_top + card_height + 46
    draw.text((90, footer_y), "Supporting Registry View", fill=navy, font=section_font)
    draw.text((90, footer_y + 56), "A source screenshot follows when available. This snapshot is informational and is not legal advice.", fill=slate, font=small_font)
    return image


def screenshot_to_pdf(state: str, org_name: str, result=None, body: str = "", status: str = "", comments: str = "") -> str | None:
    png_path = evidence_png_path(state, org_name)
    pdf_path = evidence_pdf_path(state, org_name)
    if not png_path.exists() and result is None:
        return None

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    output_buffer = io.BytesIO()
    append_images = []
    if png_path.exists():
        with Image.open(png_path) as image:
            if image.mode in {"RGBA", "P"}:
                image = image.convert("RGB")
            if image.width > 1400:
                ratio = 1400 / image.width
                image = image.resize((1400, max(1, int(image.height * ratio))), Image.Resampling.LANCZOS)
            append_images.append(image.copy())

    if result is not None:
        summary = evidence_summary_image(result, body, status, comments)
        summary.save(output_buffer, "PDF", resolution=144.0, save_all=True, append_images=append_images)
    elif append_images:
        append_images[0].save(output_buffer, "PDF", resolution=144.0, save_all=True, append_images=append_images[1:])
    else:
        return None

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
    return evidence_url(state, org_name, getattr(result, "ein", "") if result is not None else "")


def write_evidence_metadata(state: str, org_name: str, result_data: dict, body: str, status: str, comments: str) -> None:
    metadata_path = evidence_metadata_path(state, org_name)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    safe_result = {
        key: value
        for key, value in result_data.items()
        if value is None or isinstance(value, (str, int, float, bool))
    }
    metadata = {
        "state": state.upper(),
        "org_name": org_name,
        "result": safe_result,
        "body": body,
        "status": status,
        "comments": comments,
        "created_at_epoch": int(time.time()),
    }
    try:
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    except Exception as exc:
        log_error(f"Could not write evidence metadata for {state} / {org_name}: {exc}")


def prepare_evidence_pdf(candidate: Path) -> bool:
    try:
        relative = candidate.relative_to(ARTIFACTS_DIR.resolve())
    except ValueError:
        return False
    if len(relative.parts) < 2:
        return False
    state = relative.parts[0].upper()
    org_name = candidate.stem
    metadata_path = candidate.with_suffix(".evidence.json")
    if not metadata_path.exists():
        return False
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        result_data = metadata.get("result") or {}
        result = SimpleNamespace(**result_data)
        if not getattr(result, "state", ""):
            result.state = state
        if not getattr(result, "organization_name", ""):
            result.organization_name = metadata.get("org_name") or org_name
        if not getattr(result, "ein", ""):
            result.ein = result_data.get("ein", "")
        if not getattr(result, "source_url", ""):
            result.source_url = result_data.get("source_url", "")
        if (
            ON_DEMAND_EVIDENCE_SCREENSHOT
            and not evidence_png_path(state, org_name).exists()
            and getattr(result, "ein", "")
        ):
            try:
                refreshed = run_state_lookup(
                    getattr(result, "organization_name", "") or metadata.get("org_name") or org_name,
                    getattr(result, "ein", ""),
                    state,
                    capture_source_snapshot=True,
                )
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                result_data = metadata.get("result") or refreshed or result_data
                result = SimpleNamespace(**result_data)
                if not getattr(result, "state", ""):
                    result.state = state
                if not getattr(result, "organization_name", ""):
                    result.organization_name = metadata.get("org_name") or org_name
            except Exception as exc:
                log_error(f"Could not capture on-demand source screenshot for {state} / {org_name}: {exc}")
        screenshot_to_pdf(
            state,
            org_name,
            result,
            metadata.get("body") or "",
            metadata.get("status") or result_data.get("status") or "",
            metadata.get("comments") or result_data.get("comments") or "",
        )
        return candidate.exists()
    except Exception as exc:
        log_error(f"Could not prepare lazy evidence PDF {candidate}: {exc}")
        return False


def focus_md_evidence_view(page) -> None:
    for label in ["Financial Information", "Financial Informati"]:
        try:
            page.get_by_role("button", name=re.compile(label, re.I)).click(timeout=5000)
            time.sleep(1)
            break
        except Exception:
            continue
    for pattern in [
        r"Year\s+Represented",
        r"Most\s+Recent\s+Fiscal\s+Year",
        r"Total\s+Charitable\s+Contributions",
        r"Registration\s+Status",
        r"SOS\s+Charity\s+Organization\s+Record",
    ]:
        try:
            page.get_by_text(re.compile(pattern, re.I)).first.scroll_into_view_if_needed(timeout=5000)
            page.locator("body").evaluate("window.scrollBy(0, -170)")
            time.sleep(1)
            return
        except Exception:
            continue


def save_focused_viewport_artifact(page, state: str, org_name: str) -> None:
    state_dir = ARTIFACTS_DIR / state.upper()
    state_dir.mkdir(parents=True, exist_ok=True)
    safe_name = artifact_safe_name(org_name)
    try:
        (state_dir / f"{safe_name}.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
    try:
        if state.upper() == "MD":
            focus_md_evidence_view(page)
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


def log_event(message: str) -> None:
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")


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
    if is_exempt_domain(domain):
        return MAX_STATES_PER_SNAPSHOT
    return 1


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


def load_device_limits() -> dict:
    if not DEVICE_LIMIT_PATH.exists():
        return {}
    try:
        return json.loads(DEVICE_LIMIT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_device_limits(limits: dict) -> None:
    DEVICE_LIMIT_PATH.write_text(json.dumps(limits, indent=2, sort_keys=True), encoding="utf-8")


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


def normalize_device_id(device_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]", "", (device_id or "").strip())[:120]


def device_is_limited(device_id: str) -> bool:
    device_id = normalize_device_id(device_id)
    if not device_id:
        return False
    limits = load_device_limits()
    prior = int(limits.get(device_id, 0) or 0)
    if not prior:
        return False
    return int(time.time()) - prior < DOMAIN_LIMIT_DAYS * 24 * 60 * 60


def record_device_check(device_id: str) -> None:
    device_id = normalize_device_id(device_id)
    if not device_id:
        return
    limits = load_device_limits()
    limits[device_id] = int(time.time())
    save_device_limits(limits)


def should_record_domain_check(results: list[dict]) -> bool:
    if not results:
        return False
    return any((result.get("status") or "").strip().lower() != "site not reachable" for result in results)


def public_status(result) -> str:
    status = (result.status or "").strip()
    error = (result.error or "").strip().lower()

    if error:
        return "Site Not Reachable"

    normalized = status.lower()
    if normalized == "unknown":
        no_record_text = " ".join([
            result.raw_status_text or "",
            result.source_note or "",
        ])
        if re.search(r"no matching|no record|not found|no results|0 records|0 results", no_record_text, re.I):
            return "Not Registered"
        return "Unknown" if result.success else "Site Not Reachable"
    if normalized in {"not registered", "not found", "no record", "no record found"}:
        return "Not Registered"
    if "exempt" in normalized:
        return "Exempt"
    if "revoked" in normalized:
        return "Revoked"
    if "suspended" in normalized:
        return "Suspended"
    if re.search(r"\bpending\b", normalized, re.I):
        return "Pending"
    if re.search(r"\bfailed\s+to\s+renew\b", normalized, re.I):
        return "Failed to Renew"
    if re.search(r"not\s+authorized\s+to\s+solicit|may\s+not\s+(?:solicit|raise\s+funds|operate)|cease\s+and\s+desist", normalized, re.I):
        return "Suspended"
    if re.search(r"\b(withdrawn|retired|terminated|cancelled|canceled|voluntar(?:y|ily)\s+deactivat(?:ed|ion))\b", normalized, re.I):
        return "Closed / Withdrawn / Canceled"
    if re.search(r"\b(closed|inactive)\b", normalized, re.I):
        return "Closed / Withdrawn / Canceled"
    if re.search(r"\b(delinquent|non[-\s]?compliant|expired|overdue)\b", normalized, re.I):
        return "Delinquent"
    if normalized in {"current", "active", "good standing", "compliant"} or re.search(r"\bgood\s+as\s+of\b", normalized):
        return "Current"
    if "upcoming" in normalized or "due" in normalized:
        return "Upcoming Filing"

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


def add_months_preserving_end_of_month(value: date, months: int) -> date:
    shifted = add_months(value, months)
    if value.day == calendar.monthrange(value.year, value.month)[1]:
        return shifted.replace(day=calendar.monthrange(shifted.year, shifted.month)[1])
    return shifted


def fifteenth_day_after_fiscal_year_end(fy_end: date, months_after_end_month: int) -> date:
    month_anchor = date(fy_end.year, fy_end.month, 1)
    return add_months(month_anchor, months_after_end_month).replace(day=15)


def md_automatic_extension_due_date(fy_end: date) -> date:
    return fifteenth_day_after_fiscal_year_end(fy_end, 11)


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


def public_profile_for_ein(ein: str) -> dict:
    target = re.sub(r"\D", "", ein or "")
    if len(target) != 9:
        return {}
    if target in PUBLIC_PROFILE_CACHE:
        return PUBLIC_PROFILE_CACHE[target]
    try:
        url = f"https://projects.propublica.org/nonprofits/api/v2/organizations/{target}.json"
        request = urllib.request.Request(url, headers={"User-Agent": "ComplianceExpressRegistrySnapshot/1.0"})
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    except Exception:
        payload = {}
    PUBLIC_PROFILE_CACHE[target] = payload
    return payload


def public_profile_name_for_ein(ein: str) -> str:
    target = re.sub(r"\D", "", ein or "")
    if len(target) != 9:
        return ""
    if target in ORG_NAME_CACHE:
        return ORG_NAME_CACHE[target]
    payload = public_profile_for_ein(ein)
    name = ((payload.get("organization") or {}).get("name") or "").strip()
    ORG_NAME_CACHE[target] = name
    return name


def public_profile_latest_tax_year_for_ein(ein: str) -> int | None:
    payload = public_profile_for_ein(ein)
    candidates = []
    raw_tax_period = str((payload.get("organization") or {}).get("tax_period") or "")
    match = re.match(r"(20\d{2})[-/]?\d{0,2}", raw_tax_period)
    if match:
        candidates.append(int(match.group(1)))
    for filing in payload.get("filings_with_data") or []:
        for key in ("tax_prd_yr", "tax_prd"):
            raw = str(filing.get(key) or "")
            match = re.match(r"(20\d{2})", raw)
            if match:
                candidates.append(int(match.group(1)))
    return max(candidates) if candidates else None


def public_profile_latest_tax_period_for_ein(ein: str) -> tuple[int, tuple[int, int]] | None:
    """Return the latest public profile tax year and fiscal year end, if available."""
    payload = public_profile_for_ein(ein)
    candidates: list[tuple[int, tuple[int, int]]] = []
    raw_tax_period = str((payload.get("organization") or {}).get("tax_period") or "")
    match = re.match(r"(20\d{2})[-/]?(\d{1,2})?", raw_tax_period)
    if match:
        year = int(match.group(1))
        month = int(match.group(2) or "12")
        if 1 <= month <= 12:
            candidates.append((year, (month, calendar.monthrange(year, month)[1])))
    for filing in payload.get("filings_with_data") or []:
        raw_period = str(filing.get("tax_prd") or "")
        match = re.fullmatch(r"(20\d{2})(\d{2})", raw_period)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            if 1 <= month <= 12:
                candidates.append((year, (month, calendar.monthrange(year, month)[1])))
        raw_year = str(filing.get("tax_prd_yr") or "")
        if re.fullmatch(r"20\d{2}", raw_year):
            candidates.append((int(raw_year), (12, 31)))
    return max(candidates, key=lambda item: item[0]) if candidates else None


def resolved_organization_name(ein: str, supplied_name: str = "") -> str:
    supplied_name = (supplied_name or "").strip()
    reference_name = organization_name_for_ein(ein)
    profile_name = public_profile_name_for_ein(ein)
    return supplied_name or reference_name or profile_name


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
    payload = public_profile_for_ein(ein)
    filings = payload.get("filings_with_data") or []
    for filing in filings:
        raw_period = str(filing.get("tax_prd") or "")
        match = re.fullmatch(r"(\d{4})(\d{2})", raw_period)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            if 1 <= month <= 12:
                return month, calendar.monthrange(year, month)[1]
    raw_tax_period = str((payload.get("organization") or {}).get("tax_period") or "")
    match = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw_tax_period)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        if 1 <= month <= 12:
            if day == 1:
                day = calendar.monthrange(year, month)[1]
            return month, min(day, calendar.monthrange(year, month)[1])
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
        base_due = fifteenth_day_after_fiscal_year_end(fy_end, 5)
        extended_due = add_months(base_due, 6)
        effective_due = base_due if base_due >= date.today() else extended_due
        return effective_due, (
            f"California annual filing base due date is {format_date(base_due)}; "
            f"if an extension was applied, the extended due date is {format_date(extended_due)}"
        )
    if state == "MD":
        base_due = add_months_preserving_end_of_month(fy_end, 6)
        extended_due = md_automatic_extension_due_date(fy_end)
        return base_due, (
            f"Maryland annual filing initial due date is {format_date(base_due)}; "
            f"if the automatic extension applies, the extension date is {format_date(extended_due)}"
        )
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
        return date(report_year - 1, 9, 1), "based on North Dakota's annual charitable organization renewal cycle"
    if state == "AK":
        return date(report_year, 9, 1), "based on Alaska's annual charitable registration cycle"
    return None, "state due-date rule is not encoded"


def filing_due_date_options(state: str, report_year: int, fiscal_end: tuple[int, int]) -> dict:
    state = state.upper()
    fy_end = date(report_year, fiscal_end[0], fiscal_end[1])
    if state == "CA":
        base_due = date(report_year, 12, 31) if fiscal_end == (6, 30) else fifteenth_day_after_fiscal_year_end(fy_end, 5)
    elif state == "MD":
        base_due = add_months_preserving_end_of_month(fy_end, 6)
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

    if state == "MD":
        extended_due = md_automatic_extension_due_date(fy_end)
    else:
        extended_due = add_months_preserving_end_of_month(base_due, 6) if state in EXTENSION_SCENARIO_STATES else None
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


def nj_inferred_latest_filing_year(fiscal_end: tuple[int, int]) -> int | None:
    """Infer the latest NJ filing year that should be on record for a compliant charity."""
    today = date.today()
    for report_year in range(today.year, today.year - 5, -1):
        try:
            due_options = filing_due_date_options("NJ", report_year, fiscal_end)
            due_date = due_options.get("base_due") or due_options.get("effective_due")
        except Exception:
            due_date = None
        if due_date and due_date <= today:
            return report_year
    return None


def latest_year_from_text(body: str, state: str) -> int | None:
    readable_body = html.unescape(re.sub(r"<[^>]+>", " ", body))
    if state == "HI":
        annual_section_match = re.search(
            r"(?:Annual\s+filing\s+documents|Annual\s+filings?|Documents)([\s\S]{0,5000}?)(?:Registration\s+documents|Other\s+Info|Current\s+CCV|Past\s+CCV|$)",
            readable_body,
            re.I,
        )
        annual_section = annual_section_match.group(1) if annual_section_match else ""
        hi_years = [
            int(match.group(1))
            for match in re.finditer(
                r"(?:Annual\s+Filing\s+for\s+Charitable\s+Organizations|Fiscal\s+year\s+end|FYE|Accounting\s+Period\s+End\s+Date)[\s\S]{0,180}\b(20\d{2})\b",
                annual_section,
                re.I,
            )
        ]
        return max(hi_years) if hi_years else None
    if state == "MD":
        md_patterns = [
            r"Most\s+Recent\s+Fiscal\s+Year\s*:?\s*(20\d{2})",
            r"Last\s+Year\s+Represented\s*:?\s*(20\d{2})",
            r"Year\s+Represented\s*:?\s*(20\d{2})",
        ]
        md_matches = []
        for pattern in md_patterns:
            for match in re.finditer(pattern, readable_body, re.I):
                md_matches.append((match.start(), int(match.group(1))))
        if md_matches:
            return sorted(md_matches, key=lambda item: item[0])[0][1]
        return None
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
    if state == "MA":
        annual_match = re.search(
            r"Annual\s+Filings(?:\s+and\s+Documents)?([\s\S]{0,14000}?)(?:Charity\s+Registration\s+Documents|Registration\s+Documents|Other\s+Filed\s+Documents|$)",
            readable_body,
            re.I,
        )
        if annual_match:
            annual_section = annual_match.group(1)
            annual_years = []
            for match in re.finditer(r"\b(20\d{2})\b[\s\S]{0,140}\bForm[\s-]*PC\b", annual_section, re.I):
                annual_years.append(int(match.group(1)))
            for match in re.finditer(r"\bForm[\s-]*PC\b[\s\S]{0,140}\b(20\d{2})\b", annual_section, re.I):
                annual_years.append(int(match.group(1)))
            return max(annual_years) if annual_years else None
        return None
    if state == "CA":
        ca_years = ca_annual_renewal_years_from_text(readable_body)
        return ca_years.get("latest_submitted_year")
        return None
    for pattern in patterns:
        for match in re.finditer(pattern, readable_body, re.I):
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


def ca_annual_renewal_years_from_text(body: str) -> dict:
    readable_body = html.unescape(re.sub(r"<[^>]+>", " ", body or ""))
    readable_body = re.sub(r"\s+", " ", readable_body)
    annual_match = re.search(
        r"Annual\s+Renewal\s+Data([\s\S]{0,40000}?)(?:Fundraising\s+Platform\s+Data|Related\s+Registration|Filing\s+and\s+Correspondence|$)",
        readable_body,
        re.I,
    )
    if not annual_match:
        return {"latest_submitted_year": None, "latest_not_submitted_year": None}
    annual_section = annual_match.group(1)
    blocks = re.split(r"(?=Status\s+of\s+Filing\s*:)", annual_section, flags=re.I)
    submitted_years = []
    not_submitted_years = []
    not_submitted_status_by_year = {}
    for block in blocks:
        if not re.search(r"Status\s+of\s+Filing\s*:", block, re.I):
            continue
        status_match = re.search(
            r"Status\s+of\s+Filing\s*:?\s*(.*?)(?=(?:\s+)?Accounting\s+Period\s+Begin\s+Date|(?:\s+)?Accounting\s+Period\s+End\s+Date|(?:\s+)?Filing\s+Received\s+Date|$)",
            block,
            re.I,
        )
        status_text = re.sub(r"\s+", " ", status_match.group(1)).strip() if status_match else ""
        end_match = re.search(
            r"Accounting\s+Period\s+End\s+Date\s*:?\s*\d{1,2}\s*[/-]\s*\d{1,2}\s*[/-]\s*(20\d{2})",
            block,
            re.I,
        )
        if not end_match:
            continue
        filing_received_match = re.search(
            r"Filing\s+Received\s+Date\s*:?\s*\d{1,2}\s*[/-]\s*\d{1,2}\s*[/-]\s*20\d{2}",
            block,
            re.I,
        )
        year = int(end_match.group(1))
        if re.search(r"\b(?:not\s+submitted|in\s+process|pending)\b", status_text, re.I):
            not_submitted_years.append(year)
            not_submitted_status_by_year[year] = status_text or "Not Submitted"
        elif (
            (
                re.search(r"\b(?:e-)?accepted\b", status_text, re.I)
                or (not status_text and filing_received_match)
            )
            and not re.search(r"\breject|incomplete|not\s+submitted\b", status_text, re.I)
        ):
            submitted_years.append(year)
    latest_not_submitted_year = max(not_submitted_years) if not_submitted_years else None
    return {
        "latest_submitted_year": max(submitted_years) if submitted_years else None,
        "latest_not_submitted_year": latest_not_submitted_year,
        "latest_not_submitted_status": not_submitted_status_by_year.get(latest_not_submitted_year) if latest_not_submitted_year else None,
    }


def fiscal_year_end_from_result(result) -> tuple[int, int] | None:
    """Prefer fiscal year ends that the state lookup itself exposed."""
    text = " ".join([
        result.raw_status_text or "",
        result.source_note or "",
    ])
    match = re.search(r"Latest\s+FYE\s*:?\s*(20\d{2})-(\d{1,2})-(\d{1,2})", text, re.I)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        if 1 <= month <= 12:
            return month, min(day, calendar.monthrange(year, month)[1])
    match = re.search(r"Fiscal\s+Year\s+End\s*:?\s*(\d{1,2})[/-](\d{1,2})[/-](20\d{2})", text, re.I)
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
        year = int(match.group(3))
        if 1 <= month <= 12:
            return month, min(day, calendar.monthrange(year, month)[1])
    return None


def md_represented_year_from_text(body: str, ein: str = "", organization_name: str = "") -> int | None:
    source = body or ""
    for escaped, replacement in {
        "\\u003c": "<",
        "\\u003C": "<",
        "\\u003e": ">",
        "\\u003E": ">",
        "\\u0026": "&",
        "\\u00a0": " ",
        "\\/": "/",
    }.items():
        source = source.replace(escaped, replacement)
    readable = html.unescape(re.sub(r"<[^>]+>", " ", source))
    readable = re.sub(r"\s+", " ", readable)
    patterns = [
        r"Most\s+Recent\s+Fiscal\s+Year\s*:?\s*(20\d{2})",
        r"Last\s+Year\s+Represented\s*:?\s*(20\d{2})",
        r"Year\s+Represented\s*:?\s*(20\d{2})",
    ]
    ein_digits = re.sub(r"\D", "", ein or "")
    normalize = getattr(checker, "normalize_name", lambda value: re.sub(r"\s+", " ", (value or "").lower()).strip())
    normalized_name = normalize(organization_name)
    candidates = []
    for pattern in patterns:
        for match in re.finditer(pattern, readable, re.I):
            start = match.start()
            window = readable[max(0, start - 1800): start + 1800]
            window_digits = re.sub(r"\D", "", window)
            score = 0
            if ein_digits and ein_digits in window_digits:
                score += 3
            if normalized_name and normalized_name in normalize(window):
                score += 2
            if re.search(r"Charity\s+Details|Organization\s+Income|Organization\s+Expenses|Charity\s+EIN", window, re.I):
                score += 1
            candidates.append({"year": int(match.group(1)), "start": start, "score": score})
    if not candidates:
        return None
    scored = [candidate for candidate in candidates if candidate["score"] > 0]
    if scored:
        best_score = max(candidate["score"] for candidate in scored)
        return max(candidate["year"] for candidate in scored if candidate["score"] == best_score)
    return sorted(candidates, key=lambda item: item["start"])[0]["year"]


def filing_context(result, body: str) -> dict:
    state = (result.state or "").upper()
    if state == "MD":
        latest_year = md_represented_year_from_text(body, result.ein, result.organization_name)
    else:
        latest_year = latest_year_from_text(body, result.state)
    if state == "PA":
        latest_year = None
    if latest_year is None and state in {"MA", "CA", "HI", "NJ"}:
        raw_year = re.fullmatch(r"\s*(20\d{2})\s*", result.raw_status_text or "")
        if raw_year:
            latest_year = int(raw_year.group(1))
    if latest_year is None and re.search(r"registration\s+found|year\s+represented|latest|most\s+recent|filing\s+year", result.raw_status_text or "", re.I):
        year_match = re.search(r"(20\d{2})", result.raw_status_text or "")
        latest_year = int(year_match.group(1)) if year_match else None
    period_start, period_end = fiscal_period_for_ein(result.ein)
    if (
        state == "CA"
        and latest_year is not None
        and latest_year < date.today().year - 3
        and re.search(r"\bCurrent\b", " ".join([result.status or "", result.raw_status_text or ""]), re.I)
    ):
        latest_year = None
    if (
        latest_year is None
        and state == "NJ"
        and re.search(r"\b(compliant|current|active)\b", " ".join([result.status or "", result.raw_status_text or "", body or ""]), re.I)
    ):
        latest_year = public_profile_latest_tax_year_for_ein(result.ein)
    if (
        latest_year is not None
        and state == "NJ"
        and re.search(r"\b(compliant|current|active)\b", " ".join([result.status or "", result.raw_status_text or "", body or ""]), re.I)
    ):
        profile_latest_year = public_profile_latest_tax_year_for_ein(result.ein)
        _, ce_period_end = fiscal_period_for_ein(result.ein)
        ce_latest_year = ce_period_end.year if ce_period_end else None
        if profile_latest_year and profile_latest_year > latest_year:
            latest_year = profile_latest_year
        if ce_latest_year and ce_latest_year > latest_year:
            latest_year = ce_latest_year
    # For CA, use Annual Renewal Data only. Pulling a Form 990/profile year here
    # can create a filing year that the California registry did not show.
    if latest_year is None and period_end and state not in {"CA", "MA", "MD", "NJ", "PA"}:
        latest_year = period_end.year
    override_fiscal_end = FISCAL_YEAR_END_OVERRIDES.get(re.sub(r"\D", "", result.ein or ""))
    result_fiscal_end = fiscal_year_end_from_result(result)
    registry_fiscal_end = fiscal_year_end_from_body(body, state)
    profile_period = public_profile_latest_tax_period_for_ein(result.ein)
    profile_fiscal_end = profile_period[1] if profile_period else None
    fiscal_end = result_fiscal_end or registry_fiscal_end or override_fiscal_end or profile_fiscal_end or fiscal_year_end_for_ein(result.ein)

    if (
        state == "NJ"
        and fiscal_end
        and re.search(r"\b(compliant|current|active)\b", " ".join([result.status or "", result.raw_status_text or "", body or ""]), re.I)
    ):
        inferred_latest_year = nj_inferred_latest_filing_year(fiscal_end)
        if inferred_latest_year and (latest_year is None or inferred_latest_year > latest_year):
            latest_year = inferred_latest_year

    if latest_year is None or fiscal_end is None:
        return {
            "represented_year": latest_year,
            "fiscal_end": fiscal_end,
            "next_report_year": None,
            "due_date": None,
            "comment": "Annual filing due date could not be determined from the available CharityClarity check."
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


def current_cycle_already_filed(state: str, represented_year: int | None, registry_date: date | None = None) -> bool:
    """The filing year on record is recent enough to use next-due-date logic."""
    if represented_year is None:
        return False
    state = (state or "").upper()
    today = date.today()
    if state == "AK":
        return represented_year >= today.year and (registry_date is None or registry_date >= today)
    if state in {"CA", "HI", "MA", "MD"}:
        return represented_year >= today.year - 1
    return False


def status_for_filed_cycle(state: str, context: dict, registry_date: date | None = None) -> str:
    due_date = context.get("due_date")
    represented_year = context.get("represented_year")
    if due_date and represented_year:
        return status_from_calendar_date(due_date)
    if current_cycle_already_filed(state, represented_year, registry_date):
        return "Current"
    return ""


def represented_year_is_registry_evidenced(result, body: str, represented_year: int | None) -> bool:
    if represented_year is None:
        return False
    state = (result.state or "").upper()
    combined = combined_result_text(result, body)
    if latest_year_from_text(combined, state) == represented_year:
        return True
    if state == "AK" and re.search(rf"\b{represented_year}\s+registration\s+found\b", combined, re.I):
        return True
    return False


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


def md_detail_body(page, deep: bool = False) -> str:
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
    if deep:
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


def organization_name_variants(
    name: str,
    ein: str = "",
    include_ein_aliases: bool = True,
    include_name_segments: bool = False,
    include_compact_legal_suffixes: bool = True,
    include_leading_article_variants: bool = True,
) -> list[str]:
    variants = []

    def add(value: str) -> None:
        value = re.sub(r"\s+", " ", (value or "").strip())
        if value and value.lower() not in {item.lower() for item in variants}:
            variants.append(value)

    seed_names = [name]
    if ein and include_ein_aliases:
        seed_names.extend([organization_name_for_ein(ein), public_profile_name_for_ein(ein)])

    if include_name_segments:
        segmented_seeds = []
        for seed in list(seed_names):
            for part in re.split(
                r"\s*(?:/|\\|\bd/?b/?a\b|\bdoing\s+business\s+as\b|\baka\b|\bfka\b|\bformerly\b)\s*",
                seed or "",
                flags=re.I,
            ):
                part = re.sub(r"\s+", " ", part.strip(" ,;-"))
                if len(part.split()) >= 2:
                    segmented_seeds.append(part)
        seed_names.extend(segmented_seeds)

    for seed in seed_names:
        base = re.sub(r"\s+", " ", (seed or "").strip())
        if not base:
            continue
        add(base)
        us_prefixed_variants = []
        if re.match(r"^us\s+", base, re.I):
            us_prefixed_variants.append(re.sub(r"^us\s+", "U.S. ", base, flags=re.I))
            us_prefixed_variants.append(re.sub(r"^us\s+", "United States ", base, flags=re.I))
        elif re.match(r"^u\.?\s*s\.?\s+", base, re.I):
            us_prefixed_variants.append(re.sub(r"^u\.?\s*s\.?\s+", "US ", base, flags=re.I))
            us_prefixed_variants.append(re.sub(r"^u\.?\s*s\.?\s+", "United States ", base, flags=re.I))
        without_trailing_the = re.sub(r",\s*the\s*$", "", base, flags=re.I).strip()
        without_leading_the = re.sub(r"^the\s+", "", base, flags=re.I).strip()
        without_comma_suffix = re.sub(r",\s*(inc\.?|incorporated|corp\.?|corporation|llc|ltd\.?)\s*$", "", base, flags=re.I).strip()
        without_suffix = re.sub(r"\b(inc\.?|incorporated|corp\.?|corporation|llc|ltd\.?)\s*$", "", without_comma_suffix, flags=re.I).strip()
        no_comma = re.sub(r",\s*", " ", base).strip()
        no_punctuation = re.sub(r"[^\w\s]", " ", base).strip()
        no_punctuation = re.sub(r"\s+", " ", no_punctuation)
        institute_plural = re.sub(r"\bInstitute\s+of\b", "Institutes of", base, flags=re.I).strip()
        institute_singular = re.sub(r"\bInstitutes\s+of\b", "Institute of", base, flags=re.I).strip()
        hyphen_as_space = re.sub(r"[-\u2010-\u2015]+", " ", base).strip()
        hyphen_removed = re.sub(r"[-\u2010-\u2015]+", "", base).strip()
        ampersand_as_and = re.sub(r"\s*&\s*", " and ", base).strip()
        ampersand_removed = re.sub(r"\s*&\s*", " ", base).strip()
        apostrophe_removed = re.sub(r"[']", "", base).strip()
        possessive_removed = re.sub(r"\b([A-Za-z]+)'s\b", r"\1s", base).strip()
        and_no_punctuation = re.sub(r"[^\w\s]", " ", ampersand_as_and).strip()
        and_no_punctuation = re.sub(r"\s+", " ", and_no_punctuation)
        and_without_suffix = re.sub(
            r"\b(inc\.?|incorporated|corp\.?|corporation|foundation|fund|llc|ltd\.?)\b",
            " ",
            and_no_punctuation,
            flags=re.I,
        ).strip()
        and_without_suffix = re.sub(r"\s+", " ", and_without_suffix)
        compact_legal_suffixes = re.sub(
            r"\b(the|inc\.?|incorporated|corp\.?|corporation|foundation|fund|llc|ltd\.?)\b",
            " ",
            no_punctuation,
            flags=re.I,
        ).strip()
        compact_legal_suffixes = re.sub(r"\s+", " ", compact_legal_suffixes)
        hyphenated_word_pairs = []
        words = base.split()
        if "-" not in base and 2 <= len(words) <= 8:
            for idx in range(len(words) - 1):
                pair_variant = words[:]
                pair_variant[idx] = f"{pair_variant[idx]}-{pair_variant[idx + 1]}"
                del pair_variant[idx + 1]
                hyphenated_word_pairs.append(" ".join(pair_variant))
        broad_variants = [and_without_suffix, compact_legal_suffixes] if include_compact_legal_suffixes else []
        article_variants = [without_leading_the] if include_leading_article_variants else []
        for variant in [
            without_comma_suffix,
            without_suffix,
            no_comma,
            no_punctuation,
            institute_plural,
            institute_singular,
            hyphen_as_space,
            hyphen_removed,
            ampersand_as_and,
            ampersand_removed,
            apostrophe_removed,
            possessive_removed,
            and_no_punctuation,
            *broad_variants,
            *us_prefixed_variants,
            without_trailing_the,
            *article_variants,
            *hyphenated_word_pairs,
        ]:
            add(variant)
    return variants or [""]


def org_with_name(org, name: str):
    clone = SimpleNamespace(organization_name=name, ein=org.ein)
    if hasattr(org, "evidence_mode"):
        clone.evidence_mode = getattr(org, "evidence_mode")
    return clone


def result_is_retryable_name_miss(result) -> bool:
    return public_status(result) == "Not Registered" or bool(re.search(
        r"no matching|no record found|no records found|not found|no results|0 records|0 results",
        " ".join([result.status or "", result.raw_status_text or "", result.source_note or ""]),
        re.I,
    ))


def is_leading_the_drop(original_name: str, variant: str) -> bool:
    original = re.sub(r"\s+", " ", (original_name or "").strip())
    candidate = re.sub(r"\s+", " ", (variant or "").strip())
    if not re.match(r"^the\s+", original, re.I):
        return False
    if re.match(r"^the\s+", candidate, re.I):
        return False
    without_the = re.sub(r"^the\s+", "", original, flags=re.I).strip()
    normalize = getattr(checker, "normalize_name", lambda value: re.sub(r"\W+", " ", (value or "").lower()).strip())
    without_the_norm = normalize(without_the)
    candidate_norm = normalize(candidate)
    return bool(candidate_norm and without_the_norm and (candidate_norm in without_the_norm or without_the_norm in candidate_norm))


def search_with_name_variants(
    page,
    org,
    search_func,
    max_variants: int | None = None,
    reject_va_suspended_from_leading_the_drop: bool = False,
    include_ein_aliases: bool = True,
    include_name_segments: bool = False,
    include_compact_legal_suffixes: bool = True,
    include_leading_article_variants: bool = True,
):
    best_result = None
    original_name = org.organization_name
    variants = organization_name_variants(
        original_name,
        org.ein,
        include_ein_aliases=include_ein_aliases,
        include_name_segments=include_name_segments,
        include_compact_legal_suffixes=include_compact_legal_suffixes,
        include_leading_article_variants=include_leading_article_variants,
    )
    if max_variants:
        variants = variants[:max_variants]
    for variant in variants:
        result = search_func(page, org_with_name(org, variant))
        if getattr(result, "organization_name", "") != original_name:
            result.organization_name = original_name
        if (
            reject_va_suspended_from_leading_the_drop
            and public_status(result) == "Suspended"
            and is_leading_the_drop(original_name, variant)
        ):
            continue
        if not result_is_retryable_name_miss(result):
            return result
        best_result = result
    if best_result and getattr(best_result, "organization_name", "") != original_name:
        best_result.organization_name = original_name
    return best_result


def find_ak_print_link_relaxed(page, org):
    formatted_ein = checker.format_ein_with_dash(org.ein)
    ein_digits = re.sub(r"\D", "", org.ein or "")
    variants = organization_name_variants(org.organization_name, org.ein)
    for variant in variants:
        try:
            found = checker.find_ak_print_link(page, org_with_name(org, variant))
            if found:
                return found
        except Exception:
            pass
    return page.evaluate(
        """
        ({ formattedEin, einDigits, names }) => {
            const normalize = (value) => (value || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
            const normalizedNames = (names || []).map(normalize).filter(Boolean);
            const rows = Array.from(document.querySelectorAll('table.DocTable tbody tr, table tbody tr'));
            for (const row of rows) {
                const rowText = (row.innerText || row.textContent || '').trim().replace(/\\s+/g, ' ');
                const rowDigits = rowText.replace(/\\D/g, '');
                const rowNorm = normalize(rowText);
                const einSeen = (formattedEin && rowText.includes(formattedEin)) || (einDigits && rowDigits.includes(einDigits));
                const nameSeen = normalizedNames.length && normalizedNames.some((name) => rowNorm.includes(name) || name.includes(rowNorm));
                if (!einSeen && !nameSeen) continue;
                const links = Array.from(row.querySelectorAll('a'));
                for (const link of links) {
                    const text = (link.innerText || link.textContent || '').trim();
                    const rect = link.getBoundingClientRect();
                    const style = window.getComputedStyle(link);
                    const visible = !!(rect.width && rect.height) && style.display !== 'none' && style.visibility !== 'hidden';
                    if (/^Print$/i.test(text) && visible) {
                        return { found: true, rowText, x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
                    }
                }
            }
            return null;
        }
        """,
        {"formattedEin": formatted_ein, "einDigits": ein_digits, "names": variants},
    )


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
    years_to_try = list(getattr(checker, "AK_YEARS_TO_TRY", [date.today().year, date.today().year - 1]))
    for idx, year in enumerate(years_to_try):
        ak_context = browser.new_context(viewport={"width": 1365, "height": 900}, accept_downloads=False)
        configure_browser_context(ak_context)
        ak_page = ak_context.new_page()
        try:
            if not checker.open_ak_public_search(ak_page):
                result.error = "Could not open Alaska Public Search form"
                continue
            checker.fill_ak_search_form(ak_page, org, year)
            print_link = find_ak_print_link_relaxed(ak_page, org)
            page_body = registry_page_body(ak_page)
            if not print_link:
                continue
            result.status, result.raw_status_text, result.source_note = checker.classify_ak_registration_year(year, None)
            result.success = True
            return result, page_body
        except Exception as e:
            result.error = f"AK error: {e}"
            continue
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
        best_score = -10_000
        ein_digits = re.sub(r"\D", "", org.ein or "")
        wanted_name = getattr(checker, "normalize_name", lambda value: re.sub(r"\s+", " ", (value or "").lower()).strip())(
            org.organization_name
        )
        for i in range(min(link_count, 20)):
            link = detail_links.nth(i)
            try:
                row_text = ""
                row = link.locator("xpath=ancestor::tr[1]")
                if row.count():
                    row_text = re.sub(r"\s+", " ", row.first.inner_text(timeout=1500)).strip()
                href = link.get_attribute("href", timeout=1500) or ""
                if not href:
                    continue
                row_digits = re.sub(r"\D", "", row_text)
                row_name = getattr(checker, "normalize_name", lambda value: re.sub(r"\s+", " ", (value or "").lower()).strip())(
                    row_text
                )
                score = 0
                if ein_digits and ein_digits in row_digits:
                    score += 40
                if wanted_name and wanted_name in row_name:
                    score += 12
                if re.search(r"\bcharity\s+registration\b", row_text, re.I):
                    score += 10
                if re.search(r"\b(current|active|exempt|registered)\b", row_text, re.I):
                    score += 8
                if re.search(r"\b(merged\s+out|withdrawn|dissolved|closed)\b", row_text, re.I):
                    score -= 35
                if score > best_score:
                    best_score = score
                    target_href = href
            except Exception:
                continue
        if target_href:
            page.goto(urljoin(page.url, target_href), wait_until="domcontentloaded", timeout=45000)
            checker.safe_wait_for_network_idle(page, timeout=8000)
            time.sleep(0.75)
    except Exception:
        pass

    for text in ["Annual Renewal Data", "Renewal Data", "Annual Filings"]:
        try:
            page.get_by_text(re.compile(text, re.I)).first.scroll_into_view_if_needed(timeout=4000)
            page.locator("body").evaluate("window.scrollBy(0, -80)")
            time.sleep(0.5)
            break
        except Exception:
            continue
    try:
        current_body = registry_page_body(page)
        if not scroll_to_latest_year_evidence(page, "CA", current_body):
            page.locator("body").evaluate("window.scrollTo(0, Math.max(0, document.body.scrollHeight * 0.28))")
            time.sleep(0.5)
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
        best_status_score = -999
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
                    status_score = 0
                    try:
                        row_text = re.sub(r"\s+", " ", link.locator("xpath=ancestor::tr[1]").inner_text(timeout=1500)).strip()
                        if re.search(r"\bACTIVE\b", row_text, re.I):
                            status_score = 5
                        elif re.search(r"\b(CURRENT|GOOD\s+STANDING)\b", row_text, re.I):
                            status_score = 4
                        elif re.search(r"\b(FAILED\s+TO\s+RENEW|EXPIRED|REVOKED|SUSPENDED|INACTIVE)\b", row_text, re.I):
                            status_score = -5
                    except Exception:
                        status_score = 0
                    if score > best_score or (score == best_score and status_score > best_status_score):
                        best_score = score
                        best_status_score = status_score
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


def ma_detail_body(page) -> str:
    pieces = []
    for _ in range(3):
        time.sleep(2)
        body = registry_page_body(page)
        pieces.append(body)
        if latest_year_from_text(body, "MA"):
            break
        try:
            page.get_by_text(re.compile(r"Annual\s+Filings(?:\s+and\s+Documents)?", re.I)).first.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass
    return "\n".join(piece for piece in pieces if piece)


def repair_ma_false_not_registered(page, org, result, body: str):
    """Massachusetts EIN results often show the charity name without exposing EIN text."""
    if public_status(result) != "Not Registered":
        return result, body
    readable = re.sub(r"\s+", " ", body or "")
    if re.search(r"No\s+Charity\s+Found", readable, re.I):
        return result, body
    if not (re.search(r"Select\s+a\s+Charity", readable, re.I) and re.search(r"Get\s+Filings", readable, re.I)):
        return result, body

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

    try:
        checker.safe_wait_for_network_idle(page, timeout=10000)
    except Exception:
        pass
    for _ in range(8):
        time.sleep(0.75)
        try:
            refreshed = registry_page_body(page)
        except Exception:
            continue
        if re.search(r"Form[\s-]*PC|No documents found|No rows available", refreshed, re.I):
            body = refreshed
            break
    try:
        page.locator("body").evaluate("window.scrollTo(0, document.body.scrollHeight)")
    except Exception:
        pass
    body = ma_detail_body(page) or body
    latest_year = latest_year_from_text(body, "MA")
    if latest_year:
        result.raw_status_text = str(latest_year)
        classifier = getattr(checker, "classify_ma_visible_filing_year", None)
        result.status = classifier(latest_year) if classifier else checker.STATUS_DELINQUENT
        result.source_note = (
            "Massachusetts EIN search returned a charity record; CharityClarity uses the latest visible Form PC year "
            "from Annual Filings because the search result does not expose EIN text in the visible page."
        )
    else:
        result.raw_status_text = "Annual Filings not visible"
        result.status = checker.STATUS_DELINQUENT
        result.source_note = (
            "Massachusetts EIN search returned a charity record, but did not expose a visible Form PC filing year after Get Filings."
        )
    result.success = True
    return result, body


def search_hi_precise(page, org):
    url = "https://charity.ehawaii.gov/charity/new-search.html"
    result = checker.StateResult(org.organization_name, org.ein, "HI", checker.STATUS_UNKNOWN, url)
    try:
        ein_digits = re.sub(r"\D", "", org.ein or "")
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        checker.safe_wait_for_network_idle(page, timeout=6000)
        time.sleep(1)
        try:
            page.locator("#nameFilter").select_option(label="Contains...")
        except Exception:
            pass
        name_input = checker.find_visible_input(page, ["#name", 'input[name="name"]', 'input[id="name"]'])
        fein_input = checker.find_visible_input(page, ["#fein", 'input[name="fein"]', 'input[id="fein"]'])
        if not name_input or not fein_input:
            result.error = "Could not find HI search fields"
            return result
        body = ""
        clicked_result = False
        attempts = []
        if ein_digits:
            for ein_value in [checker.format_ein_with_dash(org.ein), ein_digits]:
                if ein_value and ("", ein_value) not in attempts:
                    attempts.append(("", ein_value))
        for variant in organization_name_variants(org.organization_name, org.ein):
            if variant:
                for ein_value in ([checker.format_ein_with_dash(org.ein), ein_digits] if ein_digits else [""]):
                    if (variant, ein_value) not in attempts:
                        attempts.append((variant, ein_value))
        for variant, ein_value in attempts[:5]:
            name_input.fill("")
            name_input.fill(variant)
            fein_input.fill("")
            if ein_value:
                fein_input.fill(ein_value)
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
            checker.safe_wait_for_network_idle(page, timeout=7000)
            time.sleep(1.25)
            wanted_variants = [checker.normalize_name(item) for item in organization_name_variants(org.organization_name, org.ein)]
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
                            row_digits = re.sub(r"\D", "", row_text)
                            row_name = checker.normalize_name(row_text)
                            name_match = any(name and (name in row_name or row_name in name) for name in wanted_variants)
                            if ein_digits and ein_digits not in row_digits:
                                continue
                            if not ein_digits and not name_match:
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
            if clicked_result:
                break
            body = page.locator("body").inner_text(timeout=15000)
            if re.search(r"no results|no records|0 results|showing 0 to 0 of 0 entries|no data available in table|not registered in our system", body, re.I):
                continue
        if not clicked_result:
            result.raw_status_text = "No record found" if re.search(r"no results|no records|0 results|showing 0 to 0 of 0 entries|no data available in table|not registered in our system", body, re.I) else "No matching organization result"
            result.status = "Not registered"
            result.source_note = "Hawaii search results did not contain a matching organization/EIN row."
            result.success = True
            return result
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        checker.safe_wait_for_network_idle(page, timeout=6000)
        time.sleep(1)
        detail_text = page.locator("body").inner_text(timeout=12000)
        detail_ein = (
            checker.extract_labeled_value(page, ["FEIN", "Federal Tax ID (EIN)", "Federal Tax ID", "EIN"])
            or checker.extract_labeled_value_from_text(detail_text, ["FEIN", "Federal Tax ID (EIN)", "Federal Tax ID", "EIN"])
        )
        if ein_digits and detail_ein and re.sub(r"\D", "", detail_ein) != ein_digits:
            return checker.reject_wrong_ein_result(result, "Hawaii")
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
    existing_status = " ".join([result.status or "", result.raw_status_text or ""])
    if re.search(r"\bACTIVE\b", existing_status, re.I) and not re.search(r"\b(FAILED\s+TO\s+RENEW|EXPIRED|REVOKED|SUSPENDED|INACTIVE)\b", existing_status, re.I):
        result.raw_status_text = result.raw_status_text or "Active"
        result.status = result.status or "Active"
        result.source_note = result.source_note or "Registration status with definition (ME)"
        result.error = ""
        result.success = True
        return
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


def search_nj_direct(page, org):
    url = "https://charportal.dca.njoag.gov/Charity-Registration/CHR-Public-Search-Page/"
    result = checker.StateResult(org.organization_name, org.ein, "NJ", checker.STATUS_UNKNOWN, url)
    try:
        ein_digits = re.sub(r"\D", "", org.ein or "")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(1)
        input_box = None
        for selector in [
            "#SearchBox28",
            'input[placeholder="Search"]',
            'input[aria-label*="partial text" i]',
            'input[id^="SearchBox"]',
            'input[type="search"]',
            'input[type="text"]',
        ]:
            try:
                candidate = page.locator(selector).first
                candidate.wait_for(state="visible", timeout=5000)
                input_box = candidate
                break
            except Exception:
                continue
        if not input_box:
            result.error = "Could not find NJ search box"
            return result

        input_box.fill("")
        input_box.fill(ein_digits or org.organization_name)
        page.keyboard.press("Enter")
        body = ""
        deadline = time.time() + 22
        while time.time() < deadline:
            body = page.locator("body").inner_text(timeout=5000)
            body_digits = re.sub(r"\D", "", body)
            if (ein_digits and ein_digits in body_digits) or re.search(r"no records found|no records|no matching|0 results", body, re.I):
                break
            time.sleep(0.75)
        if re.search(r"no records found|no records|no matching|0 results", body, re.I):
            result.raw_status_text = "No record found"
            result.status = checker.STATUS_NOT_REGISTERED
            result.source_note = "New Jersey search returned no matching record."
            result.success = True
            return result

        status = ""
        status_patterns = [
            ("Noncompliant", r"\bnon[-\s]?compliant\b"),
            ("Delinquent", r"\bdelinquent\b"),
            ("Retired", r"\bretired\b"),
            ("Withdrawn", r"\bwithdrawn\b"),
            ("Revoked", r"\brevoked\b"),
            ("Suspended", r"\bsuspended\b"),
            ("Expired", r"\bexpired\b"),
            ("Pending", r"\bpending\b"),
            ("Compliant", r"\bcompliant\b"),
            ("Active", r"\bactive\b"),
            ("Current", r"\bcurrent\b"),
        ]
        if ein_digits and ein_digits in re.sub(r"\D", "", body):
            try:
                rows = page.locator("tr")
                for i in range(min(rows.count(), 80)):
                    row_text = re.sub(r"\s+", " ", rows.nth(i).inner_text(timeout=1500)).strip()
                    if ein_digits not in re.sub(r"\D", "", row_text):
                        continue
                    for label, pattern in status_patterns:
                        if re.search(pattern, row_text, re.I):
                            status = label
                            break
                    if status:
                        break
            except Exception:
                pass
        if not status and ein_digits and ein_digits in re.sub(r"\D", "", body):
            for label, pattern in status_patterns:
                if re.search(pattern, body, re.I):
                    status = label
                    break
        if not status:
            status_match = re.search(r"Status\s+([A-Za-z][A-Za-z /-]+?)\s+Federal\s+EIN", re.sub(r"\s+", " ", body), re.I)
            if status_match:
                status = status_match.group(1).strip()
        result.raw_status_text = status or "Status not found"
        if re.search(r"\b(retired|withdrawn|terminated|cancelled|canceled|closed)\b", status, re.I):
            result.status = "Closed / Withdrawn / Canceled"
        elif re.search(r"\bnon[-\s]?compliant\b", status, re.I):
            result.status = "Delinquent"
        else:
            result.status = status or checker.STATUS_UNKNOWN
        result.source_note = "New Jersey uses the public search result Status value."
        result.success = True
        return result
    except Exception as exc:
        result.error = f"NJ error: {exc}"
        return result


def md_filing_context(result, body: str) -> dict:
    return filing_context(result, body)


def fiscal_year_end_from_body(body: str, state: str = "") -> tuple[int, int] | None:
    readable_body = html.unescape(re.sub(r"<[^>]+>", " ", body))
    state = (state or "").upper()
    if state == "CA":
        annual_match = re.search(
            r"Annual\s+Renewal\s+Data([\s\S]{0,12000}?)(?:Fundraising\s+Platform\s+Data|Related\s+Registration|Filing\s+and\s+Correspondence|$)",
            readable_body,
            re.I,
        )
        if not annual_match:
            return None
        annual_section = annual_match.group(1)
        ca_patterns = [
            r"Accounting\s+Period\s+End\s+Date\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            r"Accounting\s+Period\s+End\s+Date\s*:?\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})",
            r"Fiscal\s+Year\s+End(?:ing)?\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            r"Fiscal\s+Year\s+End(?:ing)?\s*:?\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})",
        ]
        for pattern in ca_patterns:
            matches = [parse_due_date(match.group(1)) for match in re.finditer(pattern, annual_section, re.I)]
            parsed_dates = [value for value in matches if value]
            if parsed_dates:
                latest_period_end = max(parsed_dates)
                return latest_period_end.month, latest_period_end.day
        return None
    if state == "HI":
        annual_match = re.search(
            r"Annual\s+filing\s+documents([\s\S]{0,5000}?)(?:Registration\s+documents|Other\s+Filed\s+Documents|$)",
            readable_body,
            re.I,
        )
        annual_section = annual_match.group(1) if annual_match else readable_body
        hi_patterns = [
            r"Fiscal\s+year\s+end\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            r"Fiscal\s+year\s+end\s*:?\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})",
            r"Accounting\s+Period\s+End\s+Date\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            r"Accounting\s+Period\s+End\s+Date\s*:?\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})",
        ]
        for pattern in hi_patterns:
            matches = [parse_due_date(match.group(1)) for match in re.finditer(pattern, annual_section, re.I)]
            parsed_dates = [value for value in matches if value]
            if parsed_dates:
                latest_period_end = max(parsed_dates)
                return latest_period_end.month, latest_period_end.day
        if re.search(r"Fiscal\s+year\s+end", annual_section, re.I):
            parsed_dates = [
                value
                for value in (parse_due_date(match.group(0)) for match in re.finditer(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", annual_section))
                if value
            ]
            if parsed_dates:
                latest_period_end = max(parsed_dates)
                return latest_period_end.month, latest_period_end.day
        return None
    patterns = [
        r"(?:Accounting\s+Period\s+End\s+Date|Fiscal\s+Year\s+End|FYE|Fiscal\s+Period\s+End|Period\s+End(?:ing)?)[\s\S]{0,140}?([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})",
        r"(?:Accounting\s+Period\s+End\s+Date|Fiscal\s+Year\s+End|FYE|Fiscal\s+Period\s+End|Period\s+End(?:ing)?)[\s\S]{0,140}?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"(?:Accounting\s+Period\s+End\s+Date|Fiscal\s+Year\s+End|FYE|Fiscal\s+Period\s+End|Period\s+End(?:ing)?)\s*:?\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})",
        r"(?:Accounting\s+Period\s+End\s+Date|Fiscal\s+Year\s+End|FYE|Fiscal\s+Period\s+End|Period\s+End(?:ing)?)\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
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
            r"\b(?:registry\s+status|status|public\s+status|registration\s+status)\b[\s\S]{0,160}\bexempt\b",
            r"\bregistration\s+type\b[\s\S]{0,120}\bexempt\b",
            r"\bregistration\s+filing\s+status\b[\s\S]{0,160}\bexempt\b",
            r"\bexempt\s+registration\b",
            r"\bexempt\s+from\s+(charitable\s+|annual\s+)?registration\b",
            r"\bexempt\s*-\s*[A-Za-z0-9 /-]+",
            r"^\s*exempt\b",
        ]
    )


def hi_indicates_exempt_registration(text: str) -> bool:
    readable = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    readable = re.sub(r"\s+", " ", readable)
    return any(
        re.search(pattern, readable, re.I)
        for pattern in [
            r"\bRegistration\s+Type\b[\s\S]{0,80}\bExempt\b",
            r"\bExempt\s+Registration\b",
        ]
    )


def result_explicitly_exempt(result) -> bool:
    """Only trust exemption when it comes from the matched result fields."""
    status_text = " ".join([
        result.status or "",
        result.raw_status_text or "",
        result.source_note or "",
    ])
    return bool(re.search(
        r"\b(exempt|exempt\s+registration|exempt\s+from\s+(?:charitable\s+|annual\s+)?registration)\b",
        status_text,
        re.I,
    ))


def result_fields_indicate_exempt(result) -> bool:
    """Use this for states where the page body has generic exemption language."""
    status_text = " ".join([
        result.status or "",
        result.raw_status_text or "",
        result.source_note or "",
    ])
    return bool(re.search(r"\bexempt\b", status_text, re.I))


def md_detail_page_matched(result, text: str) -> bool:
    readable = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    readable = re.sub(r"\s+", " ", readable)
    ein_digits = re.sub(r"\D", "", result.ein or "")
    readable_digits = re.sub(r"\D", "", readable)
    source_note = result.source_note or ""
    if re.search(r"EIN-confirmed public registry search", source_note, re.I):
        return bool(re.search(r"SOS\s+Charity\s+Organization\s+Record|Charity\s+Name|Registration\s+Status", readable, re.I))
    if re.search(r"exact-name public registry search", source_note, re.I):
        normalize = getattr(checker, "normalize_name", lambda value: re.sub(r"\s+", " ", (value or "").lower()).strip())
        raw_name = re.sub(r"\s+", " ", result.organization_name or "").strip()
        name_variants = [
            raw_name,
            re.sub(r",\s*the\s*$", "", raw_name, flags=re.I).strip(),
            re.sub(r"^the\s+", "", raw_name, flags=re.I).strip(),
            re.sub(r"\bincorporated\b", "inc", raw_name, flags=re.I).strip(),
        ]
        names = [normalize(value) for value in name_variants if normalize(value)]
        readable_name = normalize(readable)
        return bool(
            re.search(r"SOS\s+Charity\s+Organization\s+Record|Charity\s+Name|Registration\s+Status", readable, re.I)
            and any(name and name in readable_name for name in names)
        )
    if ein_digits and ein_digits not in readable_digits:
        return False
    exposes_ein = bool(
        re.search(r"\b(?:EIN|FEIN|Federal\s+Tax|Tax\s+ID|Employer\s+Identification)\b", readable, re.I)
        or re.search(r"\b\d{2}[-\s]?\d{7}\b|\b\d{9}\b", readable)
    )
    if exposes_ein and ein_digits and ein_digits not in readable_digits:
        return False
    if re.search(r"\b[1-9]\d*\s+records?\b", readable, re.I) and not re.search(r"No\s+results\s+found|0\s+records?", readable, re.I):
        return True
    if not re.search(r"SOS\s+Charity\s+Organization\s+Record|Charity\s+Name|Registration\s+Status", readable, re.I):
        return False
    if re.search(r"SoS\s+Charities\s+-\s+Public\s+Registry[\s\S]{0,600}No\s+results\s+found", readable, re.I):
        return False
    if re.search(r"SOS\s+Charity\s+Organization\s+Record\s+for", readable, re.I):
        return True
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
        r"(?:due date|renewal due|filing due|annual report due|registration expires|registration expiration|expiration date|expires on|expired on|expires|expired)\s*:?\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})",
        r"(?:due date|renewal due|filing due|annual report due|registration expires|registration expiration|expiration date|expires on|expired on|expires|expired)\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})",
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
        rf"(?:expires|expired|expired on|expiration date|registration expires|automatic extension)\s*:?\s*([A-Za-z]{{3,9}}\s+\d{{1,2}},\s+\d{{4}})",
        rf"(?:expires|expired|expired on|expiration date|registration expires|automatic extension)\s*:?\s*(\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{4}})",
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


def explicit_adverse_registry_status(result, body: str) -> str:
    """Return registry-adverse statuses that should trump filing-year math."""
    state = (result.state or "").upper()
    text = combined_result_text(result, body)
    raw_fields = " ".join([
        result.raw_status_text or "",
        result.source_note or "",
    ])
    fields = raw_fields
    primary_status_fields = " ".join([
        result.status or "",
        result.raw_status_text or "",
    ])
    if (
        re.search(r"\b(active|current|compliant|good\s+standing)\b", primary_status_fields, re.I)
        and not re.search(
            r"\b(revoked|suspended|not\s+authorized\s+to\s+solicit|may\s+not\s+(?:solicit|raise\s+funds|operate)|cease\s+and\s+desist|pending|failed\s+to\s+renew|withdrawn|retired|terminated|cancelled|canceled|voluntar(?:y|ily)\s+deactivat(?:ed|ion)|closed|inactive)\b",
            primary_status_fields,
            re.I,
        )
    ):
        return ""
    labeled_status_text = " ".join(
        match.group(0)
        for match in re.finditer(
            r"\b(?:registry\s+status|registration\s+status|registration\s+filing\s+status|status)\b[\s\S]{0,160}",
            text,
            re.I,
        )
    )
    status_evidence = " ".join([raw_fields, labeled_status_text])
    if result_explicitly_exempt(result):
        return ""
    confirmed = organization_record_confirmed(result, text) or md_detail_page_matched(result, text)
    withdrawn_pattern = r"\b(withdrawn|retired|terminated|cancelled|canceled|voluntar(?:y|ily)\s+deactivat(?:ed|ion))\b"
    closed_pattern = r"\b(closed|inactive)\b"
    terminal_pattern = rf"(?:{withdrawn_pattern}|{closed_pattern})"
    pending_pattern = r"\bpending\b"
    failed_to_renew_pattern = r"\bfailed\s+to\s+renew\b"
    if not confirmed and not re.search(r"\b(revoked|suspended|not\s+authorized\s+to\s+solicit|may\s+not\s+(?:solicit|raise\s+funds|operate)|cease\s+and\s+desist|pending)\b|" + terminal_pattern + "|" + failed_to_renew_pattern, status_evidence, re.I):
        return ""
    if state == "NJ":
        if re.search(r"\bnon[-\s]?compliant\b", status_evidence, re.I):
            return "Delinquent"
        if re.search(withdrawn_pattern, status_evidence, re.I):
            return "Closed / Withdrawn / Canceled"
        if re.search(closed_pattern, status_evidence, re.I):
            return "Closed / Withdrawn / Canceled"
        if re.search(r"\brevoked\b", status_evidence, re.I):
            return "Revoked"
        if re.search(r"\b(suspended|not\s+authorized\s+to\s+solicit|may\s+not\s+(?:solicit|raise\s+funds|operate)|cease\s+and\s+desist)\b", status_evidence, re.I):
            return "Suspended"
        if re.search(failed_to_renew_pattern, status_evidence, re.I):
            return "Failed to Renew"
        if re.search(pending_pattern, status_evidence, re.I):
            return "Pending"
        return ""
    if re.search(r"\brevoked\b", status_evidence, re.I):
        return "Revoked"
    if re.search(r"\b(suspended|not\s+authorized\s+to\s+solicit|may\s+not\s+(?:solicit|raise\s+funds|operate)|cease\s+and\s+desist)\b", status_evidence, re.I):
        return "Suspended"
    if re.search(failed_to_renew_pattern, status_evidence, re.I):
        return "Failed to Renew"
    if re.search(pending_pattern, status_evidence, re.I):
        return "Pending"
    if re.search(withdrawn_pattern, status_evidence, re.I):
        return "Closed / Withdrawn / Canceled"
    if re.search(closed_pattern, status_evidence, re.I):
        return "Closed / Withdrawn / Canceled"
    return ""


def explicit_no_registration_status(result, body: str) -> bool:
    """Return true when the matched registry response clearly says no registration exists."""
    text = combined_result_text(result, body)
    fields = " ".join([
        result.status or "",
        result.raw_status_text or "",
        result.source_note or "",
    ])
    no_registration_pattern = (
        r"\b(not\s+registered|not\s+found|no\s+(?:matching\s+)?(?:registration\s+)?record|"
        r"no\s+(?:matching\s+)?results?|0\s+records?|0\s+results?)\b"
    )
    if re.search(no_registration_pattern, fields, re.I):
        return True
    return bool(re.search(
        r"\b(?:registry\s+status|registration\s+status|registration\s+filing\s+status|status)\b"
        r"[\s\S]{0,140}"
        r"\b(not\s+registered|not\s+found|no\s+(?:matching\s+)?(?:registration\s+)?record)\b",
        text,
        re.I,
    ))


def true_status_from_body(result, body: str) -> str:
    base_status = public_status(result)
    normalized = base_status.lower()
    state = (result.state or "").upper()
    combined = combined_result_text(result, body)
    combined_lower = combined.lower()

    if "site not reachable" in normalized:
        return base_status
    if result_explicitly_exempt(result):
        return "Exempt"
    if explicit_no_registration_status(result, combined):
        return "Not Registered"
    adverse_status = explicit_adverse_registry_status(result, combined)
    if adverse_status:
        return adverse_status
    primary_registry_fields = " ".join([result.raw_status_text or "", result.source_note or ""])
    if re.search(r"\b(non[-\s]?compliant|delinquent)\b", primary_registry_fields, re.I):
        return "Delinquent"
    if state == "ME" and re.search(r"\bACTIVE\b", " ".join([result.status or "", result.raw_status_text or ""]), re.I) and not explicit_registry_date(result, combined):
        return "Unknown"
    if normalized == "suspended":
        return "Suspended"
    if normalized == "revoked":
        return "Revoked"
    if normalized == "pending":
        return "Pending"
    if normalized == "failed to renew":
        return "Failed to Renew"
    if normalized in {"withdrawn", "closed", "closed / withdrawn / canceled"}:
        return "Closed / Withdrawn / Canceled"

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
        filed_cycle_status = status_for_filed_cycle(state, context, registry_date)
        if filed_cycle_status:
            return filed_cycle_status
        if stale_represented_year_is_delinquent(represented_year):
            return "Delinquent"
        if due_date and represented_year:
            return status_from_calendar_date(due_date)
        if re.search(r"Registration\s+Status\s+Current|Registration\s+Status[^A-Za-z0-9]{0,40}Current", combined, re.I):
            return "Current"

    record_confirmed = organization_record_confirmed(result, combined) or (state == "MD" and md_detail_page_matched(result, combined))

    if result_indicates_no_record(result):
        return "Not Registered"
    if state == "HI" and record_confirmed and (result_fields_indicate_exempt(result) or hi_indicates_exempt_registration(combined)):
        return "Exempt"
    if state not in {"HI", "NJ", "NY"} and record_confirmed and indicates_exempt_registration(combined):
        return "Exempt"
    if state == "NY" and record_confirmed and result_fields_indicate_exempt(result):
        return "Exempt"
    if state == "PA" and use_registry_date:
        return status_from_calendar_date(registry_date)
    if state == "PA" and record_confirmed and not use_registry_date:
        return "Delinquent"
    if state == "AK" and represented_year and due_date:
        return status_from_calendar_date(due_date)
    if state == "CA":
        ca_years = ca_annual_renewal_years_from_text(body)
        latest_not_submitted_year = ca_years.get("latest_not_submitted_year")
        latest_not_submitted_status = ca_years.get("latest_not_submitted_status") or "Not Submitted"
        latest_submitted_year = ca_years.get("latest_submitted_year")
        if latest_not_submitted_year and (not latest_submitted_year or latest_not_submitted_year > latest_submitted_year):
            return "Delinquent"
    if state in {"MA", "NY"} and represented_year and due_date and not result_indicates_no_record(result):
        return status_from_calendar_date(due_date)
    if state in EXTENSION_SCENARIO_STATES and record_confirmed and represented_year and due_date:
        return status_from_calendar_date(due_date)
    if state == "AK" and re.search(r"\b20\d{2}\s+registration\s+found\b", combined, re.I):
        found_years = [int(match.group(1)) for match in re.finditer(r"\b(20\d{2})\s+registration\s+found\b", combined, re.I)]
        if found_years and current_cycle_already_filed(state, max(found_years), registry_date):
            return status_for_filed_cycle(state, context, registry_date) or "Current"
    if represented_year_is_registry_evidenced(result, body, represented_year) and current_cycle_already_filed(state, represented_year, registry_date):
        if not re.search(r"\b(delinquent|expired|revoked|suspended|closed|inactive|overdue|non[- ]?compliant)\b", combined_lower, re.I):
            return status_for_filed_cycle(state, context, registry_date) or "Current"
    if state == "HI" and record_confirmed and represented_year and represented_year >= date.today().year - 1 and re.search(r"\bActive\b", combined, re.I):
        return status_for_filed_cycle(state, context, registry_date) or "Current"
    if state == "HI" and record_confirmed and not represented_year and re.search(r"\bActive\b", combined, re.I):
        return "Delinquent"
    if state == "MA" and record_confirmed and represented_year and represented_year >= date.today().year - 1 and re.search(r"Annual\s+Filings?\s+not\s+visible", combined, re.I):
        return status_for_filed_cycle(state, context, registry_date) or "Current"
    if use_registry_date:
        return status_from_calendar_date(registry_date)
    labeled_dates = [] if state == "CA" else labeled_due_dates_from_text(combined)
    if labeled_dates:
        return status_from_calendar_date(labeled_dates[0])
    if annual_filings_absent(combined):
        return "Delinquent" if record_confirmed else "Not Registered"
    if body_indicates_no_organization_record(combined) and not record_confirmed:
        return "Not Registered"
    if record_confirmed and stale_represented_year_is_delinquent(represented_year):
        return "Delinquent"

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
            return "Local DNS/network resolution failed while trying to reach the public registry host. This is usually a local network/DNS issue; rerun CharityClarity after the connection stabilizes."
        if re.search(r"timed out|timeout", technical_error, re.I):
            return "The public registry did not respond before the lookup timed out. Rerun CharityClarity to confirm whether this was temporary."
        return "Public registry site could not be reached at the time of the CharityClarity check."
    if normalized_status == "not registered":
        return f"The {state} public registry was reachable, but no matching registration record was found for the organization/EIN searched."
    if normalized_status == "unknown":
        if state == "ME" and re.search(r"\bACTIVE\b", " ".join([result.status or "", result.raw_status_text or ""]), re.I):
            return "The ME public registry returned an active matching organization record, but CharityClarity did not identify an expiration or renewal date needed for the interpreted status."
        if state == "PA" and organization_record_confirmed(result, combined_result_text(result, body)):
            return "The PA public registry returned a matching record, but CharityClarity did not identify a usable expiration date or final interpreted status from the available page."
        return f"The {state} public registry was reachable, but CharityClarity could not confirm a final interpreted status from the available registry page."
    if normalized_status == "exempt":
        return f"The {state} public registry indicates the organization is exempt from charitable registration or annual filing requirements in that state."
    if normalized_status == "revoked":
        return f"The {state} public registry shows the organization registration status as Revoked, which CharityClarity treats as an adverse status."
    if normalized_status == "suspended":
        if state == "VA" and re.search(r"not\s+authorized\s+to\s+solicit", combined_result_text(result, body), re.I):
            return "The VA public registry shows the organization is not authorized to solicit in Virginia, which CharityClarity treats as Suspended."
        return f"The {state} public registry shows the organization registration status as Suspended."
    if normalized_status == "pending":
        return (
            f"The {state} public registry shows the organization registration status as Pending. "
            "CharityClarity uses that registry status instead of calculating status from annual filing records."
        )
    if normalized_status == "failed to renew":
        return (
            f"The {state} public registry shows the organization registration status as Failed to Renew. "
            "CharityClarity uses that registry status instead of calculating status from annual filing records."
        )
    if normalized_status in {"withdrawn", "closed", "closed / withdrawn / canceled"}:
        if re.search(r"voluntar(?:y|ily)\s+deactivat(?:ed|ion)", combined_result_text(result, body), re.I):
            return (
                f"The {state} public registry shows the organization registration status as Voluntarily Deactivated. "
                "CharityClarity treats that as Closed / Withdrawn / Canceled instead of calculating status from older annual filing records."
            )
        if re.search(r"\bcancell?ed\b", combined_result_text(result, body), re.I):
            return (
                f"The {state} public registry shows the organization registration status as Canceled. "
                "CharityClarity treats that as Closed / Withdrawn / Canceled instead of calculating status from older annual filing records."
            )
        return (
            f"The {state} public registry shows the organization registration status as Closed, Withdrawn, Canceled, or inactive. "
            "CharityClarity uses that registry status instead of calculating status from older annual filing records."
        )
    if state == "CA" and normalized_status == "current" and not context.get("due_date"):
        return "The CA public registry shows Registry Status Current. CharityClarity did not identify a delinquency in this quick check."
    if state == "MD" and normalized_status == "current" and not context.get("represented_year"):
        return (
            "The MD public registry shows Registration Status: Current. CharityClarity did not identify a Maryland filing-year value "
            "from the public snapshot, so this quick check treats the registry status as Current without citing a specific annual filing year."
        )
    if normalized_status == "delinquent" and re.search(r"\b(closed|inactive)\b", " ".join([result.status or "", result.raw_status_text or ""]), re.I):
        return f"The {state} public registry shows a found organization record with a closed or inactive registration status."
    if normalized_status == "delinquent" and state == "VA" and re.search(r"not\s+authorized\s+to\s+solicit", " ".join([result.status or "", result.raw_status_text or "", result.source_note or ""]), re.I):
        return "The VA public registry shows the organization is not authorized to solicit in Virginia, which CharityClarity treats as Delinquent."
    if state == "AK" and normalized_status in {"upcoming filing", "current", "delinquent"} and context.get("represented_year") and context.get("due_date"):
        timing = "within 6 months" if normalized_status == "upcoming filing" else ("overdue" if normalized_status == "delinquent" else "not within the next 6 months")
        return (
            f"The AK public registry shows the {context['represented_year']} charitable organization registration/renewal is on file. "
            f"The next Alaska charitable registration renewal is due {format_date(context.get('due_date'))}, which is {timing}."
        )
    registry_noncompliant_text = " ".join([result.raw_status_text or "", result.source_note or "", body or ""])
    if normalized_status == "delinquent" and re.search(r"\bnon[-\s]?compliant\b", registry_noncompliant_text, re.I):
        return f"The {state} public registry shows a Noncompliant status, which CharityClarity treats as Delinquent."
    if normalized_status == "delinquent" and state == "PA" and organization_record_confirmed(result, combined_result_text(result, body)) and not explicit_registry_date(result, body):
        return "The PA public registry returned a matching organization record but did not show a current usable expiration date, so CharityClarity treats the record as Delinquent."
    if state == "CO" and normalized_status == "delinquent" and re.search(r"\b(expired|may not solicit)\b", combined_result_text(result, body), re.I):
        registry_date = explicit_registry_date(result, body)
        if registry_date:
            return f"The CO public registry shows an expiration date of {format_date(registry_date)}, which is overdue."
        return "The CO public registry shows an expired registration status, which CharityClarity treats as Delinquent."
    if state == "CA" and normalized_status == "delinquent":
        context = filing_context(result, body)
        ca_years = ca_annual_renewal_years_from_text(body)
        latest_not_submitted_year = ca_years.get("latest_not_submitted_year")
        latest_not_submitted_status = ca_years.get("latest_not_submitted_status") or "Not Submitted"
        latest_submitted_year = ca_years.get("latest_submitted_year")
        if latest_not_submitted_year:
            fiscal_end = context.get("fiscal_end") or fiscal_year_end_for_ein(result.ein)
            due_sentence = ""
            if fiscal_end:
                due_options = filing_due_date_options("CA", latest_not_submitted_year, fiscal_end)
                base_due = due_options.get("base_due") or due_options.get("effective_due")
                extended_due = due_options.get("extended_due")
                if base_due:
                    due_sentence = (
                        f" Based on a {fiscal_end[0]}/{fiscal_end[1]} fiscal year end, the "
                        f"{latest_not_submitted_year} annual renewal initial due date is {format_date(base_due)}."
                    )
                if extended_due:
                    extended_status = status_from_calendar_date(extended_due)
                    due_sentence += (
                        f" If a six-month extension was applied for and approved, the due date becomes "
                        f"{format_date(extended_due)} and the status becomes {extended_status}."
                    )
            submitted_sentence = (
                f" The latest accepted annual renewal year identified is {latest_submitted_year}."
                if latest_submitted_year else
                " CharityClarity did not identify a later accepted annual renewal year."
            )
            return (
                f"The CA Annual Renewal Data shows the {latest_not_submitted_year} annual renewal with Status of Filing: {latest_not_submitted_status}."
                f"{submitted_sentence}{due_sentence} CharityClarity treats the organization as Delinquent."
            )
    if normalized_status == "delinquent" and annual_filings_absent(combined_result_text(result, body)):
        return (
            f"The {state} public registry detail page shows the organization record, but the annual filing section shows no annual filings available "
            "and the CharityClarity check does not show an exempt registration status."
        )
    if normalized_status == "delinquent" and state == "HI" and not context.get("represented_year"):
        return (
            "The HI public registry shows an active organization record, but CharityClarity did not identify a visible annual filing year "
            "from the annual filing/document section and the record does not show an exempt registration status."
        )
    if normalized_status == "delinquent" and stale_represented_year_is_delinquent(context.get("represented_year")) and not context.get("due_date"):
        return (
            f"The {state} public registry detail page shows the organization record and the most recent fiscal/filing year identified is "
            f"{context.get('represented_year')}. The available CharityClarity check did not provide enough fiscal year-end information to calculate a precise due date, "
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
    if state == "PA" and use_registry_date and normalized_status in {"upcoming filing", "current", "delinquent"}:
        registry_status = status_from_calendar_date(registry_date).lower()
        if registry_status == "upcoming filing":
            return f"The PA public registry shows an expiration date of {format_date(registry_date)}, which is within 6 months."
        if registry_status == "current":
            return f"The PA public registry shows an expiration date of {format_date(registry_date)}, which is not within the next 6 months."
        return f"The PA public registry shows an expiration date of {format_date(registry_date)}, which is overdue."
    if normalized_status == "current" and current_cycle_already_filed(state, context.get("represented_year"), registry_date):
        if state == "AK":
            return (
                f"The AK public registry shows the {context['represented_year']} charitable organization registration/renewal is on file. "
                f"The next Alaska charitable registration renewal is due {format_date(context.get('due_date'))}, which is not within the next 6 months."
            )
        filing_label = "annual filing"
        if state == "MA":
            filing_label = "Form PC"
        elif state == "MD":
            filing_label = "annual filing"
        elif state == "CA":
            filing_label = "annual renewal"
        elif state == "HI":
            filing_label = "annual filing"
        if context.get("due_date") and context.get("fiscal_end"):
            extension_sentence = ""
            extended_due = context.get("extended_due_date")
            if extended_due:
                extended_status = status_from_calendar_date(extended_due)
                if state == "MD":
                    extension_sentence = f" If Maryland's automatic extension applies, the due date becomes {format_date(extended_due)} and the status becomes {extended_status}."
                elif state in EXTENSION_SCENARIO_STATES:
                    extension_sentence = f" If a six-month extension was applied for and approved, the due date becomes {format_date(extended_due)} and the status becomes {extended_status}."
            return (
                f"{context['represented_year']} appears to be the most recent {state} {filing_label} year identified in the CharityClarity check. "
                f"Based on a {context['fiscal_end'][0]}/{context['fiscal_end'][1]} fiscal year end, the {context['next_report_year']} {filing_label} initial due date is {format_date(context['due_date'])}. "
                f"CE Status is Current based on the initial due date.{extension_sentence}"
            )
        return (
            f"The {state} public registry shows a {context['represented_year']} {filing_label} on record. "
            f"Based on the filing year identified in this CharityClarity check, no {state} charitable filing appears overdue for the period reviewed, so CharityClarity treats the organization as Current."
        )
    if normalized_status == "upcoming filing" and current_cycle_already_filed(state, context.get("represented_year"), registry_date) and context.get("due_date"):
        extension_sentence = ""
        extended_due = context.get("extended_due_date")
        if extended_due:
            extended_status = status_from_calendar_date(extended_due)
            if state == "MD":
                extension_sentence = f" If Maryland's automatic extension applies, the due date becomes {format_date(extended_due)} and the status becomes {extended_status}."
            elif state in EXTENSION_SCENARIO_STATES:
                extension_sentence = f" If a six-month extension was applied for and approved, the due date becomes {format_date(extended_due)} and the status becomes {extended_status}."
        if state == "AK":
            return (
                f"The AK public registry shows the {context['represented_year']} charitable organization registration/renewal is on file. "
                f"The next Alaska charitable registration renewal is due {format_date(context.get('due_date'))}, which is within 6 months."
            )
        return (
            f"The {state} public registry shows a {context.get('represented_year')} filing or renewal on record. "
            f"The next required filing is due {format_date(context.get('due_date'))}, which is within 6 months.{extension_sentence}"
        )
    if use_registry_date and normalized_status in {"upcoming filing", "current", "delinquent"}:
        descriptor = "expiration or renewal date"
        if state == "AK":
            descriptor = "registration expiration date"
        elif state == "VA":
            descriptor = "registration extended-until date" if re.search(r"Registration\s+Extended\s+Until", result.source_note or "", re.I) else "registration expiration date"
        elif state in {"CO", "PA"}:
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
                if state == "NJ":
                    nj_status = status_from_calendar_date(base_due)
                    fiscal_end = context["fiscal_end"]
                    report_year = context["next_report_year"]
                    fy_end = date(report_year, fiscal_end[0], fiscal_end[1])
                    return (
                        f"{context['represented_year']} appears to be the most recent New Jersey filing year identified in the CharityClarity check. "
                        f"Based on a {fiscal_end[0]}/{fiscal_end[1]} fiscal year end, the next New Jersey annual filing is for FY ending {format_date(fy_end)} "
                        f"and is due {format_date(base_due)}. CE Status is {nj_status}."
                    )
                if state == "MD":
                    extension_label = "Maryland automatic extension"
                elif state == "MA":
                    extension_label = "Massachusetts six-month extension"
                else:
                    extension_label = "six-month extension"
                if state == "MD":
                    status_sentence = (
                        f"CE Status is {base_status} based on the initial due date. "
                        f"If Maryland's automatic extension was processed, the due date would be {format_date(extended_due)} "
                        f"and the status would be {extended_status} under that extension scenario."
                    )
                else:
                    status_sentence = (
                        f"CE Status is {base_status} based on the base due date. "
                        f"If the {extension_label} was granted, the extended deadline would be {format_date(extended_due)} and the status would be {extended_status}."
                    )
                return (
                    f"{context['represented_year']} appears to be the most recent {state} filing year identified in the CharityClarity check. "
                    f"Based on a {context['fiscal_end'][0]}/{context['fiscal_end'][1]} fiscal year end, the {context['next_report_year']} {filing_name} initial due date is {format_date(base_due)}. "
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
            if state == "NJ":
                due_date = context["due_date"]
                calculated_status = status_from_calendar_date(due_date)
                fiscal_end = context["fiscal_end"]
                report_year = context["next_report_year"]
                fy_end = date(report_year, fiscal_end[0], fiscal_end[1])
                return (
                    f"{context['represented_year']} appears to be the most recent New Jersey filing year identified in the CharityClarity check. "
                    f"Based on a {fiscal_end[0]}/{fiscal_end[1]} fiscal year end, the next New Jersey annual filing is for FY ending {format_date(fy_end)} "
                    f"and is due {format_date(due_date)}. CE Status is {calculated_status}."
                )
            return context["comment"]
    if normalized_status == "upcoming filing":
        return "A filing or renewal appears to be due soon based on the CharityClarity check."
    if normalized_status == "current":
        return "No delinquency was identified in the CharityClarity check."
    if "delinquent" in normalized_status or "non-compliant" in normalized_status:
        return "The CharityClarity check indicates a delinquency."
    return "Review the CharityClarity result for additional details."


def adjudicated_override_for_result(result) -> str:
    ein_digits = re.sub(r"\D", "", result.ein or "")
    state = (result.state or "").upper()
    return ADJUDICATED_STATUS_OVERRIDES.get((ein_digits, state), "")


def adjudicated_comment_for_status(result, body: str, status: str) -> str:
    state = (result.state or "the selected state").upper()
    normalized = status.lower()
    if normalized == "not registered":
        return f"The {state} public registry was reachable, but no matching registration record was found for the organization/EIN searched."
    if normalized == "suspended":
        return f"The {state} public registry shows the organization registration status as Suspended."
    if normalized == "delinquent":
        if state == "NJ":
            return "The NJ public registry shows a Noncompliant status, which CharityClarity treats as Delinquent."
        if state == "PA":
            return "The PA public registry returned a matching organization record but did not show a current usable expiration date, so CharityClarity treats the record as Delinquent."
        if state == "CA":
            context = filing_context(result, body)
            ca_years = ca_annual_renewal_years_from_text(body)
            latest_not_submitted_year = ca_years.get("latest_not_submitted_year")
            latest_submitted_year = ca_years.get("latest_submitted_year")
            if latest_not_submitted_year:
                fiscal_end = context.get("fiscal_end") or fiscal_year_end_for_ein(result.ein)
                due_sentence = ""
                if fiscal_end:
                    due_options = filing_due_date_options("CA", latest_not_submitted_year, fiscal_end)
                    base_due = due_options.get("base_due_date") or due_options.get("base_due") or due_options.get("effective_due")
                    extended_due = due_options.get("extended_due")
                    if base_due:
                        due_sentence = (
                            f" Based on a {fiscal_end[0]}/{fiscal_end[1]} fiscal year end, the "
                            f"{latest_not_submitted_year} annual renewal initial due date is {format_date(base_due)}."
                        )
                    if extended_due:
                        extended_status = status_from_calendar_date(extended_due)
                        due_sentence += (
                            f" If a six-month extension was applied for and approved, the due date becomes "
                            f"{format_date(extended_due)} and the status becomes {extended_status}."
                        )
                submitted_sentence = (
                    f" The most recent CA annual renewal CharityClarity identified as submitted/accepted is {latest_submitted_year}."
                    if latest_submitted_year else
                    " CharityClarity did not identify a submitted/accepted CA annual renewal year in the available Annual Renewal Data."
                )
                return (
                    f"The CA Annual Renewal Data shows the {latest_not_submitted_year} annual renewal with Status of Filing: Not Submitted."
                    f"{submitted_sentence}{due_sentence} CharityClarity treats the organization as Delinquent."
                )
            if context.get("represented_year") and context.get("fiscal_end") and context.get("due_date"):
                extension_sentence = ""
                extended_due = context.get("extended_due_date")
                if extended_due:
                    extended_status = status_from_calendar_date(extended_due)
                    extension_sentence = (
                        f" If a six-month extension was applied for and approved, the due date becomes "
                        f"{format_date(extended_due)} and the status becomes {extended_status}."
                    )
                return (
                    f"{context['represented_year']} appears to be the most recent CA annual renewal year identified in the CharityClarity check. "
                    f"Based on a {context['fiscal_end'][0]}/{context['fiscal_end'][1]} fiscal year end, the "
                    f"{context['next_report_year']} annual renewal initial due date is {format_date(context['due_date'])}. "
                    "The CA public registry indicates a delinquency, so CharityClarity treats the organization as Delinquent."
                    f"{extension_sentence}"
                )
            return "The CA public registry indicates a delinquency, so CharityClarity treats the organization as Delinquent."
        return f"The {state} public registry indicates a delinquency."
    return comments_for_result(result, "", status)


def run_state_lookup(organization_name: str, ein: str, state: str, capture_source_snapshot: bool = False) -> dict:
    lookup_started = time.perf_counter()
    artifact_name = organization_name or f"EIN {format_ein(ein)}"
    lookup_name = organization_name
    org = checker.Organization(organization_name=lookup_name, ein=ein)
    if hasattr(org, "evidence_mode"):
        org.evidence_mode = capture_source_snapshot
    body = ""
    proof_url = None

    result = None
    with checker.sync_playwright() as p:
        browser = None
        context = None
        page = None
        try:
            browser = p.chromium.launch(headless=True)
            if state == "AK":
                result, body = search_ak_with_registration_evidence(browser, org, artifact_name)
            else:
                context = browser.new_context()
                if state != "MA":
                    configure_browser_context(context)
                page = context.new_page()
            if state == "AK":
                pass
            elif state == "CA":
                result = checker.search_ca(page, org)
                if public_status(result) != "Not Registered":
                    body = ca_detail_body(page, org)
            elif state == "MA":
                result = checker.search_ma(page, org)
                body = ma_detail_body(page)
                result, body = repair_ma_false_not_registered(page, org, result, body)
            elif state == "MD":
                result = checker.search_md(page, org)
                md_body = registry_page_body(page)
                if public_status(result) != "Not Registered" and not md_detail_page_matched(result, md_body):
                    result.raw_status_text = "No matching EIN result"
                    result.status = checker.STATUS_NOT_REGISTERED
                    result.source_note = "Maryland search did not confirm a public registry record matching the requested EIN."
                    result.success = True
                    body = md_no_results_body(page)
                elif re.search(r"Maryland record found", " ".join([result.raw_status_text or "", result.source_note or ""]), re.I) and not capture_source_snapshot:
                    body = md_body
                elif md_detail_page_matched(result, md_body):
                    result.status = result.raw_status_text if result.raw_status_text and result.raw_status_text != "No matching EIN result" else checker.STATUS_UNKNOWN
                    result.raw_status_text = result.raw_status_text if result.raw_status_text not in {"No matching EIN result", "No record found"} else "Maryland record found"
                    result.source_note = "Maryland detail page was reached from the public registry search."
                    result.success = True
                    body = md_detail_body(page, deep=capture_source_snapshot)
                elif public_status(result) != "Not Registered":
                    body = md_detail_body(page, deep=capture_source_snapshot)
                else:
                    body = md_no_results_body(page)
            elif state == "CO":
                result = checker.search_co(page, org)
            elif state == "NY":
                result = search_with_name_variants(page, org, checker.search_ny, max_variants=25)
            elif state == "NJ":
                result = search_nj_direct(page, org)
                if public_status(result) != "Not Registered":
                    body = nj_detail_body(page, org)
            elif state == "PA":
                result = checker.search_pa(page, org)
            elif state == "VA":
                result = search_with_name_variants(
                    page,
                    org,
                    checker.search_va,
                    max_variants=18,
                    reject_va_suspended_from_leading_the_drop=False,
                    include_ein_aliases=False,
                    include_name_segments=False,
                    include_compact_legal_suffixes=False,
                )
            elif state == "SC":
                result = search_with_name_variants(
                    page,
                    org,
                    checker.search_sc,
                    max_variants=18,
                    include_ein_aliases=False,
                    include_name_segments=False,
                    include_compact_legal_suffixes=False,
                    include_leading_article_variants=False,
                )
            elif state == "HI":
                result = search_hi_precise(page, org)
                if public_status(result) != "Not Registered":
                    body = hi_detail_body(page)
            elif state == "ME":
                result = search_with_name_variants(
                    page,
                    org,
                    checker.search_me,
                    max_variants=18,
                    include_ein_aliases=False,
                    include_name_segments=False,
                    include_compact_legal_suffixes=False,
                    include_leading_article_variants=False,
                )
                me_status_source = " ".join([result.raw_status_text or "", result.source_note or ""])
                if re.search(r"Maine uses the Status shown|No matching organization|No record found|no matching", me_status_source, re.I):
                    body = registry_page_body(page)
                else:
                    body = me_detail_body(page, org)
                    enrich_me_result_from_body(result, body)
            elif state == "ND":
                result = search_with_name_variants(
                    page,
                    org,
                    checker.search_nd,
                    max_variants=18,
                    include_ein_aliases=False,
                    include_name_segments=False,
                    include_compact_legal_suffixes=False,
                    include_leading_article_variants=False,
                )
            else:
                raise ValueError(f"Unsupported state: {state}")
            if page:
                if not body:
                    body = registry_page_body(page)
                if CAPTURE_EVIDENCE_SCREENSHOTS:
                    checker.save_artifacts(
                        page,
                        ARTIFACTS_DIR,
                        state,
                        artifact_name,
                    )
                    if state in {"CA", "MD", "ME"}:
                        save_focused_viewport_artifact(page, state, artifact_name)
                elif CAPTURE_LIGHTWEIGHT_SOURCE_SNAPSHOT or capture_source_snapshot:
                    save_focused_viewport_artifact(page, state, artifact_name)
        except Exception as exc:
            log_error(f"{state} lookup for {format_ein(ein)} failed before completion: {exc}")
            result = checker.StateResult(organization_name or f"EIN {format_ein(ein)}", format_ein(ein), state, "Site Not Reachable", "")
            result.raw_status_text = "Lookup could not be completed"
            result.source_note = "Public registry lookup could not be completed."
            result.error = str(exc)
            result.success = False
        finally:
            if context:
                context.close()
            if browser:
                browser.close()

    if result is None:
        result = checker.StateResult(organization_name or f"EIN {format_ein(ein)}", format_ein(ein), state, "Site Not Reachable", "")
        result.raw_status_text = "Browser launch failed"
        result.source_note = "Public registry lookup could not start because the browser runtime was unavailable."
        result.error = "Browser launch failed"
        result.success = False

    result.source_note = source_note_for_result(result)
    data = checker.asdict(result)
    if organization_name:
        data["organization_name"] = organization_name
        result.organization_name = organization_name
    elif not (data.get("organization_name") or "").strip():
        data["organization_name"] = "Organization not identified"
        result.organization_name = data["organization_name"]
    data["status"] = true_status_from_body(result, body)
    override_status = adjudicated_override_for_result(result)
    if override_status:
        data["status"] = override_status
        data["comments"] = adjudicated_comment_for_status(result, body, override_status)
    else:
        data["comments"] = comments_for_result(result, body, data["status"])
    data["evidence_url"] = ""
    data["lookup_seconds"] = round(time.perf_counter() - lookup_started, 2)
    data["checked_at_epoch"] = int(time.time())
    data["app_version"] = APP_VERSION
    log_event(f"{state} lookup for {format_ein(ein)} finished in {data['lookup_seconds']}s with status {data.get('status')}")
    return data


def run_state_lookups_parallel(organizations: list[dict], states: list[str]) -> list[dict]:
    lookup_requests = [
        (org["organization_name"], org["ein"], st)
        for org in organizations
        for st in states
    ]
    if len(lookup_requests) <= 1:
        return [run_state_lookup(*lookup_requests[0])]

    worker_count = min(MAX_PARALLEL_LOOKUPS, len(lookup_requests))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        # executor.map preserves input order, so the table stays predictable.
        return list(executor.map(lambda args: run_state_lookup(*args), lookup_requests))


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
            parsed = urlparse(self.path)
            relative_path = unquote(parsed.path.removeprefix("/evidence/"))
            candidate = (ARTIFACTS_DIR / relative_path).resolve()
            artifacts_root = ARTIFACTS_DIR.resolve()
            if artifacts_root not in candidate.parents or candidate.suffix.lower() != ".pdf":
                self._send_json(404, {"error": "Evidence PDF not found."})
                return True
            try:
                relative_candidate = candidate.relative_to(artifacts_root)
                state = relative_candidate.parts[0].upper()
            except Exception:
                self._send_json(404, {"error": "Evidence PDF not found."})
                return True
            query = parse_qs(parsed.query)
            request_ein = format_ein((query.get("ein") or [""])[0])
            request_org = ((query.get("org") or [""])[0] or candidate.stem.replace("_", " ")).strip()
            metadata_candidate = candidate.with_suffix(".evidence.json")
            if not metadata_candidate.exists() and request_ein:
                prepare_name = request_org or candidate.stem.replace("_", " ")
                run_state_lookup(prepare_name, request_ein, state, capture_source_snapshot=True)
            should_prepare = not candidate.exists()
            if metadata_candidate.exists() and candidate.exists():
                should_prepare = metadata_candidate.stat().st_mtime > candidate.stat().st_mtime
            if ON_DEMAND_EVIDENCE_SCREENSHOT and metadata_candidate.exists() and not evidence_png_path(state, candidate.stem).exists():
                should_prepare = True
            if should_prepare:
                prepare_evidence_pdf(candidate)
            if not candidate.exists():
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

    def _send_landing_page(self, include_body: bool = True) -> None:
        page_path = Path(__file__).with_name("registry-snapshot-index.html")
        if page_path.exists():
            body = page_path.read_bytes()
            content_type = "text/html; charset=utf-8"
        else:
            body = (
                "<!doctype html><title>CharityClarity API</title>"
                "<h1>CharityClarity API is running.</h1>"
            ).encode("utf-8")
            content_type = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def do_HEAD(self) -> None:
        if self._send_lead_log(include_body=False):
            return

        if self._send_evidence_pdf(include_body=False):
            return

        if self.path in {"/", "/registry-snapshot", "/registry-snapshot/", "/api/check"}:
            self._send_landing_page(include_body=False)
            return

        self._send_json(404, {"error": "Open http://127.0.0.1:8765/ to use the registry snapshot page."})

    def do_GET(self) -> None:
        if self._send_lead_log(include_body=True):
            return

        if self._send_evidence_pdf(include_body=True):
            return

        if self.path in {"/", "/registry-snapshot", "/registry-snapshot/", "/api/check"}:
            self._send_landing_page(include_body=True)
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
            device_id = normalize_device_id(payload.get("device_id") or "")

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
                self._send_json(400, {"error": "Enter a valid 9-digit EIN and select one supported state."})
                return

            state_limit = state_limit_for_request(domain)
            org_limit = org_limit_for_request(email, domain)
            if len(states) > state_limit:
                self._send_json(400, {"error": "Select one state."})
                return
            if len(organizations) > org_limit:
                self._send_json(400, {"error": f"This email can submit up to {org_limit} organization{'s' if org_limit != 1 else ''} at a time."})
                return

            is_batch = isinstance(requested_states, list)
            if is_batch and not privileged and domain_is_limited(domain):
                self._send_json(429, {"error": "A complimentary snapshot was already requested for this email domain."})
                return
            if is_batch and not privileged and device_is_limited(device_id):
                self._send_json(429, {"error": "A complimentary snapshot was already requested from this browser."})
                return

            results = run_state_lookups_parallel(organizations, states)
            append_lead_log(email, results)
            if is_batch:
                if not privileged and should_record_domain_check(results):
                    record_domain_check(domain)
                    record_device_check(device_id)
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

