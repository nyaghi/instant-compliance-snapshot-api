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
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, quote, unquote, urlencode, urljoin, urlparse
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

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
STATE_EXTENSION_BUNDLE_PATH = (
    Path(os.environ["CE_STATE_EXTENSION_BUNDLE_PATH"])
    if os.environ.get("CE_STATE_EXTENSION_BUNDLE_PATH")
    else first_existing_path(
        str(BASE_DIR / "Charity_Checker_mi_oh_la_or_ar.py"),
        r"C:\Users\nyagh\Downloads\Charity_Checker_mi_oh_la_or_ar.py",
    )
)
LOG_PATH = Path(os.environ.get("CE_LOG_PATH", str(BASE_DIR / "registry_snapshot_server.log")))
LEAD_LOG_PATH = Path(__file__).with_name("registry_snapshot_leads.csv")
PIN_LOG_PATH = Path(__file__).with_name("registry_snapshot_passcodes.log")
LEAD_LOG_WEBHOOK_URL = os.environ.get("CE_LEAD_LOG_WEBHOOK_URL", "").strip()
LEAD_LOG_WEBHOOK_SECRET = os.environ.get("CE_LEAD_LOG_WEBHOOK_SECRET", "").strip()
LEAD_LOG_WEBHOOK_TIMEOUT_SECONDS = min(max(1.0, float(os.environ.get("CE_LEAD_LOG_WEBHOOK_TIMEOUT_SECONDS", "4"))), 8.0)
ARTIFACTS_DIR = Path(os.environ.get("CE_ARTIFACTS_DIR", str(BASE_DIR / "artifacts")))
PORT = int(os.environ.get("PORT", "8765"))
HOST = os.environ.get("HOST") or ("0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
PUBLIC_BASE_URL = (os.environ.get("PUBLIC_BASE_URL", f"http://127.0.0.1:{PORT}").splitlines()[0]).strip().rstrip("/")
APP_VERSION = "2026.05.23.3"
SUPPORTED_STATES = [
    "AK", "CA", "CO", "CT", "FL", "HI", "MA", "MD", "ME", "MI",
    "MN", "ND", "NJ", "NY", "OH", "OR", "PA", "SC", "VA", "WI",
]
EXTENSION_SCENARIO_STATES = {"CA", "CT", "HI", "KY", "MA", "MD", "NJ", "NY", "OH", "PA"}
MAX_STATES_PER_SNAPSHOT = len(SUPPORTED_STATES)

REQUESTED_PARALLEL_LOOKUPS = max(1, int(os.environ.get("CE_MAX_PARALLEL_LOOKUPS", "4")))
ALLOW_PARALLEL_BROWSER_LOOKUPS = os.environ.get("CE_ALLOW_PARALLEL_BROWSER_LOOKUPS", "1").strip().lower() in {"1", "true", "yes"}
MAX_BROWSER_LOOKUPS = max(1, int(os.environ.get("CE_MAX_BROWSER_LOOKUPS", "4")))
MAX_PARALLEL_LOOKUPS = min(REQUESTED_PARALLEL_LOOKUPS, MAX_BROWSER_LOOKUPS) if ALLOW_PARALLEL_BROWSER_LOOKUPS else 1
BROWSER_LOOKUP_SEMAPHORE = threading.BoundedSemaphore(MAX_BROWSER_LOOKUPS)
BLOCK_HEAVY_BROWSER_RESOURCES = os.environ.get("CE_BLOCK_HEAVY_BROWSER_RESOURCES", "1").strip().lower() not in {"0", "false", "no"}
EAGER_EVIDENCE_PDF = os.environ.get("CE_EAGER_EVIDENCE_PDF", "0").strip().lower() in {"1", "true", "yes"}
CAPTURE_EVIDENCE_SCREENSHOTS = os.environ.get("CE_CAPTURE_EVIDENCE_SCREENSHOTS", "0").strip().lower() in {"1", "true", "yes"}
CAPTURE_LIGHTWEIGHT_SOURCE_SNAPSHOT = os.environ.get("CE_CAPTURE_LIGHTWEIGHT_SOURCE_SNAPSHOT", "0").strip().lower() in {"1", "true", "yes"}
ON_DEMAND_EVIDENCE_SCREENSHOT = os.environ.get("CE_ON_DEMAND_EVIDENCE_SCREENSHOT", "1").strip().lower() not in {"0", "false", "no"}
LOOKUP_SOFT_MAX_SECONDS = min(max(20.0, float(os.environ.get("CE_LOOKUP_SOFT_MAX_SECONDS", "59"))), 59.0)
SC_NAME_VARIANT_MAX_SECONDS = max(12.0, float(os.environ.get("CE_SC_NAME_VARIANT_MAX_SECONDS", "25")))
NAME_SEARCH_VARIANT_MAX_SECONDS = max(18.0, float(os.environ.get("CE_NAME_SEARCH_VARIANT_MAX_SECONDS", "35")))
FL_LOOKUP_MAX_SECONDS = min(max(20.0, float(os.environ.get("CE_FL_LOOKUP_MAX_SECONDS", "45"))), 59.0)
SC_PREFLIGHT_TIMEOUT_SECONDS = min(max(3.0, float(os.environ.get("CE_SC_PREFLIGHT_TIMEOUT_SECONDS", "8"))), 10.0)
NAME_SEARCH_PREFLIGHT_TIMEOUT_SECONDS = min(max(3.0, float(os.environ.get("CE_NAME_SEARCH_PREFLIGHT_TIMEOUT_SECONDS", "8"))), 10.0)
ME_LOOKUP_MIN_INTERVAL_SECONDS = min(max(0.0, float(os.environ.get("CE_ME_LOOKUP_MIN_INTERVAL_SECONDS", "1.0"))), 20.0)
ME_NOT_REGISTERED_CONFIRMATION_DELAY_SECONDS = min(max(0.0, float(os.environ.get("CE_ME_NOT_REGISTERED_CONFIRMATION_DELAY_SECONDS", "1.0"))), 30.0)
ME_NOT_REGISTERED_CONFIRMATION_ATTEMPTS = min(max(1, int(os.environ.get("CE_ME_NOT_REGISTERED_CONFIRMATION_ATTEMPTS", "2"))), 4)
ME_CONFIRM_NOT_REGISTERED = os.environ.get("CE_ME_CONFIRM_NOT_REGISTERED", "1").strip().lower() in {"1", "true", "yes"}
MI_ENABLE_NAME_FALLBACK = os.environ.get("CE_MI_ENABLE_NAME_FALLBACK", "1").strip().lower() in {"1", "true", "yes"}
ENABLE_CROSS_STATE_NAME_RETRY = os.environ.get("CE_ENABLE_CROSS_STATE_NAME_RETRY", "0").strip().lower() in {"1", "true", "yes"}
CONFIRM_FRAGILE_BATCH_RESULTS = os.environ.get("CE_CONFIRM_FRAGILE_BATCH_RESULTS", "1").strip().lower() in {"1", "true", "yes"}
BATCH_CONFIRMATION_WORKERS = min(max(1, int(os.environ.get("CE_BATCH_CONFIRMATION_WORKERS", "3"))), 3)
BATCH_NO_MATCH_CONFIRMATION_DELAY_SECONDS = min(max(0.0, float(os.environ.get("CE_BATCH_NO_MATCH_CONFIRMATION_DELAY_SECONDS", "8"))), 20.0)
FL_NOT_REGISTERED_CONFIRMATION_DELAY_SECONDS = min(max(0.0, float(os.environ.get("CE_FL_NOT_REGISTERED_CONFIRMATION_DELAY_SECONDS", "8"))), 20.0)
NAME_SEARCH_PREFLIGHT_URLS = {
    "CT": "https://www.elicense.ct.gov/lookup/licenselookup.aspx",
    "FL": "https://csapp.fdacs.gov/CSPublicApp/CheckACharity/CheckACharity.aspx",
    "ME": "https://www.pfr.maine.gov/almsonline/almsquery/SearchCompany.aspx",
    "ND": "https://firststop.sos.nd.gov/search/charitable",
    "OR": "https://justice.oregon.gov/charities",
    "SC": "https://search.scsos.com/charities",
    "VA": "https://cos.vdacs.virginia.gov/cgi-bin/char_search.cgi",
}
ME_LOOKUP_LOCK = threading.Lock()
ME_LAST_LOOKUP_FINISHED = 0.0
VA_SEARCH_VARIANT_LOCK = threading.Lock()
BROWSER_USER_AGENT = os.environ.get(
    "CE_BROWSER_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
)
WI_SEARCH_URL = "https://apps.dfi.wi.gov/ice/berg/Registration/OrganizationCredentialSearch.aspx"
WI_RESULTS_URL = "https://apps.dfi.wi.gov/ice/berg/Registration/OrgCredentialSearchResults.aspx"
WI_READER_BASE_URL = os.environ.get("CE_WI_READER_BASE_URL", "https://r.jina.ai/http://")
WI_LOOKUP_MAX_SECONDS = min(max(20.0, float(os.environ.get("CE_WI_LOOKUP_MAX_SECONDS", "55"))), 90.0)
WI_READER_TIMEOUT_SECONDS = min(max(5.0, float(os.environ.get("CE_WI_READER_TIMEOUT_SECONDS", "12"))), 20.0)
WI_HTTP_TIMEOUT_SECONDS = min(max(5.0, float(os.environ.get("CE_WI_HTTP_TIMEOUT_SECONDS", "10"))), 20.0)
WI_DIRECT_VARIANT_LIMIT = min(max(3, int(os.environ.get("CE_WI_DIRECT_VARIANT_LIMIT", "8"))), 12)
WI_BROWSER_VARIANT_LIMIT = min(max(0, int(os.environ.get("CE_WI_BROWSER_VARIANT_LIMIT", "0"))), 5)
WI_SIDECAR_URL = os.environ.get("CE_WI_SIDECAR_URL", "").strip()
WI_LOOKUP_SECRET = os.environ.get("CE_WI_LOOKUP_SECRET", "").strip()
WI_SIDECAR_TIMEOUT_SECONDS = min(max(10.0, float(os.environ.get("CE_WI_SIDECAR_TIMEOUT_SECONDS", "45"))), 58.0)
WI_SIDECAR_ATTEMPTS = min(max(1, int(os.environ.get("CE_WI_SIDECAR_ATTEMPTS", "3"))), 5)
MAX_EXTERNAL_EXEMPT_ORGS = 3
DOMAIN_LIMIT_DAYS = 7
ADMIN_PASSCODE = "8977"
STAGING_ACCESS_REQUIRED = os.environ.get("CE_STAGING_ACCESS_REQUIRED", "0").strip().lower() in {"1", "true", "yes"}
PIN_EXPIRY_SECONDS = 10 * 60
PIN_MAX_ATTEMPTS = 5
VERIFICATION_TOKEN_SECONDS = 60 * 60
EXEMPT_EMAIL_DOMAIN = "compliance-express.com"
EXEMPT_EMAIL_ADDRESSES = {"nyaghi17@gmail.com"}
DOMAIN_LIMIT_PATH = Path(__file__).with_name("registry_snapshot_domain_limits.json")
DEVICE_LIMIT_PATH = Path(__file__).with_name("registry_snapshot_device_limits.json")
try:
    EASTERN_TZ = ZoneInfo("America/New_York")
except Exception:
    EASTERN_TZ = None
LEAD_LOG_FIELDNAMES = [
    "checked_at",
    "checked_at_timezone",
    "email",
    "domain",
    "organization_name",
    "ein",
    "state",
    "status",
    "comments",
    "lookup_seconds",
    "app_version",
    "evidence_url",
    "source_url",
    "environment",
    "origin",
    "page_url",
    "referrer",
    "remote_ip",
    "user_agent",
    "device_id",
    "submission_id",
]
PIN_STORE: dict[str, dict] = {}
VERIFICATION_TOKENS: dict[str, dict] = {}
ORG_NAME_CACHE: dict[str, str] = {}
PUBLIC_PROFILE_CACHE: dict[str, dict] = {}
def load_checker():
    spec = importlib.util.spec_from_file_location("charity_state_checker_v9", CHECKER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load checker from {CHECKER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = load_checker()
STATE_EXTENSION_BUNDLE = None
STATE_EXTENSION_MODULES: dict[str, object] = {}


def load_state_extension_bundle():
    global STATE_EXTENSION_BUNDLE
    if STATE_EXTENSION_BUNDLE is not None:
        return STATE_EXTENSION_BUNDLE
    if not STATE_EXTENSION_BUNDLE_PATH.exists():
        raise RuntimeError(f"State extension bundle not found: {STATE_EXTENSION_BUNDLE_PATH}")
    spec = importlib.util.spec_from_file_location("charity_state_extension_bundle", STATE_EXTENSION_BUNDLE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load state extension bundle from {STATE_EXTENSION_BUNDLE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    STATE_EXTENSION_BUNDLE = module
    return module


def state_extension_module(state: str):
    state = (state or "").upper()
    if state in STATE_EXTENSION_MODULES:
        return STATE_EXTENSION_MODULES[state]
    bundle = load_state_extension_bundle()
    module = bundle.load_module(state)
    STATE_EXTENSION_MODULES[state] = module
    return module


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


def append_master_lead_log(rows: list[dict]) -> None:
    if not LEAD_LOG_WEBHOOK_URL or not rows:
        return
    payload = {
        "secret": LEAD_LOG_WEBHOOK_SECRET,
        "app_version": APP_VERSION,
        "rows": rows,
    }
    try:
        request = urllib.request.Request(
            LEAD_LOG_WEBHOOK_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "CharityClarityLeadLogger/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=LEAD_LOG_WEBHOOK_TIMEOUT_SECONDS) as response:
            response.read(200)
    except Exception as exc:
        log_error(f"Master lead log webhook failed: {exc}")


def append_master_lead_log_async(rows: list[dict]) -> None:
    if not LEAD_LOG_WEBHOOK_URL or not rows:
        return
    thread = threading.Thread(target=append_master_lead_log, args=(rows,), daemon=True)
    thread.start()


def eastern_timestamp() -> tuple[str, str]:
    now = datetime.now(EASTERN_TZ) if EASTERN_TZ else datetime.now().astimezone()
    tz_name = now.tzname() or "Eastern"
    tz_label = "EDT" if "daylight" in tz_name.lower() else ("EST" if "standard" in tz_name.lower() else tz_name)
    return f"{now:%Y-%m-%d %H:%M:%S} {tz_label}", tz_label


def safe_audit_value(value: object, max_length: int = 500) -> str:
    return re.sub(r"[\r\n\t]+", " ", str(value or "")).strip()[:max_length]


def first_header_ip(headers) -> str:
    for name in ("CF-Connecting-IP", "X-Forwarded-For", "X-Real-IP"):
        value = headers.get(name, "")
        if value:
            return safe_audit_value(value.split(",")[0], 80)
    return ""


def request_audit_context(handler: BaseHTTPRequestHandler, payload: dict) -> dict:
    origin = safe_audit_value(payload.get("origin") or handler.headers.get("Origin", ""), 300)
    page_url = safe_audit_value(payload.get("page_url") or "", 500)
    referrer = safe_audit_value(payload.get("referrer") or handler.headers.get("Referer", ""), 500)
    environment = safe_audit_value(payload.get("environment") or "", 80)
    if not environment:
        environment = "staging" if "staging" in f"{origin} {page_url}".lower() else "production"
    remote_ip = first_header_ip(handler.headers)
    if not remote_ip and handler.client_address:
        remote_ip = safe_audit_value(handler.client_address[0], 80)
    return {
        "environment": environment,
        "origin": origin,
        "page_url": page_url,
        "referrer": referrer,
        "remote_ip": remote_ip,
        "user_agent": safe_audit_value(handler.headers.get("User-Agent", "") or payload.get("client_user_agent", ""), 500),
        "device_id": normalize_device_id(payload.get("device_id") or ""),
        "submission_id": secrets.token_hex(8),
    }


def ensure_lead_log_header(fieldnames: list[str]) -> None:
    if not LEAD_LOG_PATH.exists() or LEAD_LOG_PATH.stat().st_size == 0:
        return
    try:
        with LEAD_LOG_PATH.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            existing = reader.fieldnames or []
            if existing == fieldnames:
                return
            rows = list(reader)
        with LEAD_LOG_PATH.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in fieldnames})
    except Exception as exc:
        log_error(f"Lead log header migration failed: {exc}")


def append_lead_log(email: str, results: list[dict], audit_context: dict | None = None) -> None:
    if not email or not results:
        return
    LEAD_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = LEAD_LOG_FIELDNAMES
    ensure_lead_log_header(fieldnames)
    write_header = not LEAD_LOG_PATH.exists() or LEAD_LOG_PATH.stat().st_size == 0
    checked_at, checked_at_timezone = eastern_timestamp()
    domain = email_domain(email)
    audit_context = audit_context or {}
    master_rows = []
    with LEAD_LOG_PATH.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        for result in results:
            row = {
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
                "lookup_seconds": result.get("lookup_seconds", ""),
                "app_version": result.get("app_version", APP_VERSION),
                "checked_at_timezone": checked_at_timezone,
                "environment": audit_context.get("environment", ""),
                "origin": audit_context.get("origin", ""),
                "page_url": audit_context.get("page_url", ""),
                "referrer": audit_context.get("referrer", ""),
                "remote_ip": audit_context.get("remote_ip", ""),
                "user_agent": audit_context.get("user_agent", ""),
                "device_id": audit_context.get("device_id", ""),
                "submission_id": audit_context.get("submission_id", ""),
            }
            writer.writerow({key: row.get(key, "") for key in fieldnames})
            master_rows.append(row)
    append_master_lead_log_async(master_rows)


def append_submission_log(email: str, organizations: list[dict], states: list[str], audit_context: dict | None = None) -> None:
    """Capture valid usage before the slower registry lookups begin."""
    if not email or not organizations or not states:
        return
    rows = []
    for org in organizations:
        ein = org.get("ein", "")
        organization_name = org.get("organization_name") or f"EIN {ein}"
        for state in states:
            rows.append({
                "organization_name": organization_name,
                "ein": ein,
                "state": state,
                "status": "Lookup Started",
                "comments": "Submission received. CharityClarity started the public registry lookup.",
                "source_url": "",
                "lookup_seconds": "",
                "app_version": APP_VERSION,
            })
    append_lead_log(email, rows, audit_context)


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


def staging_access_error(email_address: str, passcode: str) -> str:
    if not STAGING_ACCESS_REQUIRED:
        return ""
    if not is_exempt_domain(email_domain(email_address)):
        return "Staging access requires a Compliance Express email address."
    if (passcode or "").strip() != ADMIN_PASSCODE:
        return "Enter the Compliance Express passcode to use staging."
    return ""


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


def usage_limit_key(identifier: str, ein: str) -> str:
    ein_digits = re.sub(r"\D", "", ein or "")
    identifier = (identifier or "").strip().lower()
    if not identifier or len(ein_digits) != 9:
        return ""
    return f"{identifier}|{ein_digits}"


def domain_is_limited(domain: str, ein: str) -> bool:
    if not domain or is_exempt_domain(domain):
        return False
    key = usage_limit_key(domain, ein)
    if not key:
        return False
    limits = load_domain_limits()
    prior = int(limits.get(key, 0) or 0)
    if not prior:
        return False
    return int(time.time()) - prior < DOMAIN_LIMIT_DAYS * 24 * 60 * 60


def record_domain_check(domain: str, ein: str) -> None:
    if not domain or is_exempt_domain(domain):
        return
    key = usage_limit_key(domain, ein)
    if not key:
        return
    limits = load_domain_limits()
    limits[key] = int(time.time())
    save_domain_limits(limits)


def normalize_device_id(device_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]", "", (device_id or "").strip())[:120]


def device_is_limited(device_id: str, ein: str) -> bool:
    device_id = normalize_device_id(device_id)
    if not device_id:
        return False
    key = usage_limit_key(device_id, ein)
    if not key:
        return False
    limits = load_device_limits()
    prior = int(limits.get(key, 0) or 0)
    if not prior:
        return False
    return int(time.time()) - prior < DOMAIN_LIMIT_DAYS * 24 * 60 * 60


def record_device_check(device_id: str, ein: str) -> None:
    device_id = normalize_device_id(device_id)
    if not device_id:
        return
    key = usage_limit_key(device_id, ein)
    if not key:
        return
    limits = load_device_limits()
    limits[key] = int(time.time())
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
        if re.search(r"\bexempt\b", no_record_text, re.I):
            return "Exempt"
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
    if re.search(r"\binactive\b", normalized, re.I):
        return "Closed / Withdrawn / Canceled"
    if re.search(r"\bfailed\s+to\s+renew\b", normalized, re.I):
        return "Failed to Renew"
    if re.search(r"not\s+authorized\s+to\s+solicit|may\s+not\s+(?:solicit|raise\s+funds|operate)|cease\s+and\s+desist", normalized, re.I):
        return "Suspended"
    if re.search(r"\bpending\b", normalized, re.I):
        return "Pending"
    if re.search(r"\bin\s+process\b", normalized, re.I):
        return "Pending"
    if re.search(r"\b(withdrawn|retired|terminated|cancelled|canceled|voluntar(?:y|ily)\s+(?:deactivat(?:ed|ion)|surrender(?:ed)?))\b", normalized, re.I):
        return "Closed / Withdrawn / Canceled"
    if re.search(r"\bclosed\b", normalized, re.I):
        return "Closed / Withdrawn / Canceled"
    if re.search(r"\b(delinquent|non\W*compliant|expired|overdue)\b", normalized, re.I):
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


def known_names_for_ein(ein: str) -> list[str]:
    names = []
    for name in [
        organization_name_for_ein(ein),
        public_profile_name_for_ein(ein),
    ]:
        cleaned = re.sub(r"\s+", " ", (name or "").strip())
        if cleaned and cleaned not in names:
            names.append(cleaned)
    return names


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
    if candidates:
        return max(candidates, key=lambda item: item[0])
    raw_tax_period = str((payload.get("organization") or {}).get("tax_period") or "")
    match = re.match(r"(20\d{2})[-/]?(\d{1,2})?", raw_tax_period)
    if match:
        year = int(match.group(1))
        month = int(match.group(2) or "12")
        if 1 <= month <= 12:
            candidates.append((year, (month, calendar.monthrange(year, month)[1])))
    return max(candidates, key=lambda item: item[0]) if candidates else None


def resolved_organization_name(ein: str, supplied_name: str = "") -> str:
    supplied_name = (supplied_name or "").strip()
    reference_name = organization_name_for_ein(ein)
    profile_name = public_profile_name_for_ein(ein)
    known_names = known_names_for_ein(ein)
    return supplied_name or profile_name or reference_name or (known_names[0] if known_names else "")


def format_ein(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 9:
        return f"{digits[:2]}-{digits[2:]}"
    return (value or "").strip()


def fiscal_year_end_for_ein(ein: str) -> tuple[int, int] | None:
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
        return base_due, (
            f"Massachusetts Form PC base due date is {format_date(base_due)}; "
            f"if an extension applies, the extended due date is {format_date(extended_due)}"
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
    elif state == "MA" and extended_due:
        rule_note = "Massachusetts allows a six-month Form PC extension; CE Status is based on the base due date and the extension impact is shown as a scenario"
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
        # Hawaii often exposes the filing years as document tabs/list entries
        # rather than repeating "Annual Filing" beside each year.
        for match in re.finditer(r"\b(20\d{2})\b", annual_section):
            year = int(match.group(1))
            if 2000 <= year <= date.today().year:
                hi_years.append(year)
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
        return {
            "latest_submitted_year": None,
            "latest_not_submitted_year": None,
            "latest_pending_year": None,
        }
    annual_section = annual_match.group(1)
    reporting_incomplete = bool(re.search(r"\b(reporting\s+incomplete|awaiting\s+reporting)\b", readable_body, re.I))
    blocks = re.split(r"(?=Status\s+of\s+Filing\s*:)", annual_section, flags=re.I)
    submitted_years = []
    not_submitted_years = []
    pending_years = []
    not_submitted_status_by_year = {}
    pending_status_by_year = {}
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
        if re.search(r"\b(?:in\s+process|pending)\b", status_text, re.I):
            pending_years.append(year)
            pending_status_by_year[year] = status_text or "In Process"
        elif re.search(r"\bnot\s+submitted\b", status_text, re.I):
            not_submitted_years.append(year)
            not_submitted_status_by_year[year] = status_text or "Not Submitted"
        elif reporting_incomplete and not status_text and not filing_received_match:
            not_submitted_years.append(year)
            not_submitted_status_by_year[year] = "Reporting Incomplete"
        elif (
            (
                re.search(r"\b(?:e-)?accepted\b", status_text, re.I)
                or (not status_text and filing_received_match)
            )
            and not re.search(r"\breject|incomplete|not\s+submitted\b", status_text, re.I)
        ):
            submitted_years.append(year)
    latest_not_submitted_year = max(not_submitted_years) if not_submitted_years else None
    latest_pending_year = max(pending_years) if pending_years else None
    return {
        "latest_submitted_year": max(submitted_years) if submitted_years else None,
        "latest_not_submitted_year": latest_not_submitted_year,
        "latest_not_submitted_status": not_submitted_status_by_year.get(latest_not_submitted_year) if latest_not_submitted_year else None,
        "latest_pending_year": latest_pending_year,
        "latest_pending_status": pending_status_by_year.get(latest_pending_year) if latest_pending_year else None,
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
    result_fiscal_end = fiscal_year_end_from_result(result)
    registry_fiscal_end = fiscal_year_end_from_body(body, state)
    profile_period = public_profile_latest_tax_period_for_ein(result.ein)
    profile_fiscal_end = profile_period[1] if profile_period else None
    fiscal_end = result_fiscal_end or registry_fiscal_end or profile_fiscal_end or fiscal_year_end_for_ein(result.ein)

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
    if due_date is None:
        return {
            "represented_year": latest_year,
            "fiscal_end": fiscal_end,
            "next_report_year": next_report_year,
            "due_date": None,
            "base_due_date": due_options.get("base_due"),
            "extended_due_date": due_options.get("extended_due"),
            "uses_extension_assumption": due_options.get("uses_extension_assumption", False),
            "uses_extension_scenario": due_options.get("uses_extension_scenario", False),
            "comment": "Annual filing due date could not be determined from the available CharityClarity check."
        }
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
    include_and_segments: bool = True,
    include_compact_legal_suffixes: bool = True,
    include_leading_article_variants: bool = True,
    include_broad_query_prefixes: bool = True,
    include_institutional_reductions: bool = True,
) -> list[str]:
    variants = []

    def add(value: str) -> None:
        value = re.sub(r"\s+", " ", (value or "").strip())
        if value and value not in variants:
            variants.append(value)

    def final_substantive_number_variants(value: str) -> list[str]:
        if not re.search(r"\b(?:and|&)\b", value or "", re.I):
            return []
        legal_or_generic = {
            "the", "a", "an", "inc", "inc.", "incorporated", "corp", "corp.",
            "corporation", "llc", "ltd", "ltd.", "limited", "foundation",
            "fund", "charity", "charities", "association", "society",
            "institute", "center", "centre", "organization", "trust",
        }
        matches = list(re.finditer(r"[A-Za-z]{4,}", value or ""))
        for match in reversed(matches):
            word = match.group(0)
            if word.lower() in legal_or_generic:
                continue
            replacements = []
            if word.lower().endswith("ies"):
                replacements.append(f"{word[:-3]}y")
            elif word.lower().endswith("s") and not word.lower().endswith(("ss", "us")):
                replacements.append(word[:-1])
            else:
                replacements.append(f"{word}s")
            return [
                f"{value[:match.start()]}{replacement}{value[match.end():]}"
                for replacement in replacements
                if replacement and replacement.lower() != word.lower()
            ]
        return []

    seed_names = [name]
    if ein and include_ein_aliases:
        for alias in known_names_for_ein(ein):
            if compatible_ein_alias_for_name(name, alias):
                seed_names.append(alias)

    if include_name_segments:
        segmented_seeds = []
        for seed in list(seed_names):
            segment_pattern = (
                r"\s*(?:/|\\|,|&|\band\b|\bd/?b/?a\b|\bdoing\s+business\s+as\b|\baka\b|\bfka\b|\bformerly\b)\s*"
                if include_and_segments
                else r"\s*(?:/|\\|,|\bd/?b/?a\b|\bdoing\s+business\s+as\b|\baka\b|\bfka\b|\bformerly\b)\s*"
            )
            for part in re.split(
                segment_pattern,
                seed or "",
                flags=re.I,
            ):
                part = re.sub(r"\s+", " ", part.strip(" ,;-"))
                if (len(part.split()) >= 2) or len(part) >= 4:
                    segmented_seeds.append(part)
        # Try slash/DBA/AKA sides early. Several name-only registries do not
        # find "A / B" as a combined string, but do find the formal side by
        # itself. Keep the original name first, then the meaningful segments,
        # then any EIN-sourced aliases.
        seed_names = [seed_names[0], *segmented_seeds, *seed_names[1:]]
        if segmented_seeds:
            add(seed_names[0])
            for disease_seed in [seed_names[0]]:
                if re.search(r"\bTuberculosis\b", disease_seed or "", re.I):
                    abbreviated = re.sub(r"\bTuberculosis\b", "TB", disease_seed, flags=re.I).strip()
                    abbreviated = re.sub(r"^(?:the|a|an)\s+", "", abbreviated, flags=re.I).strip()
                    abbreviated_ampersand = re.sub(r"\s+and\s+", " & ", abbreviated, flags=re.I).strip()
                    abbreviated_no_punctuation = re.sub(r"[^\w\s]", " ", abbreviated_ampersand).strip()
                    abbreviated_no_punctuation = re.sub(r"\s+", " ", abbreviated_no_punctuation)
                    add(abbreviated_ampersand)
                    add(abbreviated_no_punctuation)
            for segmented_seed in segmented_seeds:
                add(segmented_seed)

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
        leading_article_from_trailing = ""
        trailing_article_match = re.match(r"^(.*?),\s*the\s*$", base, flags=re.I)
        if trailing_article_match:
            leading_article_from_trailing = f"The {trailing_article_match.group(1).strip()}"
        without_leading_article = re.sub(r"^(?:the|a|an)\s+", "", base, flags=re.I).strip()
        without_comma_suffix = re.sub(r",\s*(inc\.?|incorporated|corp\.?|corporation|llc|ltd\.?)\s*$", "", base, flags=re.I).strip()
        without_suffix = re.sub(r"\b(inc\.?|incorporated|corp\.?|corporation|llc|ltd\.?)\s*$", "", without_comma_suffix, flags=re.I).strip()
        no_comma = re.sub(r",\s*", " ", base).strip()
        no_punctuation = re.sub(r"[^\w\s]", " ", base).strip()
        no_punctuation = re.sub(r"\s+", " ", no_punctuation)
        us_word_variants = []
        for us_source in [base, without_leading_article]:
            if re.search(r"\bu\.?\s*s\.?(?=\W|$)", us_source or "", re.I):
                compact = re.sub(r"\bu\.?\s*s\.?(?=\W|$)", "US", us_source, flags=re.I).strip()
                expanded = re.sub(r"\bu\.?\s*s\.?(?=\W|$)", "United States", us_source, flags=re.I).strip()
                us_word_variants.extend([compact, expanded])
                us_word_variants.extend([
                    re.sub(r"^(?:the|a|an)\s+", "", compact, flags=re.I).strip(),
                    re.sub(r"^(?:the|a|an)\s+", "", expanded, flags=re.I).strip(),
                ])
        slash_as_space = re.sub(r"\s*(?:/|\\)\s*", " ", base).strip()
        slash_as_space = re.sub(r"\s+", " ", slash_as_space)
        broad_query_prefixes = []
        broad_query_suffixes = []
        prefix_source = re.sub(r"^the\s+", "", no_punctuation, flags=re.I).strip()
        prefix_words = prefix_source.split()
        if include_broad_query_prefixes and len(prefix_words) >= 5:
            # Some name-only registries fail on long formal names but return
            # the right row from a shorter prefix. Candidate scoring still has
            # to match the full target name before any result is accepted.
            broad_query_prefixes.extend([
                " ".join(prefix_words[:4]),
                " ".join(prefix_words[:3]),
                " ".join(prefix_words[:2]),
            ])
            broad_query_suffixes.extend([
                " ".join(prefix_words[-3:]),
                " ".join(prefix_words[-2:]),
            ])
        institute_plural = re.sub(r"\bInstitute\s+of\b", "Institutes of", base, flags=re.I).strip()
        institute_singular = re.sub(r"\bInstitutes\s+of\b", "Institute of", base, flags=re.I).strip()
        hyphen_as_space = re.sub(r"[-\u2010-\u2015]+", " ", base).strip()
        hyphen_removed = re.sub(r"[-\u2010-\u2015]+", "", base).strip()
        title_hyphen_base = ""
        if re.match(r"^[A-Z]{2,8}[-\u2010-\u2015][A-Za-z]", base):
            # A few name-search registries are picky about casing for acronym-hyphen names.
            title_hyphen_base = re.sub(
                r"^[A-Z]{2,8}",
                lambda match: match.group(0).title(),
                base,
                count=1,
            )
        final_number_variants = []
        for number_source in [base, without_suffix, no_punctuation]:
            for number_variant in final_substantive_number_variants(number_source):
                final_number_variants.append(number_variant)
        ampersand_as_and = re.sub(r"\s*&\s*", " and ", base).strip()
        ampersand_removed = re.sub(r"\s*&\s*", " ", base).strip()
        apostrophe_removed = re.sub(r"[']", "", base).strip()
        possessive_removed = re.sub(r"\b([A-Za-z]+)'s\b", r"\1s", base).strip()
        compact_alnum_token = re.sub(r"\b([A-Za-z]\d)\s+([A-Za-z])\b", r"\1\2", base).strip()
        compact_alnum_token = re.sub(r"\b([A-Za-z]+)\s+(\d+)\s+([A-Za-z]+)\b", r"\1\2\3", compact_alnum_token).strip()
        spaced_alnum_token = re.sub(r"\b([A-Za-z]+)(\d+)([A-Za-z]+)\b", r"\1 \2 \3", base).strip()
        saint_expanded = re.sub(r"\bSt\.?\s+", "Saint ", base, flags=re.I).strip()
        saint_abbreviated = re.sub(r"\bSaint\s+", "St. ", base, flags=re.I).strip()
        childrens_hospital = re.sub(
            r"\b(Children'?s?)\s+Foundation\b",
            r"\1 Hospital Foundation",
            base,
            flags=re.I,
        ).strip()
        childrens_hospital_no_punctuation = re.sub(
            r"\b(Children'?s?)\s+Foundation\b",
            r"\1 Hospital Foundation",
            no_punctuation,
            flags=re.I,
        ).strip()
        cancer_research_center = re.sub(
            r"\bCancer\s+Center\b",
            "Cancer Research Center",
            base,
            flags=re.I,
        ).strip()
        cancer_center = re.sub(
            r"\bCancer\s+Research\s+Center\b",
            "Cancer Center",
            base,
            flags=re.I,
        ).strip()
        of_america_removed = re.sub(r"\bof\s+(?:america|the\s+united\s+states|united\s+states)\b\.?\s*$", "", base, flags=re.I).strip(" ,;-")
        of_connector_removed = re.sub(r"\bof\s+(America|United\s+States)\b", r"\1", base, flags=re.I).strip()
        ms_expanded = re.sub(r"\bMS\s+Society\b", "Multiple Sclerosis Society", base, flags=re.I).strip()
        disease_abbreviated = re.sub(r"\bTuberculosis\b", "TB", base, flags=re.I).strip()
        disease_abbreviated_ampersand = re.sub(r"\s+and\s+", " & ", disease_abbreviated, flags=re.I).strip()
        disease_abbreviated_no_punctuation = re.sub(r"[^\w\s]", " ", disease_abbreviated_ampersand).strip()
        disease_abbreviated_no_punctuation = re.sub(r"\s+", " ", disease_abbreviated_no_punctuation)
        institution_descriptor_removed = institutional_tail_reduction(base) if include_institutional_reductions else ""
        and_no_punctuation = re.sub(r"[^\w\s]", " ", ampersand_as_and).strip()
        and_no_punctuation = re.sub(r"\s+", " ", and_no_punctuation)
        and_without_suffix = re.sub(
            r"\b(inc\.?|incorporated|corp\.?|corporation|llc|ltd\.?)\b",
            " ",
            and_no_punctuation,
            flags=re.I,
        ).strip()
        and_without_suffix = re.sub(r"\s+", " ", and_without_suffix)
        compact_legal_suffixes = re.sub(
            r"\b(the|inc\.?|incorporated|corp\.?|corporation|llc|ltd\.?)\b",
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
        legal_suffix_additions = []
        if not re.search(r"\b(inc\.?|incorporated|corp\.?|corporation|llc|ltd\.?|limited)\s*$", base, re.I):
            # Some public profiles omit the legal suffix even when name-search
            # registries require it to find the organization.
            legal_suffix_additions.extend([
                f"{base} Inc",
                f"{base} Inc.",
                f"{base}, Inc",
                f"{base}, Inc.",
                f"{hyphen_as_space} Inc" if hyphen_as_space and hyphen_as_space.lower() != base.lower() else "",
                f"{hyphen_as_space} Inc." if hyphen_as_space and hyphen_as_space.lower() != base.lower() else "",
                f"{hyphen_as_space}, Inc" if hyphen_as_space and hyphen_as_space.lower() != base.lower() else "",
                f"{hyphen_as_space}, Inc." if hyphen_as_space and hyphen_as_space.lower() != base.lower() else "",
                f"{title_hyphen_base} Inc" if title_hyphen_base else "",
                f"{title_hyphen_base} Inc." if title_hyphen_base else "",
                f"{title_hyphen_base}, Inc" if title_hyphen_base else "",
                f"{title_hyphen_base}, Inc." if title_hyphen_base else "",
            ])
        broad_variants = [and_without_suffix, compact_legal_suffixes] if include_compact_legal_suffixes else []
        with_leading_the = "" if re.match(r"^the\s+", base, re.I) else f"The {base}"
        article_variants = [with_leading_the, without_leading_article] if include_leading_article_variants else []
        for variant in [
            institution_descriptor_removed,
            without_leading_article,
            without_comma_suffix,
            without_suffix,
            no_comma,
            disease_abbreviated,
            disease_abbreviated_ampersand,
            disease_abbreviated_no_punctuation,
            *broad_query_prefixes,
            *broad_query_suffixes,
            *final_number_variants,
            childrens_hospital,
            childrens_hospital_no_punctuation,
            *hyphenated_word_pairs,
            *us_word_variants,
            no_punctuation,
            slash_as_space,
            institute_plural,
            institute_singular,
            hyphen_as_space,
            hyphen_removed,
            compact_alnum_token,
            spaced_alnum_token,
            ampersand_as_and,
            ampersand_removed,
            apostrophe_removed,
            possessive_removed,
            saint_expanded,
            saint_abbreviated,
            cancer_research_center,
            cancer_center,
            of_america_removed,
            of_connector_removed,
            title_hyphen_base,
            ms_expanded,
            and_no_punctuation,
            *broad_variants,
            *us_prefixed_variants,
            leading_article_from_trailing,
            without_trailing_the,
            *article_variants,
            *legal_suffix_additions,
        ]:
            add(variant)
    return variants or [""]


def institutional_tail_reduction(value: str) -> str:
    """Trim narrow institutional suffixes used inconsistently by registries."""
    reduced = re.sub(
        r"\b(?:national\s+)?(?:medical\s+center|hospital\s+center|hospital)\b\.?\s*$",
        "",
        value or "",
        flags=re.I,
    ).strip(" ,;-")
    return re.sub(r"\s+", " ", reduced)


def prioritized_institutional_variants(variants: list[str]) -> list[str]:
    prioritized = []

    def add(value: str) -> None:
        cleaned = re.sub(r"\s+", " ", (value or "").strip())
        if cleaned and cleaned.lower() not in {existing.lower() for existing in prioritized}:
            prioritized.append(cleaned)

    for variant in variants:
        reduced = institutional_tail_reduction(variant)
        if reduced and reduced.lower() != (variant or "").strip().lower():
            add(reduced)
    for variant in variants:
        add(variant)
    return prioritized or variants


def compatible_ein_alias_for_name(original_name: str, alias_name: str) -> bool:
    """Only let EIN-resolved aliases accept rows when they remain specific.

    The query layer can stay flexible, but the acceptance layer should not let a
    broad alias such as "University of Missouri" certify a row for "The Curators
    of University of Missouri". That was the source of the recent name-only
    false positives.
    """
    normalize = getattr(checker, "normalize_name", lambda value: re.sub(r"\W+", " ", (value or "").lower()).strip())
    original = normalize(original_name)
    alias = normalize(alias_name)
    if not original or not alias:
        return False
    if original == alias:
        return True

    original_words = original.split()
    alias_words = alias.split()
    if not original_words or not alias_words:
        return False

    def acronym_from_words(words: list[str]) -> str:
        ignored = {"the", "a", "an", "of", "for", "and", "to", "in", "on", "at", "by", "inc", "incorporated", "corp", "corporation", "llc", "ltd", "limited"}
        return "".join(word[0] for word in words if word and word not in ignored)

    original_compact = re.sub(r"[^a-z0-9]+", "", original)
    alias_compact = re.sub(r"[^a-z0-9]+", "", alias)
    alias_acronym = acronym_from_words(alias_words)
    original_acronym = acronym_from_words(original_words)
    if 2 <= len(original_compact) <= 8 and original_compact == alias_acronym:
        return True
    if 2 <= len(alias_compact) <= 8 and alias_compact == original_acronym:
        return True
    for index, word in enumerate(original_words):
        if not (2 <= len(word) <= 6 and word.isalpha()):
            continue
        for start in range(len(alias_words)):
            for end in range(start + 2, min(len(alias_words), start + 5) + 1):
                if acronym_from_words(alias_words[start:end]) != word:
                    continue
                expanded = original_words[:index] + alias_words[start:end] + original_words[index + 1:]
                if expanded == alias_words:
                    return True
                if (
                    len(expanded) == len(alias_words)
                    and expanded[:index] == alias_words[:index]
                    and expanded[index + (end - start):] == alias_words[end:]
                ):
                    return True

    governance_words = {"trustees", "curators", "regents", "board"}
    if original_words[0] in governance_words and alias_words[0] != original_words[0]:
        return False

    if alias in original or original in alias:
        shorter_words = alias_words if len(alias_words) <= len(original_words) else original_words
        if len(shorter_words) >= 3:
            return True
        # Allow established two-word fund aliases while
        # avoid broad two-word institution aliases such as "Allen Institute".
        if len(alias_words) == 2 and alias_words == original_words[:2] and alias_words[-1] == "fund":
            return True
        return False

    entity_words = {"foundation", "fund", "association", "society", "institute", "center", "centre", "network", "mission", "trust"}
    if (
        len(original_words) >= 3
        and len(alias_words) >= 3
        and original_words[:2] == alias_words[:2]
        and original_words[-1] == alias_words[-1]
        and original_words[-1] in entity_words
    ):
        return True

    generic_words = {
        "the", "and", "of", "for", "to", "in", "on", "at", "by", "inc", "incorporated",
        "corp", "corporation", "llc", "ltd", "foundation", "fund", "charity", "charities",
        "association", "society", "center", "centre", "institute", "organization",
    }
    shared_distinctive = (set(original_words) & set(alias_words)) - generic_words
    if len(shared_distinctive) >= 2:
        return True

    return False


def organization_match_target_variants(name: str, ein: str = "") -> list[str]:
    """Safe names used to accept a registry row after a broad search query.

    Name-only registries often need loose queries to find a row, but the row
    itself must still match the requested organization. These variants preserve
    safe aliases such as punctuation, leading/trailing "The", slash segments,
    hyphen variants, acronym expansion, and legal suffix differences while
    excluding broad two/three/four-word prefixes such as "Trustees Of".
    """
    variants = organization_name_variants(
        name,
        ein,
        include_ein_aliases=False,
        include_name_segments=True,
        include_and_segments=False,
        include_compact_legal_suffixes=True,
        include_leading_article_variants=True,
        include_broad_query_prefixes=False,
        include_institutional_reductions=False,
    )
    for alias in known_names_for_ein(ein):
        if compatible_ein_alias_for_name(name, alias):
            variants.extend(organization_name_variants(
                alias,
                "",
                include_ein_aliases=False,
                include_name_segments=True,
                include_and_segments=False,
                include_compact_legal_suffixes=True,
                include_leading_article_variants=True,
                include_broad_query_prefixes=False,
                include_institutional_reductions=False,
            ))
    return variants or [name]


def org_with_name(org, name: str):
    clone = SimpleNamespace(organization_name=name, ein=org.ein)
    if hasattr(org, "match_target_names"):
        clone.match_target_names = getattr(org, "match_target_names")
    else:
        clone.match_target_names = organization_match_target_variants(getattr(org, "organization_name", ""), getattr(org, "ein", ""))
    if hasattr(org, "evidence_mode"):
        clone.evidence_mode = getattr(org, "evidence_mode")
    return clone


def result_registry_name_is_safe(result, original_name: str, ein: str = "") -> bool:
    registry_name = clean_registry_name(getattr(result, "matched_registry_name", "") or "")
    if not registry_name:
        return False
    return registry_name_is_safe_for_org(registry_name, original_name, ein)


def registry_name_is_safe_for_org(registry_name: str, original_name: str, ein: str = "") -> bool:
    registry_name = clean_registry_name(registry_name or "")
    if not registry_name:
        return False
    safe_targets = organization_match_target_variants(original_name, ein)
    if target_name_score(registry_name, safe_targets) >= 450:
        return True
    if incompatible_institutional_prefix_expansion(original_name, registry_name):
        return False
    return compatible_ein_alias_for_name(original_name, registry_name)


def incompatible_institutional_prefix_expansion(original_name: str, registry_name: str) -> bool:
    reduced = institutional_tail_reduction(original_name)
    if not reduced or reduced.lower() == (original_name or "").strip().lower():
        return False
    reduced_norm = normalized_match_name(reduced)
    original_norm = normalized_match_name(original_name)
    registry_norm = normalized_match_name(registry_name)
    if not reduced_norm or not original_norm or not registry_norm:
        return False
    if registry_norm == reduced_norm:
        return False
    return registry_norm.startswith(f"{reduced_norm} ") and not original_norm.startswith(registry_norm)


def copy_name_fallback_result(original_org, result):
    result.organization_name = original_org.organization_name
    result.ein = original_org.ein
    return result


def quick_registry_preflight(url: str, timeout_seconds: float) -> tuple[bool, str]:
    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 CharityClarity preflight"},
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return response.status < 500, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        # Some older state sites prove reachability with redirects that urllib
        # treats as errors. A non-5xx HTTP response is still enough to continue.
        return exc.code < 500, f"HTTP {exc.code}"
    except Exception as exc:
        return False, str(exc)


def preflight_name_search_registry(org, state: str) -> tuple[bool, str, object | None]:
    state = state.upper()
    url = NAME_SEARCH_PREFLIGHT_URLS.get(state)
    if not url:
        return True, "", None
    timeout = SC_PREFLIGHT_TIMEOUT_SECONDS if state == "SC" else NAME_SEARCH_PREFLIGHT_TIMEOUT_SECONDS
    reachable, note = quick_registry_preflight(url, timeout)
    if reachable:
        return True, note, None
    result = checker.StateResult(org.organization_name, org.ein, state, "Site Not Reachable", url)
    result.raw_status_text = f"{state} registry preflight failed"
    result.source_note = f"{state} public registry did not respond to a quick preflight check: {note}"
    result.error = f"{state} preflight failed: {note}"
    result.success = False
    return False, note, result


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
    max_elapsed_seconds: float | None = None,
    reject_va_suspended_from_leading_the_drop: bool = False,
    include_ein_aliases: bool = True,
    include_name_segments: bool = False,
    include_and_segments: bool = True,
    include_compact_legal_suffixes: bool = True,
    include_leading_article_variants: bool = True,
    prioritize_institution_reductions: bool = False,
    require_safe_registry_name: bool = False,
    preferred_variants: list[str] | None = None,
):
    best_result = None
    original_name = org.organization_name
    variants = organization_name_variants(
        original_name,
        org.ein,
        include_ein_aliases=include_ein_aliases,
        include_name_segments=include_name_segments,
        include_and_segments=include_and_segments,
        include_compact_legal_suffixes=include_compact_legal_suffixes,
        include_leading_article_variants=include_leading_article_variants,
    )
    if include_ein_aliases:
        alias_priority = [
            alias for alias in known_names_for_ein(org.ein)
            if compatible_ein_alias_for_name(original_name, alias)
        ]
        prioritized = []
        for variant in [variants[0] if variants else original_name, *alias_priority, *variants[1:]]:
            cleaned = re.sub(r"\s+", " ", (variant or "").strip())
            if cleaned and cleaned.lower() not in {existing.lower() for existing in prioritized}:
                prioritized.append(cleaned)
        variants = prioritized or variants
    if include_leading_article_variants and re.match(r"^(?:the|a|an)\s+", original_name or "", re.I):
        article_drop = re.sub(r"^(?:the|a|an)\s+", "", original_name or "", flags=re.I).strip()
        article_drop_no_suffix = re.sub(
            r"\b(inc\.?|incorporated|corp\.?|corporation|llc|ltd\.?)\s*$",
            "",
            re.sub(r",\s*(inc\.?|incorporated|corp\.?|corporation|llc|ltd\.?)\s*$", "", article_drop, flags=re.I).strip(),
            flags=re.I,
        ).strip()
        prioritized = []
        for variant in [article_drop, article_drop_no_suffix, variants[0] if variants else "", *variants[1:]]:
            cleaned = re.sub(r"\s+", " ", (variant or "").strip())
            if cleaned and cleaned.lower() not in {existing.lower() for existing in prioritized}:
                prioritized.append(cleaned)
        variants = prioritized or variants
    if prioritize_institution_reductions:
        variants = prioritized_institutional_variants(variants)
    if preferred_variants:
        prioritized = []
        for variant in [*preferred_variants, *variants]:
            cleaned = re.sub(r"\s+", " ", (variant or "").strip())
            if cleaned and cleaned.lower() not in {existing.lower() for existing in prioritized}:
                prioritized.append(cleaned)
        variants = prioritized or variants
    safe_match_targets = organization_match_target_variants(original_name, org.ein)
    if max_variants:
        variants = variants[:max_variants]
    started = time.perf_counter()
    for variant in variants:
        if max_elapsed_seconds and best_result is not None and (time.perf_counter() - started) >= max_elapsed_seconds:
            if getattr(best_result, "organization_name", "") != original_name:
                best_result.organization_name = original_name
            return best_result
        variant_org = org_with_name(org, variant)
        variant_org.match_target_names = safe_match_targets
        result = search_func(page, variant_org)
        if getattr(result, "organization_name", "") != original_name:
            result.organization_name = original_name
        if public_status(result) == "Site Not Reachable":
            return result
        if (
            reject_va_suspended_from_leading_the_drop
            and public_status(result) == "Suspended"
            and is_leading_the_drop(original_name, variant)
        ):
            continue
        if (
            require_safe_registry_name
            and public_status(result) not in {"Not Registered", "Site Not Reachable"}
            and (getattr(result, "matched_registry_name", "") or "").strip()
            and not result_registry_name_is_safe(result, original_name, org.ein)
        ):
            replacement = checker.StateResult(
                original_name,
                org.ein,
                getattr(result, "state", "") or "",
                checker.STATUS_NOT_REGISTERED,
                getattr(result, "source_url", "") or "",
                raw_status_text="Registry name did not safely match the requested organization",
                source_note="The public registry returned a row, but CharityClarity rejected it because the registry name did not safely match the requested organization.",
                success=True,
            )
            best_result = replacement
            continue
        if not result_is_retryable_name_miss(result):
            return result
        best_result = result
    if best_result and getattr(best_result, "organization_name", "") != original_name:
        best_result.organization_name = original_name
    return best_result


def search_va_bounded(page, org):
    # Virginia's search helper already generates punctuation/article/name
    # variants internally. During no-match cases, trying the full internal list
    # for every outer variant can make a clean Not Registered result take more
    # than a minute. Limit the internal query list to the strongest few forms
    # while keeping the normal candidate matching and detail parsing.
    with VA_SEARCH_VARIANT_LOCK:
        original_variant_builder = checker.search_name_query_variants

        def bounded_variants(name: str, max_words: int = 5):
            generated = original_variant_builder(name, max_words=max_words)
            bounded = []

            def add(value: str) -> None:
                value = re.sub(r"\s+", " ", (value or "").strip())
                if value and value not in bounded:
                    bounded.append(value)

            for variant in generated[:3]:
                add(variant)
            for variant in generated:
                if "-" in variant or re.match(r"^(?:the|a|an)\s+", variant, re.I):
                    add(variant)
                if len(bounded) >= 6:
                    break
            return bounded or generated[:2]

        checker.search_name_query_variants = bounded_variants
        try:
            return checker.search_va(page, org)
        finally:
            checker.search_name_query_variants = original_variant_builder


def search_me_serialized(page, org):
    global ME_LAST_LOOKUP_FINISHED
    with ME_LOOKUP_LOCK:
        elapsed = time.perf_counter() - ME_LAST_LOOKUP_FINISHED
        if elapsed < ME_LOOKUP_MIN_INTERVAL_SECONDS:
            time.sleep(ME_LOOKUP_MIN_INTERVAL_SECONDS - elapsed)

        def run_lookup():
            preferred_variants = []
            if re.search(r"\bTuberculosis\b", org.organization_name or "", re.I):
                preferred_variants = [
                    variant for variant in organization_name_variants(
                        org.organization_name,
                        org.ein,
                        include_ein_aliases=True,
                        include_name_segments=True,
                        include_compact_legal_suffixes=False,
                        include_leading_article_variants=True,
                    )
                    if re.search(r"\bTB\b", variant or "", re.I)
                ][:3]
            return search_with_name_variants(
                page,
                org,
                checker.search_me,
                max_variants=6,
                max_elapsed_seconds=min(max(NAME_SEARCH_VARIANT_MAX_SECONDS, 25.0), 35.0),
                include_ein_aliases=True,
                include_name_segments=True,
                include_compact_legal_suffixes=False,
                include_leading_article_variants=True,
                require_safe_registry_name=True,
                preferred_variants=preferred_variants,
            )

        result = run_lookup()
        if ME_CONFIRM_NOT_REGISTERED and public_status(result) == "Not Registered":
            confirmations = 1
            for _ in range(max(0, ME_NOT_REGISTERED_CONFIRMATION_ATTEMPTS - 1)):
                time.sleep(ME_NOT_REGISTERED_CONFIRMATION_DELAY_SECONDS)
                confirmation = run_lookup()
                confirmations += 1
                if public_status(confirmation) != "Not Registered":
                    result = confirmation
                    result.source_note = (
                        (result.source_note or "Maine public registry record found.")
                        + f" Maine no-match was rechecked {confirmations} times before returning this result."
                    )
                    break
            else:
                result.source_note = (
                    (result.source_note or "Maine search returned no matching organization result.")
                    + f" {confirmations} Maine searches returned no matching organization result."
                )
        ME_LAST_LOOKUP_FINISHED = time.perf_counter()
        return result


def external_status_to_checker_status(status: str) -> str:
    raw = (status or "").strip()
    normalized = raw.lower()
    if normalized in {"not registered", "not registered.", "not found", "no record", "no record found"}:
        return checker.STATUS_NOT_REGISTERED
    if normalized in {"delinquent/non-compliant", "delinquent", "non-compliant", "noncompliant", "expired"}:
        return checker.STATUS_DELINQUENT
    if normalized == "upcoming filing":
        return checker.STATUS_UPCOMING
    if normalized == "current":
        return checker.STATUS_CURRENT
    if normalized == "pending":
        return "Pending"
    if normalized in {"revoked", "suspended", "exempt", "closed / withdrawn / canceled", "failed to renew"}:
        return raw
    return raw or checker.STATUS_UNKNOWN


def classify_mi_solicitation_status(raw_status: str) -> str:
    raw = re.sub(r"\s+", " ", raw_status or "").strip()
    if not raw or raw.upper() == "N/A":
        return ""
    if re.search(r"\bpending\b", raw, re.I):
        return "Pending"
    registered_expiration = re.search(
        r"\b(?:registered|active)\b[\s\S]{0,220}?\bExpiration\s+Date\s*:?\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})",
        raw,
        re.I,
    )
    if registered_expiration:
        return classify_expiration_date(parse_due_date(registered_expiration.group(1)))
    if re.search(r"\b(exempt)\b", raw, re.I):
        return "Exempt"
    if re.search(r"\b(revoked|suspended)\b", raw, re.I):
        return "Suspended"
    if re.search(r"\b(withdrawn|terminated|closed|cancel(?:ed|led)|inactive)\b", raw, re.I):
        return "Closed / Withdrawn / Canceled"
    if re.search(r"\b(delinquent|non\W*compliant|expired)\b", raw, re.I):
        return checker.STATUS_DELINQUENT
    if re.search(r"\b(registered|active|current|compliant)\b", raw, re.I):
        return checker.STATUS_CURRENT
    return checker.STATUS_UNKNOWN


def mi_solicitation_raw_from_combined(raw_status: str) -> str:
    match = re.search(
        r"Solicitation\s+Registration\s+Status\s*:\s*(.*?)(?:\s*\|\s*Charitable\s+Trust\s+Registration\s+Status\s*:|$)",
        raw_status or "",
        re.I | re.S,
    )
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def copy_external_result(org, state: str, external_result):
    status = external_status_to_checker_status(getattr(external_result, "status", ""))
    raw_status = getattr(external_result, "raw_status_text", "") or status
    normalized_error = getattr(external_result, "error", "") or ""
    if state.upper() == "MI":
        if re.search(r"Could not find the Michigan results frame", normalized_error, re.I):
            status = checker.STATUS_NOT_REGISTERED
            raw_status = "No results frame after Michigan EIN search"
            normalized_error = ""
        solicitation_raw = mi_solicitation_raw_from_combined(raw_status)
        solicitation_status = classify_mi_solicitation_status(solicitation_raw)
        if solicitation_status:
            status = solicitation_status
        solicitation_match = re.search(
            r"Solicitation\s+Registration\s+Status\s*:\s*Registered[\s\S]{0,160}?Expiration\s+Date\s*:\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})",
            raw_status,
            re.I,
        )
        if solicitation_match and status != "Pending":
            status = classify_expiration_date(parse_due_date(solicitation_match.group(1)))
            raw_status = f"Solicitation Registration Status: Registered - Expiration Date: {solicitation_match.group(1)}"
    result = checker.StateResult(
        org.organization_name,
        org.ein,
        state,
        status,
        getattr(external_result, "source_url", "") or "",
    )
    result.raw_status_text = raw_status
    result.source_note = getattr(external_result, "source_note", "") or ""
    result.matched_registry_name = getattr(external_result, "matched_registry_name", "") or ""
    result.matched_registry_identifier = getattr(external_result, "matched_registry_identifier", "") or ""
    result.success = bool(getattr(external_result, "success", False) or public_status(result) != "Site Not Reachable")
    result.error = normalized_error
    return result


def patch_mi_module_for_fast_lookups(module) -> None:
    """Keep MI on the same registry path, but avoid 30-60s waits per phase."""
    if getattr(module, "_cc_fast_lookup_patch", False):
        return

    def wait_for_search_form_fast(page) -> bool:
        deadline = time.time() + 6
        while time.time() < deadline:
            try:
                locator = page.locator("#ctl00_MainContent_txtEIN")
                if locator.count() > 0 and locator.first.is_visible(timeout=500):
                    return True
            except Exception:
                pass
            time.sleep(0.25)
        return False

    def open_search_form_fast(page) -> bool:
        for _ in range(1):
            page.goto(module.MI_DISCLAIMER_URL, wait_until="domcontentloaded", timeout=18000)
            if wait_for_search_form_fast(page):
                return True

            actions = [
                lambda: page.evaluate("__doPostBack('ctl00$MainContent$lblYes','')"),
                lambda: page.locator("#ctl00_MainContent_lblYes").click(timeout=5000, no_wait_after=True),
                lambda: page.locator("#ctl00_MainContent_lblYes").evaluate("el => el.click()"),
            ]
            for action in actions:
                try:
                    action()
                except Exception:
                    continue
                if wait_for_search_form_fast(page):
                    return True

            try:
                page.goto(module.MI_SEARCH_URL, wait_until="domcontentloaded", timeout=12000)
                if wait_for_search_form_fast(page):
                    return True
            except Exception:
                pass
        return False

    def find_results_frame_fast(page):
        deadline = time.time() + 10
        while time.time() < deadline:
            for frame in reversed(page.frames):
                text = re.sub(r"\s+", " ", module.body_text(frame, timeout=2500)).strip()
                if not text:
                    continue
                if "Results for the following input" in text or "record(s) found" in text or "No records found" in text:
                    return frame
            time.sleep(0.25)
        return None

    def find_detail_frame_fast(page):
        deadline = time.time() + 10
        while time.time() < deadline:
            for frame in reversed(page.frames):
                try:
                    if frame.locator("#ctl00_MainContent_fvCSForm_lblSolicitationRegistrationStatus").count() > 0:
                        return frame
                except Exception:
                    pass
                text = re.sub(r"\s+", " ", module.body_text(frame, timeout=2500)).strip()
                if "Solicitation Registration Status" in text and "Charitable Trust Registration Status" in text:
                    return frame
            time.sleep(0.25)
        return None

    def search_mi_fast(page, org, artifacts_dir, no_screenshot):
        formatted_ein = module.format_ein(org.ein)
        result = module.SearchResult(
            organization_name=org.organization_name or formatted_ein,
            ein=formatted_ein,
            status=module.STATUS_UNKNOWN,
            raw_status_text="",
        )

        if len(module.digits_only(org.ein)) != 9:
            result.error = "Michigan search requires a 9-digit EIN."
            return result

        try:
            if not open_search_form_fast(page):
                result.error = "Could not open the Michigan search form after the disclaimer."
                return result

            page.locator("#ctl00_MainContent_txtEIN").fill("")
            page.locator("#ctl00_MainContent_txtEIN").fill(formatted_ein)
            page.locator("#ctl00_MainContent_btnTextSearch").click(timeout=8000, no_wait_after=True)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            time.sleep(4)

            results_frame = find_results_frame_fast(page)
            if not results_frame:
                result.error = "Could not find the Michigan results frame."
                return result

            results_text = re.sub(r"\s+", " ", module.body_text(results_frame, timeout=5000)).strip()
            if re.search(r"\b0 record\(s\) found\b|no records found|no results found|not found", results_text, re.I):
                result.status = module.STATUS_NOT_REGISTERED
                result.raw_status_text = "No results found"
                result.success = True
                result.source_note = "Michigan EIN search returned no matching result."
                return result

            chosen = module.choose_result_link(results_frame, org.organization_name)
            if not chosen:
                result.status = module.STATUS_NOT_REGISTERED
                result.raw_status_text = "No matching organization link"
                result.success = True
                result.source_note = "Michigan results did not contain a clickable organization summary link."
                return result

            _, clicked_name, link, href = chosen
            module.click_result_link(results_frame, link, href)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            time.sleep(2)

            detail_frame = find_detail_frame_fast(page)
            if not detail_frame:
                result.error = "Could not load the Michigan detail page."
                return result

            site_name = module.extract_legal_name(detail_frame) or clicked_name or formatted_ein
            raw_status = module.extract_solicitation_status(detail_frame)
            charitable_trust_status = module.extract_charitable_trust_status(detail_frame)
            if not raw_status and not charitable_trust_status:
                result.organization_name = site_name
                result.status = module.STATUS_UNKNOWN
                result.raw_status_text = "Registration statuses not found"
                result.success = True
                result.source_note = (
                    "Michigan detail page loaded, but neither Solicitation Registration Status "
                    "nor Charitable Trust Registration Status could be extracted."
                )
                return result

            result.organization_name = site_name
            result.raw_status_text = (
                f"Solicitation Registration Status: {raw_status or 'N/A'} | "
                f"Charitable Trust Registration Status: {charitable_trust_status or 'N/A'}"
            )
            result.status = module.classify_mi_status(raw_status, charitable_trust_status)
            result.success = True
            return result
        except Exception as exc:
            result.error = f"MI error: {exc}"
            return result

    module.wait_for_search_form = wait_for_search_form_fast
    module.open_search_form = open_search_form_fast
    module.find_results_frame = find_results_frame_fast
    module.find_detail_frame = find_detail_frame_fast
    module.search_mi = search_mi_fast
    module._cc_fast_lookup_patch = True


def search_bundled_extension_state(page, org, state: str):
    state = state.upper()
    module = state_extension_module(state)
    if state == "MI":
        patch_mi_module_for_fast_lookups(module)
    bundle_org = module.Organization(organization_name=org.organization_name, ein=org.ein)
    if state == "MI":
        external_result = module.search_mi(page, bundle_org, ARTIFACTS_DIR / "MI", True)
        copied = copy_external_result(org, state, external_result)
        if public_status(copied) == "Not Registered" and re.search(
            r"clickable organization summary link|No matching organization link",
            " ".join([getattr(external_result, "raw_status_text", "") or "", getattr(external_result, "source_note", "") or ""]),
            re.I,
        ):
            # Michigan's EIN search is authoritative. If the exact EIN returns a
            # row under a registry/legal name that differs from the supplied
            # public-profile name, use the first EIN-confirmed row instead of
            # rejecting it on name alone.
            external_result = module.search_mi(page, module.Organization(organization_name="", ein=org.ein), ARTIFACTS_DIR / "MI", True)
        return copy_external_result(org, state, external_result)
    elif state == "OH":
        external_result = module.search_oh(page, bundle_org, ARTIFACTS_DIR / "OH", True)
    elif state == "OR":
        def or_detail_ein_mismatches(registry_name: str = "") -> bool:
            if registry_name:
                safe_targets = organization_match_target_variants(org.organization_name, org.ein)
                if target_name_score(registry_name, safe_targets) >= 450:
                    return False
            body_text = registry_page_body(page)
            registry_ein = checker.extract_labeled_value_from_text(body_text, ["Federal EIN", "EIN"])
            registry_digits = re.sub(r"\D", "", registry_ein or "")
            requested_digits = re.sub(r"\D", "", org.ein or "")
            return bool(registry_digits and requested_digits and registry_digits != requested_digits)

        def or_registry_name_from_detail() -> str:
            body_text = registry_page_body(page)
            before_address = re.split(r"\bMailing\s+Address\s*:", body_text, maxsplit=1, flags=re.I)[0]
            lines = [re.sub(r"\s+", " ", line).strip() for line in before_address.splitlines()]
            for line in reversed(lines):
                cleaned = useful_registry_name(line)
                if cleaned and not re.search(r"Search Oregon Charities|Charitable Organizations Registered|Download Charity database", cleaned, re.I):
                    return cleaned
            return ""

        def or_detail_name_mismatches(registry_name: str = "") -> bool:
            candidate_name = clean_registry_name(registry_name or or_registry_name_from_detail())
            if not candidate_name:
                return False
            return not registry_name_is_safe_for_org(candidate_name, org.organization_name, org.ein)

        def best_or_registry_name_from_page() -> str:
            try:
                row_candidates = page.evaluate(
                    """
                    () => Array.from(document.querySelectorAll('table tbody tr, table tr')).map((row) => {
                        const cells = Array.from(row.querySelectorAll('td')).map((cell) => (cell.innerText || cell.textContent || '').replace(/\\s+/g, ' ').trim());
                        const link = row.querySelector('a');
                        return { cells, text: (row.innerText || row.textContent || '').replace(/\\s+/g, ' ').trim(), linkText: link ? (link.innerText || link.textContent || '').replace(/\\s+/g, ' ').trim() : '' };
                    }).filter((row) => row.linkText && row.cells.length >= 1);
                    """
                )
            except Exception:
                row_candidates = []
            safe_targets = organization_match_target_variants(org.organization_name, org.ein)
            best_candidate_name = ""
            best_candidate_score = -10000
            for candidate in row_candidates:
                candidate_name = clean_registry_name(candidate.get("linkText") or (candidate.get("cells") or [""])[0])
                score = target_name_score(candidate_name, safe_targets)
                if score > best_candidate_score:
                    best_candidate_score = score
                    best_candidate_name = candidate_name
            return best_candidate_name if best_candidate_score >= 450 else ""

        variants = organization_name_variants(
            org.organization_name,
            org.ein,
            include_ein_aliases=True,
            include_name_segments=True,
            include_compact_legal_suffixes=True,
            include_leading_article_variants=True,
        )
        variants = prioritized_institutional_variants(variants)

        def or_variant_priority(value: str) -> tuple[int, int, str]:
            cleaned = re.sub(r"\s+", " ", value or "").strip()
            if cleaned == (org.organization_name or "").strip():
                return (0, 0, cleaned.lower())
            words = re.findall(r"[A-Za-z0-9]+", cleaned)
            has_separator_source = bool(re.search(r"[/\\]", org.organization_name or ""))
            has_legal_suffix = bool(re.search(r"\b(inc\.?|incorporated|corp\.?|corporation|llc|ltd\.?|limited)\b", cleaned, re.I))
            has_article = bool(re.search(r"^(?:the|a|an)\s+", cleaned, re.I) or re.search(r",\s*(?:the|a|an)$", cleaned, re.I))
            if has_separator_source and len(words) >= 3 and not re.search(r"[/\\]", cleaned):
                return (1 + (1 if has_legal_suffix else 0) + (1 if has_article else 0), -len(words), cleaned.lower())
            if len(words) <= 1:
                return (3, len(words), cleaned.lower())
            return (4 + (1 if has_legal_suffix else 0) + (1 if has_article else 0), -len(words), cleaned.lower())

        variants = sorted(variants, key=or_variant_priority)
        expanded = []
        trailing_articles = []
        for variant in variants:
            if variant not in expanded:
                expanded.append(variant)
            for article in ("The", "A"):
                trailing = f"{variant}, {article}"
                if not re.search(rf",\s*{article}$", variant, re.I) and trailing not in trailing_articles:
                    trailing_articles.append(trailing)
        expanded.extend(item for item in trailing_articles if item not in expanded)
        best_result = None
        started = time.perf_counter()
        for variant in expanded[:20]:
            if best_result is not None and (time.perf_counter() - started) >= min(NAME_SEARCH_VARIANT_MAX_SECONDS, 45.0):
                return best_result
            active_org = org_with_name(org, variant)
            external_result = module.search_or(
                page,
                module.Organization(organization_name=active_org.organization_name, ein=active_org.ein),
            )
            result = copy_external_result(org, "OR", external_result)
            if public_status(result) == "Site Not Reachable":
                return result
            if not result_is_retryable_name_miss(result):
                registry_name = or_registry_name_from_detail() or best_or_registry_name_from_page() or variant
                if or_detail_ein_mismatches(registry_name):
                    best_result = checker.StateResult(
                        org.organization_name,
                        org.ein,
                        "OR",
                        checker.STATUS_NOT_REGISTERED,
                        getattr(external_result, "source_url", "") or "",
                        raw_status_text="Oregon detail EIN did not match the requested EIN",
                        source_note="Oregon returned a same/similar-name detail record, but its Federal EIN did not match the requested organization.",
                        success=True,
                    )
                    continue
                if registry_name and or_detail_name_mismatches(registry_name):
                    best_result = checker.StateResult(
                        org.organization_name,
                        org.ein,
                        "OR",
                        checker.STATUS_NOT_REGISTERED,
                        getattr(external_result, "source_url", "") or "",
                        raw_status_text="Oregon detail name did not safely match the requested organization",
                        source_note="Oregon returned an EIN/name detail record, but the registry name did not safely match the requested organization or a compatible public alias.",
                        success=True,
                    )
                    continue
                if not result.matched_registry_name:
                    result.matched_registry_name = registry_name
                return result
            best_candidate_name = best_or_registry_name_from_page()
            if best_candidate_name:
                external_result = module.search_or(
                    page,
                    module.Organization(organization_name=best_candidate_name, ein=org.ein),
                )
                result = copy_external_result(org, "OR", external_result)
                if not result.matched_registry_name:
                    result.matched_registry_name = or_registry_name_from_detail() or best_candidate_name
                if or_detail_ein_mismatches(result.matched_registry_name or best_candidate_name):
                    best_result = checker.StateResult(
                        org.organization_name,
                        org.ein,
                        "OR",
                        checker.STATUS_NOT_REGISTERED,
                        getattr(external_result, "source_url", "") or "",
                        raw_status_text="Oregon detail EIN did not match the requested EIN",
                        source_note="Oregon returned a same/similar-name detail record, but its Federal EIN did not match the requested organization.",
                        success=True,
                    )
                    continue
                if (result.matched_registry_name or best_candidate_name) and or_detail_name_mismatches(result.matched_registry_name or best_candidate_name):
                    best_result = checker.StateResult(
                        org.organization_name,
                        org.ein,
                        "OR",
                        checker.STATUS_NOT_REGISTERED,
                        getattr(external_result, "source_url", "") or "",
                        raw_status_text="Oregon detail name did not safely match the requested organization",
                        source_note="Oregon returned an EIN/name detail record, but the registry name did not safely match the requested organization or a compatible public alias.",
                        success=True,
                    )
                    continue
                if public_status(result) == "Site Not Reachable":
                    return result
                if not result_is_retryable_name_miss(result):
                    return result
            best_result = result
        return best_result or copy_external_result(org, "OR", module.search_or(page, bundle_org))
    else:
        raise ValueError(f"Unsupported bundled extension state: {state}")
    return copy_external_result(org, state, external_result)


def search_co_with_name_fallback(page, org):
    result = checker.search_co(page, org)
    if public_status(result) != "Not Registered":
        return result
    for variant in organization_name_variants(
        org.organization_name,
        org.ein,
        include_ein_aliases=True,
        include_name_segments=True,
        include_compact_legal_suffixes=True,
        include_leading_article_variants=True,
        include_broad_query_prefixes=False,
    )[:8]:
        variant_org = SimpleNamespace(organization_name=variant, ein="")
        fallback = checker.search_co(page, variant_org)
        if public_status(fallback) == "Site Not Reachable":
            return copy_name_fallback_result(org, fallback)
        if public_status(fallback) == "Not Registered":
            continue
        if result_registry_name_is_safe(fallback, org.organization_name, org.ein):
            fallback.source_note = (
                (fallback.source_note or "Colorado public search found a matching organization-name record.")
                + " CharityClarity used a name fallback after the EIN search returned no matching record."
            )
            return copy_name_fallback_result(org, fallback)
    return result


def search_mi_name_fallback(page, org):
    module = state_extension_module("MI")
    result = checker.StateResult(org.organization_name, org.ein, "MI", checker.STATUS_NOT_REGISTERED, "")
    safe_targets = organization_match_target_variants(org.organization_name, org.ein)
    started = time.perf_counter()
    variants = []
    for variant in organization_name_variants(
        org.organization_name,
        org.ein,
        include_ein_aliases=True,
        include_name_segments=True,
        include_compact_legal_suffixes=True,
        include_leading_article_variants=True,
        include_broad_query_prefixes=False,
    ):
        variant_words = re.findall(r"[A-Za-z0-9]+", variant or "")
        substantive_variant_words = [
            word for word in variant_words
            if word.lower() not in {"the", "a", "an", "inc", "incorporated", "corp", "corporation", "llc", "ltd", "limited"}
        ]
        if len(substantive_variant_words) < 2:
            continue
        if variant not in variants:
            variants.append(variant)
    if not variants:
        result.status = checker.STATUS_NOT_REGISTERED
        result.raw_status_text = "No matching organization record"
        result.source_note = "Michigan EIN search returned no exact result, and no narrow structural name fallback was appropriate."
        result.success = True
        result.error = ""
        return result
    def mi_variant_priority(value: str) -> tuple[int, int, str]:
        cleaned = re.sub(r"\s+", " ", value or "").strip()
        has_legal_suffix = bool(re.search(r"\b(inc\.?|incorporated|corp\.?|corporation|llc|ltd\.?|limited)\b", cleaned, re.I))
        has_comma = "," in cleaned
        has_generated_punctuation = bool(re.search(r"[-/\\]", cleaned))
        return (
            2 if has_legal_suffix or has_comma else (1 if has_generated_punctuation else 0),
            len(cleaned.split()),
            cleaned.lower(),
        )

    variants = sorted(variants, key=mi_variant_priority)

    for variant in variants[:5]:
        if time.perf_counter() - started > 22:
            result.status = checker.STATUS_NOT_REGISTERED
            result.raw_status_text = "No matching organization record"
            result.source_note = "Michigan EIN search returned no exact result, and the bounded organization-name fallback found no matching record before the safe retry limit."
            result.success = True
            result.error = ""
            return result
        try:
            if not module.open_search_form(page):
                result.error = "MI: Could not reopen search form for name fallback"
                return result
            page.locator("#ctl00_MainContent_txtName").fill("")
            page.locator("#ctl00_MainContent_txtName").fill(variant)
            page.locator("#ctl00_MainContent_txtEIN").fill("")
            page.locator("#ctl00_MainContent_btnTextSearch").click(timeout=10000, no_wait_after=True)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=6000)
            except Exception:
                pass
            time.sleep(2)
            frame = module.find_results_frame(page)
            if not frame:
                continue
            results_text = re.sub(r"\s+", " ", module.body_text(frame, timeout=15000)).strip()
            if no_registry_results_seen(results_text):
                continue
            chosen = module.choose_result_link(frame, variant) or module.choose_result_link(frame, "")
            if not chosen:
                continue
            _, clicked_name, link, href = chosen
            clicked_name_score = target_name_score(clicked_name, safe_targets)
            if clicked_name_score < 0:
                try:
                    checker_score = checker.candidate_selection_score_for_targets(results_text, safe_targets, results_text)
                    if checker_score[0] < 0:
                        pass
                    else:
                        clicked_name_score = 450 + checker_score[0]
                except Exception:
                    pass
            if clicked_name_score >= 0:
                row_window_match = re.search(
                    rf"(?P<id>\b\d{{3,8}}\b)?\s*{re.escape(clicked_name)}[\s\S]{{0,220}}?(?P<date>\d{{1,2}}/\d{{1,2}}/\d{{2,4}})",
                    results_text,
                    re.I,
                )
                if row_window_match:
                    expiration_date = parse_due_date(row_window_match.group("date"))
                    if expiration_date:
                        result.status = classify_expiration_date(expiration_date)
                        result.raw_status_text = (
                            f"License / Registration Expiration: {format_date(expiration_date)} | "
                            "Matched by organization name after EIN search returned no exact result"
                        )
                        result.source_note = "MI tried EIN search first, then used the public organization-name search result row when the EIN field returned no exact result."
                        result.matched_registry_name = clean_registry_name(clicked_name)
                        result.matched_registry_identifier = row_window_match.group("id") or ""
                        result.success = True
                        result.error = ""
                        return result
            module.click_result_link(frame, link, href)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=6000)
            except Exception:
                pass
            time.sleep(2)
            detail_frame = module.find_detail_frame(page)
            if not detail_frame:
                continue
            detail_text = re.sub(r"\s+", " ", module.body_text(detail_frame, timeout=15000)).strip()
            site_name = module.extract_legal_name(detail_frame) or clicked_name or org.organization_name
            ein_digits = re.sub(r"\D", "", org.ein or "")
            ein_confirmed = bool(ein_digits and ein_digits in re.sub(r"\D", "", detail_text))
            if not ein_confirmed and clicked_name_score < 0 and target_name_score(site_name, safe_targets) < 0:
                continue
            raw_status = module.extract_solicitation_status(detail_frame)
            charitable_trust_status = module.extract_charitable_trust_status(detail_frame)
            if not raw_status and not charitable_trust_status:
                continue
            result.status = classify_mi_solicitation_status(raw_status) or external_status_to_checker_status(module.classify_mi_status(raw_status, ""))
            result.raw_status_text = (
                f"Solicitation Registration Status: {raw_status or 'N/A'} | "
                f"Charitable Trust Registration Status: {charitable_trust_status or 'N/A'} | "
                "Matched by organization name after EIN search returned no exact result"
            )
            result.source_note = "MI tried EIN search first, then used the public organization-name search when the EIN field returned no exact result."
            result.matched_registry_name = clean_registry_name(site_name)
            result.success = True
            return result
        except Exception as exc:
            result.error = f"MI name fallback error: {exc}"
            return result
    result.status = checker.STATUS_NOT_REGISTERED
    result.raw_status_text = "No matching organization record"
    result.source_note = "Michigan EIN and organization-name searches returned no matching result."
    result.success = True
    result.error = ""
    return result


def classify_expiration_date(exp_date: date | None) -> str:
    if not exp_date:
        return checker.STATUS_UNKNOWN
    return status_from_calendar_date(exp_date)


def readable_page_text(page) -> str:
    try:
        return page.locator("body").inner_text(timeout=10000)
    except Exception:
        return registry_page_body(page)


def no_registry_results_seen(text: str) -> bool:
    return bool(re.search(
        r"\b(no\s+(?:matching\s+)?(?:records?|results?|organizations?|licenses?)\s+(?:found|match)|"
        r"showing\s+0\s+results?|0\s+(?:records?|results?)|your\s+search\s+returned\s+no|sorry,\s+there\s+are\s+no\s+matches|did\s+not\s+match\s+any)\b",
        text or "",
        re.I,
    ))


def first_date_near_label(text: str, labels: list[str]) -> date | None:
    readable = re.sub(r"\s+", " ", text or "")
    for label in labels:
        pattern = rf"{label}\s*:?\s*([A-Za-z]{{3,9}}\s+\d{{1,2}},\s+\d{{4}}|\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}}|\d{{4}}-\d{{1,2}}-\d{{1,2}})"
        match = re.search(pattern, readable, re.I)
        if match:
            parsed = parse_due_date(match.group(1))
            if parsed:
                return parsed
    return None


def best_row_with_link_by_name(page, targets: list[str], link_pattern: str = r"details|view|select|license") -> tuple[object | None, str]:
    rows = page.locator("tr")
    best_row = None
    best_text = ""
    best_score = (-999, -999)
    try:
        count = min(rows.count(), 80)
    except Exception:
        count = 0
    for index in range(count):
        row = rows.nth(index)
        try:
            text = re.sub(r"\s+", " ", row.inner_text(timeout=1500)).strip()
        except Exception:
            continue
        if not text:
            continue
        try:
            if row.locator("a, button, input[type='submit'], input[type='button']").count() == 0:
                continue
        except Exception:
            continue
        try:
            score = checker.candidate_selection_score_for_targets(text, targets, text)
        except Exception:
            score = (1, len(text)) if any((target or "").lower() in text.lower() for target in targets) else (-1, len(text))
        if score[0] < 0:
            normalized_text = re.sub(r"\b(the|a|an)\b", " ", re.sub(r"[^a-z0-9]+", " ", text.lower()))
            normalized_text = re.sub(r"\s+", " ", normalized_text).strip()
            for target in targets:
                normalized_target = re.sub(r"\b(the|a|an)\b", " ", re.sub(r"[^a-z0-9]+", " ", (target or "").lower()))
                normalized_target = re.sub(r"\s+", " ", normalized_target).strip()
                if normalized_target and normalized_target in normalized_text:
                    score = (1, len(normalized_target))
                    break
        if score > best_score:
            best_score = score
            best_row = row
            best_text = text
    if best_row is None or best_score[0] < 0:
        return None, ""
    links = best_row.locator("a, button, input[type='submit'], input[type='button']")
    try:
        count = links.count()
    except Exception:
        count = 0
    for index in range(count):
        link = links.nth(index)
        try:
            label = " ".join([
                link.inner_text(timeout=750) if link.evaluate("el => el.tagName.toLowerCase() !== 'input'") else "",
                link.get_attribute("value") or "",
                link.get_attribute("title") or "",
                link.get_attribute("aria-label") or "",
            ])
        except Exception:
            label = ""
        if re.search(link_pattern, label or "", re.I):
            return link, best_text
    return best_row.locator("a, button").first if count else None, best_text


def normalized_match_name(value: str) -> str:
    normalized = checker.normalize_name(value or "") if hasattr(checker, "normalize_name") else re.sub(r"\W+", " ", (value or "").lower()).strip()
    normalized = re.sub(r"\b(the|a|an|inc|incorporated|corp|corporation|llc|ltd|limited)\b", " ", normalized, flags=re.I)
    return re.sub(r"\s+", " ", normalized).strip()


def target_name_score(row_name: str, targets: list[str]) -> int:
    row_norm = normalized_match_name(row_name)
    if not row_norm:
        return -1000
    best = -1000
    for target in targets:
        target_norm = normalized_match_name(target)
        if not target_norm:
            continue
        if row_norm == target_norm:
            best = max(best, 1000)
        elif row_norm.startswith(target_norm) or target_norm.startswith(row_norm):
            shorter = min(len(row_norm.split()), len(target_norm.split()))
            if shorter >= 3:
                best = max(best, 700 + shorter)
        elif target_norm in row_norm or row_norm in target_norm:
            shorter = min(len(row_norm.split()), len(target_norm.split()))
            if shorter >= 3:
                best = max(best, 450 + shorter)
    return best


def clean_registry_name(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", (value or "").strip())
    cleaned = re.sub(r"\s*/\s*DBA\s*/\s*Nickname\s*:?.*$", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"\s+\b(?:aka|d/?b/?a|f/?k/?a|formerly(?:\s+known\s+as)?)\b\s+.*$", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"\b(Credential|License/Registration Number|Status|Expiration Date)\b.*$", "", cleaned, flags=re.I).strip()
    return cleaned.strip(" :-")


def useful_registry_name(value: str) -> str:
    cleaned = clean_registry_name(value)
    normalized = re.sub(r"[^a-z0-9]+", "", cleaned.lower())
    if not cleaned or len(normalized) < 4:
        return ""
    if re.fullmatch(r"s|name|names|organization|charity|dba|nickname|title", normalized, re.I):
        return ""
    if re.search(r"\b(search|advanced search|word phrase ein|no records?|results?)\b", cleaned, re.I):
        return ""
    if re.search(r"\b(Registration\s+Number|FEIN|Federal\s+EIN|Status|Expiration\s+Date)\b", cleaned, re.I):
        return ""
    return cleaned


def fill_registry_match_from_text(result, body: str, org) -> None:
    if (getattr(result, "matched_registry_name", "") or "").strip():
        result.matched_registry_name = useful_registry_name(result.matched_registry_name)
        return
    if public_status(result) == "Not Registered":
        return
    text_sources = [
        body or "",
        getattr(result, "raw_status_text", "") or "",
        getattr(result, "source_note", "") or "",
    ]
    combined_text = "\n".join(text_sources)
    readable = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", combined_text or ""))).strip()
    if not readable:
        return
    candidates = []
    for label in ["Organization Name", "Organization name", "Charity Name", "Business Name", "Legal Name", "Entity Name", "Name"]:
        candidate = useful_registry_name(text_between_labels(readable, label, [
            "FEIN", "Federal EIN", "Federal ID", "EIN", "Status", "Registration Status",
            "Registration Number", "License Number", "License", "Credential",
            "Expiration Date", "Address", "City", "State",
        ]))
        if candidate:
            candidates.append(candidate)
    ein_digits = re.sub(r"\D", "", getattr(org, "ein", "") or getattr(result, "ein", "") or "")
    if ein_digits:
        for line in re.split(r"[\r\n]+|\s{2,}", combined_text or ""):
            line_text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", line))).strip()
            if not line_text or ein_digits not in re.sub(r"\D", "", line_text):
                continue
            line_name = ""
            ein_pattern = rf"{re.escape(ein_digits[:2])}-?{re.escape(ein_digits[2:])}"
            ein_match = re.search(ein_pattern, line_text)
            if ein_match:
                after_ein = line_text[ein_match.end():].strip(" :-")
                line_name = useful_registry_name(re.split(r"\s+\d{2,}\b|\b(?:Status|Registration|License|Expiration|Address|City|State)\b", after_ein, maxsplit=1, flags=re.I)[0])
            if not line_name:
                line_name = useful_registry_name(re.split(r"\b(?:FEIN|Federal\s+EIN|Federal\s+ID|EIN|Status|Registration)\b", line_text, maxsplit=1, flags=re.I)[0])
            if line_name:
                candidates.append(line_name)
    safe_targets = organization_match_target_variants(getattr(org, "organization_name", "") or getattr(result, "organization_name", ""), getattr(org, "ein", "") or getattr(result, "ein", ""))
    best_name = ""
    best_score = -10000
    for candidate in candidates:
        score = target_name_score(candidate, safe_targets)
        if score > best_score:
            best_name = candidate
            best_score = score
    if best_name and best_score >= 450:
        result.matched_registry_name = best_name
    elif (
        (getattr(result, "state", "") or "").upper() in {"AK", "MA", "MD", "MI", "MN", "PA"}
        and public_status(result) not in {"Not Registered", "Site Not Reachable"}
        and (getattr(org, "organization_name", "") or "").strip()
    ):
        result.matched_registry_name = re.sub(r"\s+", " ", getattr(org, "organization_name", "")).strip()


def text_between_labels(text: str, start_label: str, end_labels: list[str]) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if not compact:
        return ""
    end_pattern = "|".join(re.escape(label) for label in end_labels)
    match = re.search(rf"{re.escape(start_label)}\s*:?\s*(.*?)(?=\s+(?:{end_pattern})\s*:?\s|$)", compact, re.I)
    return re.sub(r"\s+", " ", match.group(1)).strip(" :-") if match else ""


def click_nth_details_control(page, index: int) -> bool:
    locator = page.locator("a, button, input[type='button'], input[type='submit']")
    try:
        count = locator.count()
    except Exception:
        return False
    seen = 0
    for item_index in range(count):
        item = locator.nth(item_index)
        try:
            label = " ".join([
                item.inner_text(timeout=500) if item.evaluate("el => el.tagName.toLowerCase() !== 'input'") else "",
                item.get_attribute("value") or "",
                item.get_attribute("title") or "",
                item.get_attribute("aria-label") or "",
            ])
        except Exception:
            continue
        if not re.search(r"details|view", label or "", re.I):
            continue
        if seen == index:
            try:
                item.click(timeout=5000)
            except Exception:
                item.click(force=True, timeout=5000)
            return True
        seen += 1
    return False


def search_ct(page, org):
    url = "https://www.elicense.ct.gov/lookup/licenselookup.aspx"
    original_name = org.organization_name
    safe_targets = organization_match_target_variants(original_name, org.ein)
    for target in list(safe_targets):
        if not re.search(r"^\s*(the|a)\s+", target, re.I):
            for suffix in (f"{target} (THE)", f"{target}, THE", f"{target}, The"):
                if suffix not in safe_targets:
                    safe_targets.append(suffix)
    best_result = None
    for variant in organization_name_variants(
        original_name,
        org.ein,
        include_ein_aliases=True,
        include_name_segments=True,
        include_compact_legal_suffixes=True,
        include_leading_article_variants=True,
    )[:14]:
        result = checker.StateResult(original_name, org.ein, "CT", checker.STATUS_UNKNOWN, url)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            checker.safe_wait_for_network_idle(page, timeout=8000)
            input_box = checker.find_visible_input(page, [
                '#ctl00_MainContentPlaceHolder_ucLicenseLookup_ctl03_tbDBA_Contact',
                'input[name*="tbDBA_Contact"]',
                'input[name*="Business" i]',
                'input[id*="Business" i]',
                'input[type="text"]',
            ])
            if not input_box:
                result.error = "CT: Could not find public registry search input"
                return result
            input_box.fill("")
            input_box.fill(variant)
            try:
                page.locator("#ctl00_MainContentPlaceHolder_ucLicenseLookup_btnLookup, input[type='submit']").first.click(timeout=5000)
            except Exception:
                page.keyboard.press("Enter")
            checker.safe_wait_for_network_idle(page, timeout=10000)
            try:
                page.get_by_text(re.compile(r"Showing\s+\d+\s+result", re.I)).wait_for(timeout=8000)
            except Exception:
                time.sleep(4)
            text = readable_page_text(page)
            if no_registry_results_seen(text):
                result.status = checker.STATUS_NOT_REGISTERED
                result.raw_status_text = "No matching organization record"
                result.source_note = "Connecticut public registry returned no matching record for the generated name variants."
                result.success = True
                best_result = result
                continue
            candidate_rows = page.evaluate(
                """
                () => Array.from(document.querySelectorAll('tr')).map((row, index) => {
                    const text = (row.innerText || row.textContent || '').replace(/\\s+/g, ' ').trim();
                    const detailControl = Array.from(row.querySelectorAll('a,button,input')).find((el) => {
                        const label = ((el.innerText || el.textContent || '') + ' ' + (el.value || '') + ' ' + (el.title || '')).trim();
                        return /details|view/i.test(label);
                    });
                    const hasDetails = Array.from(row.querySelectorAll('a,button,input')).some((el) => {
                        const label = ((el.innerText || el.textContent || '') + ' ' + (el.value || '') + ' ' + (el.title || '')).trim();
                        return /details|view/i.test(label);
                    });
                    return { index, text, hasDetails, detailHref: detailControl ? (detailControl.getAttribute('href') || '') : '' };
                }).filter((row) => row.hasDetails && row.text && /PUBLIC CHARITY|CHR\\./i.test(row.text));
                """
            )
            best_candidate = None
            best_score = -10000
            details_index = 0
            for candidate in candidate_rows:
                row_text = re.sub(r"\s+", " ", candidate.get("text") or "").strip()
                row_name = clean_registry_name(re.split(r"\bCredential\b|\bStatus\b|\bLicense\b", row_text, maxsplit=1, flags=re.I)[0])
                name_score = target_name_score(row_name, safe_targets)
                if name_score < 0:
                    details_index += 1
                    continue
                score = name_score
                if re.search(r"\bPUBLIC\s+CHARITY\b|\bCHR\.", row_text, re.I):
                    score += 80
                else:
                    score -= 250
                if re.search(r"\bStatus\s+ACTIVE\b|\bACTIVE\b|\bStatus\s+Reason\s+CURRENT\b", row_text, re.I):
                    score += 180
                if re.search(r"\bEXEMPT\b", row_text, re.I):
                    score += 10
                if re.search(r"\bINACTIVE\b|\bCLOSED\b|\bWITHDRAWN\b|\bCANCEL(?:ED|LED)\b", row_text, re.I):
                    score -= 180
                if re.search(r"\bSCIENTIFIC\s+RESEARCH\b|\bRESEARCH\s+CERTIFICATE\b", row_text, re.I):
                    score -= 300
                if score > best_score:
                    best_score = score
                    best_candidate = {**candidate, "details_index": details_index, "row_text": row_text, "row_name": row_name}
                details_index += 1
            if not best_candidate:
                continue
            row_text = best_candidate["row_text"]
            clicked_detail = False
            detail_href = (best_candidate.get("detailHref") or "").strip()
            if detail_href.lower().startswith("javascript:"):
                try:
                    clicked_detail = bool(page.evaluate("(href) => { eval(href.slice(11)); return true; }", detail_href))
                except Exception:
                    clicked_detail = False
            if not clicked_detail and not click_nth_details_control(page, best_candidate["details_index"]):
                continue
            checker.safe_wait_for_network_idle(page, timeout=10000)
            try:
                page.get_by_text(re.compile(r"License\s+Details|Credential\s+Details", re.I)).wait_for(timeout=6000)
            except Exception:
                time.sleep(4)
            time.sleep(2)
            detail_text = readable_page_text(page)
            detail_segment = detail_text
            for marker in ("License Details", "Lookup Detail View"):
                marker_index = detail_segment.rfind(marker)
                if marker_index >= 0:
                    detail_segment = detail_segment[marker_index:]
                    break
            if detail_segment == detail_text and not re.search(r"Registration\s+Information|Expiration\s+Date", detail_segment, re.I):
                detail_segment = row_text
            exp_date = first_date_near_label(detail_segment, ["Expiration Date", "Expiration", "Expires", "Expire Date"])
            matched_name = clean_registry_name(
                checker.extract_labeled_value_from_text(detail_segment, ["Business Name", "DBA Name", "Name and Address", "Name", "Licensee Name", "Organization Name"])
                or best_candidate.get("row_name", "")
            )
            credential = text_between_labels(detail_segment, "Credential", ["Credential Description", "Registration Type", "Status", "Effective Date", "Expiration Date"]) or text_between_labels(row_text, "Credential", ["Credential Description", "Registration Type", "Status", "Effective Date", "Expiration Date"])
            credential_description = text_between_labels(detail_segment, "Credential Description", ["Registration Type", "Status", "Effective Date", "Expiration Date"]) or text_between_labels(row_text, "Credential Description", ["Department", "Status", "Effective Date", "Expiration Date"])
            registration_type = text_between_labels(detail_segment, "Registration Type", ["Status", "Effective Date", "Expiration Date", "Status Reason"])
            status_text = text_between_labels(detail_segment, "Status", ["Status Reason", "Effective Date", "Expiration Date", "Credential", "Registration Type"]) or text_between_labels(row_text, "Status", ["Status Reason", "City", "DBA", "Details"])
            status_reason = text_between_labels(detail_segment, "Status Reason", ["Effective Date", "Expiration Date", "Credential", "Registration Type"]) or text_between_labels(row_text, "Status Reason", ["City", "DBA", "Details"])
            status_after_expiration = re.search(r"Expiration\s+Date\s+\d{1,2}/\d{1,2}/\d{2,4}\s+Status\s+([A-Z ]{3,40})(?:\s+\d{1,2}/\d{1,2}/\d{4}|$)", detail_segment, re.I)
            if status_after_expiration:
                status_text = re.sub(r"\s+", " ", status_after_expiration.group(1)).strip()
            combined_detail = " ".join([detail_segment, row_text, credential, credential_description, registration_type, status_text, status_reason])
            result.matched_registry_name = matched_name
            credential_match = re.search(r"\b[A-Z]{2,5}\.[0-9A-Z.-]+", " ".join([credential, row_text, detail_segment]))
            result.matched_registry_identifier = credential_match.group(0) if credential_match else (checker.extract_registry_identifier_from_text(detail_text, org.ein) if hasattr(checker, "extract_registry_identifier_from_text") else "")
            if re.search(r"\bEXEMPT\b", " ".join([credential, credential_description, registration_type, row_text]), re.I):
                result.status = "Exempt"
            elif re.search(r"\b(non\W*compliant|not\s+in\s+compliance)\b", combined_detail, re.I):
                result.status = checker.STATUS_DELINQUENT
            elif re.search(r"\bINACTIVE\b", status_text or combined_detail, re.I):
                result.status = "Closed / Withdrawn / Canceled"
            elif exp_date:
                result.status = classify_expiration_date(exp_date)
            elif re.search(r"\bStatus\s+ACTIVE\b|\bStatus\s+Reason\s+CURRENT\b|\bACTIVE\s+Status\s+Reason\s+CURRENT\b", detail_text, re.I):
                result.status = checker.STATUS_CURRENT
            else:
                result.status = checker.STATUS_UNKNOWN
            result.raw_status_text = " | ".join(
                item for item in [
                    f"Status: {status_text}" if status_text else "",
                    f"Status Reason: {status_reason}" if status_reason else "",
                    f"Registration Type: {registration_type}" if registration_type else "",
                    f"Credential Description: {credential_description}" if credential_description else "",
                    f"Expiration Date {format_date(exp_date)}" if exp_date else "",
                ]
            ) or "Connecticut registry record found"
            result.source_note = "CT uses the selected public-registry detail record, including exemption, noncompliance, and expiration fields."
            result.success = True
            return result
        except Exception as exc:
            result.error = f"CT error: {exc}"
            return result
    return best_result or checker.StateResult(original_name, org.ein, "CT", checker.STATUS_NOT_REGISTERED, url, raw_status_text="No matching organization record", source_note="Connecticut public registry returned no matching record for the generated name variants.", success=True)


def search_fl(page, org):
    url = "https://csapp.fdacs.gov/CSPublicApp/CheckACharity/CheckACharity.aspx"
    original_name = org.organization_name
    safe_targets = organization_match_target_variants(original_name, org.ein)
    lookup_started = time.monotonic()
    deadline = lookup_started + FL_LOOKUP_MAX_SECONDS

    def remaining_seconds() -> float:
        return max(0.0, deadline - time.monotonic())

    def remaining_ms(default_ms: int, minimum_ms: int = 1000) -> int:
        remaining = int(remaining_seconds() * 1000)
        if remaining <= minimum_ms:
            return minimum_ms
        return min(default_ms, remaining)

    def deadline_expired() -> bool:
        return time.monotonic() >= deadline

    def clean_fl_registry_name(value: str) -> str:
        cleaned = clean_registry_name(value)
        cleaned = re.sub(r"\s+\bAlso\s+Soliciting\s+as\b.*$", "", cleaned, flags=re.I).strip()
        cleaned = re.sub(r"\s+\bPrint\b\s*$", "", cleaned, flags=re.I).strip()
        cleaned = re.sub(r",\s*[A-Z][A-Z .'-]+,\s*[A-Z]{2}\s*$", "", cleaned).strip()
        return cleaned.strip(" ,-")

    def florida_local_chapter_mismatch(row_name: str) -> bool:
        row_norm = normalized_match_name(row_name)
        target_norms = [normalized_match_name(target) for target in safe_targets]
        if not row_norm or not target_norms:
            return False
        if re.search(r"\bchapter\b", row_norm, re.I) and not any(re.search(r"\bchapter\b", target, re.I) for target in target_norms):
            return True
        if re.search(r"\bflorida\s+chapter\b|\bfl\s+chapter\b", row_norm, re.I) and not any(re.search(r"\bflorida\s+chapter\b|\bfl\s+chapter\b", target, re.I) for target in target_norms):
            return True
        return False

    def florida_related_entity_mismatch(row_name: str) -> bool:
        row_norm = normalized_match_name(row_name)
        target_norms = [normalized_match_name(target) for target in safe_targets]
        related_entity_terms = [
            "action fund",
            "political action",
            "pac",
            "auxiliary",
            "chapter",
        ]
        for term in related_entity_terms:
            term_norm = normalized_match_name(term)
            if term_norm and term_norm in row_norm and not any(term_norm in target for target in target_norms):
                return True
        return False

    def florida_nested_unrelated_entity_mismatch(row_name: str) -> bool:
        row_norm = normalized_match_name(row_name)
        target_norms = [normalized_match_name(target) for target in safe_targets]
        if not row_norm or not target_norms:
            return False
        generic = {
            "the", "a", "an", "of", "for", "and", "to", "in", "on", "at", "by",
            "inc", "incorporated", "corp", "corporation", "llc", "ltd", "limited",
            "foundation", "fund", "charity", "charities", "association", "society",
            "center", "centre", "institute", "organization", "university",
        }
        row_words = set(row_norm.split())
        for target_norm in target_norms:
            if not target_norm or target_norm == row_norm:
                return False
            if row_norm.startswith(target_norm + " "):
                return False
            if re.search(rf"\b(?:foundation|fund|friends)\s+of\s+(?:the\s+)?{re.escape(target_norm)}$", row_norm):
                return False
            if target_norm in row_norm:
                target_words = set(target_norm.split())
                extra_words = row_words - target_words - generic
                if len(extra_words) >= 2:
                    return True
        return False

    def useful_fl_search_variant(variant: str) -> bool:
        norm = normalized_match_name(variant)
        if not norm:
            return False
        generic = {
            "the", "a", "an", "of", "for", "and", "to", "in", "on", "at", "by",
            "inc", "incorporated", "corp", "corporation", "llc", "ltd", "limited",
            "co", "company", "foundation", "fund", "charity", "charities",
            "association", "society", "center", "centre", "institute",
            "organization",
        }
        meaningful = [word for word in norm.split() if word not in generic]
        if not meaningful:
            return False
        if len(meaningful) == 1 and len(meaningful[0]) < 4:
            return False
        return True

    def load_fl_search_page():
        last_error = None
        for attempt in range(2):
            if deadline_expired():
                raise TimeoutError("FL lookup exceeded its bounded search window")
            try:
                page.goto(url, wait_until="commit", timeout=remaining_ms(12000))
                return
            except Exception as exc:
                last_error = exc
                try:
                    page.evaluate("window.stop()")
                except Exception:
                    pass
                try:
                    page.goto("about:blank", wait_until="commit", timeout=remaining_ms(3000))
                except Exception:
                    pass
                if attempt == 0:
                    time.sleep(min(1, remaining_seconds()))
        raise last_error

    generated_variants = organization_name_variants(
        original_name,
        org.ein,
        include_ein_aliases=True,
        include_name_segments=True,
        include_and_segments=False,
        include_compact_legal_suffixes=True,
        include_leading_article_variants=True,
        include_broad_query_prefixes=False,
    )
    original_has_hyphen = "-" in (original_name or "")
    variants = []
    variant_keys = set()
    for variant in generated_variants:
        # Florida's partial-name search is slow and sometimes stalls when hit
        # repeatedly. Avoid synthetic hyphen probes unless the source name
        # actually contains a hyphen; legal suffix/article variants preserve
        # the useful coverage without multiplying no-match page loads.
        if not original_has_hyphen and "-" in variant:
            continue
        if not useful_fl_search_variant(variant):
            continue
        variant_key = (
            normalized_match_name(variant),
            bool(re.search(r"\b(?:inc|incorporated|corp|corporation|ltd|limited|llc)\.?\b", variant, re.I)),
        )
        if variant_key not in variant_keys:
            variant_keys.add(variant_key)
            variants.append(variant)
    best_result = None
    last_error = None
    for variant in variants[:8]:
        if deadline_expired():
            break
        result = checker.StateResult(original_name, org.ein, "FL", checker.STATUS_UNKNOWN, url)
        try:
            try:
                page.set_default_timeout(remaining_ms(8000))
                page.set_default_navigation_timeout(remaining_ms(12000))
            except Exception:
                pass
            load_fl_search_page()
            try:
                page.locator('input[name*="BusinessName" i], input[id*="BusinessName" i], input[type="text"]').first.wait_for(state="visible", timeout=remaining_ms(6000))
            except Exception:
                checker.safe_wait_for_network_idle(page, timeout=remaining_ms(3000))
            input_box = checker.find_visible_input(page, [
                'input[name*="BusinessName" i]',
                'input[id*="BusinessName" i]',
                'input[name*="Organization" i]',
                'input[type="text"]',
            ])
            if not input_box:
                result.error = "FL: Could not find Business Name input"
                return result
            input_box.fill("", timeout=remaining_ms(4000))
            input_box.fill(variant, timeout=remaining_ms(4000))
            try:
                page.get_by_role("button", name=re.compile("search", re.I)).click(timeout=remaining_ms(4000), no_wait_after=True)
            except Exception:
                page.keyboard.press("Enter")
            checker.safe_wait_for_network_idle(page, timeout=remaining_ms(5000))
            time.sleep(min(0.5, remaining_seconds()))
            text = readable_page_text(page)
            if no_registry_results_seen(text):
                result.status = checker.STATUS_NOT_REGISTERED
                result.raw_status_text = "No matching organization record"
                result.source_note = "Florida Check-A-Charity returned no matching record for the generated name variants."
                result.success = True
                best_result = result
                continue
            candidate_rows = page.evaluate(
                """
                () => Array.from(document.querySelectorAll('tr')).map((row) => {
                    const text = (row.innerText || row.textContent || '').replace(/\\s+/g, ' ').trim();
                    return { text };
                }).filter((row) => row.text && /License\\/Registration Number|Expiration Date|Solicitation|Business Name|CH\\d+/i.test(row.text));
                """
            )
            best_candidate = None
            best_score = -10000
            for candidate in candidate_rows:
                row_text = re.sub(r"\s+", " ", candidate.get("text") or "").strip()
                row_name = (
                    text_between_labels(row_text, "Business Name", ["License/Registration Number", "Registration Number", "Expiration Date", "Status"])
                    or clean_fl_registry_name(re.split(r"\bLicense/Registration Number\b|\bRegistration Number\b|\bExpiration Date\b", row_text, maxsplit=1, flags=re.I)[0])
                )
                row_name = clean_fl_registry_name(row_name)
                name_score = target_name_score(row_name, safe_targets)
                if name_score < 0:
                    continue
                if re.search(r"\bAdvanced\s+Search\b", row_name, re.I):
                    continue
                if florida_local_chapter_mismatch(row_name):
                    continue
                if florida_related_entity_mismatch(row_name):
                    continue
                if florida_nested_unrelated_entity_mismatch(row_name):
                    continue
                score = name_score
                if re.search(r"\bCH\d+\b", row_text, re.I):
                    score += 40
                if score > best_score:
                    best_score = score
                    best_candidate = {"row_text": row_text, "row_name": row_name}
            if not best_candidate:
                result.status = checker.STATUS_NOT_REGISTERED
                result.raw_status_text = "No matching organization record"
                result.source_note = "Florida Check-A-Charity returned search results, but none safely matched the requested organization."
                result.success = True
                best_result = result
                continue
            row_text = best_candidate["row_text"]
            exp_date = first_date_near_label(row_text, ["Expiration Date", "Expiration", "Expires"])
            suspended_match = re.search(r"\bSuspended\b", row_text, re.I)
            revoked_match = re.search(r"\bRevoked\b", row_text, re.I)
            if not exp_date:
                if suspended_match:
                    result.status = "Suspended"
                    result.raw_status_text = "Status: Suspended"
                    result.source_note = "FL uses the registration status shown next to the Check-A-Charity registration number."
                    result.matched_registry_name = clean_fl_registry_name(best_candidate["row_name"])
                    id_match = re.search(r"\bCH\d+\b", row_text, re.I)
                    result.matched_registry_identifier = id_match.group(0).upper() if id_match else ""
                    result.success = True
                    return result
                if revoked_match:
                    result.status = "Revoked"
                    result.raw_status_text = "Status: Revoked"
                    result.source_note = "FL uses the registration status shown next to the Check-A-Charity registration number."
                    result.matched_registry_name = clean_fl_registry_name(best_candidate["row_name"])
                    id_match = re.search(r"\bCH\d+\b", row_text, re.I)
                    result.matched_registry_identifier = id_match.group(0).upper() if id_match else ""
                    result.success = True
                    return result
                best_result = result
                continue
            if suspended_match:
                result.status = "Suspended"
                result.raw_status_text = f"Status: Suspended | Expiration Date {format_date(exp_date)}"
            elif revoked_match:
                result.status = "Revoked"
                result.raw_status_text = f"Status: Revoked | Expiration Date {format_date(exp_date)}"
            else:
                result.status = classify_expiration_date(exp_date)
                result.raw_status_text = f"Expiration Date {format_date(exp_date)}"
            result.source_note = "FL uses the expiration date shown by Check-A-Charity."
            result.matched_registry_name = clean_fl_registry_name(best_candidate["row_name"])
            id_match = re.search(r"\bCH\d+\b", row_text, re.I)
            result.matched_registry_identifier = id_match.group(0).upper() if id_match else ""
            result.success = True
            return result
        except Exception as exc:
            last_error = exc
            result.error = f"FL error: {exc}"
            if deadline_expired():
                break
            continue
    if best_result:
        if deadline_expired():
            best_result.source_note = " ".join(
                part for part in [
                    best_result.source_note,
                    "Florida Check-A-Charity reached the bounded lookup window before all generated name variants were attempted.",
                ] if part
            )
        return best_result
    if last_error:
        return checker.StateResult(
            original_name,
            org.ein,
            "FL",
            "Site Not Reachable",
            url,
            raw_status_text="Lookup could not be completed",
            source_note="Florida Check-A-Charity did not return a usable search result within the bounded lookup window.",
            success=False,
            error=f"FL error: {last_error}",
        )
    return checker.StateResult(original_name, org.ein, "FL", checker.STATUS_NOT_REGISTERED, url, raw_status_text="No matching organization record", source_note="Florida Check-A-Charity returned no matching record for the generated name variants.", success=True)


def mn_status_from_fiscal_year(year: int | None) -> str:
    if not year:
        return checker.STATUS_UNKNOWN
    try:
        next_report_due = date(year + 1, 12, 31)
    except ValueError:
        return checker.STATUS_UNKNOWN
    return status_from_calendar_date(next_report_due)


def search_mn(page, org):
    url = "https://www.ag.state.mn.us/Charity/Search/"
    result = checker.StateResult(org.organization_name, org.ein, "MN", checker.STATUS_UNKNOWN, url)
    ein_digits = re.sub(r"\D", "", org.ein or "")
    formatted_ein = format_ein(org.ein)
    search_values = []
    for value in [ein_digits, formatted_ein, org.ein]:
        value = (value or "").strip()
        if value and value not in search_values:
            search_values.append(value)
    try:
        for search_value in search_values:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            checker.safe_wait_for_network_idle(page, timeout=8000)
            input_box = checker.find_visible_input(page, [
                '#txtEIN',
                'input[name*="EIN" i]',
                'input[id*="EIN" i]',
                'input[name*="FEIN" i]',
                'input[type="text"]',
            ])
            if not input_box:
                result.error = "MN: Could not find EIN input"
                return result
            input_box.fill("")
            input_box.fill(search_value)
            try:
                page.locator('input[name="cmdSearch"], input[type="submit"]').last.click(timeout=5000)
            except Exception:
                page.keyboard.press("Enter")
            checker.safe_wait_for_network_idle(page, timeout=10000)
            time.sleep(1)
            text = readable_page_text(page)
            if no_registry_results_seen(text):
                result.status = checker.STATUS_NOT_REGISTERED
                result.raw_status_text = "No matching EIN result"
                result.source_note = "Minnesota Attorney General charity search returned no matching EIN record."
                result.success = True
                continue
            detail_link = None
            if ein_digits:
                detail_link = page.locator(f'a[href*="FederalID={ein_digits}"]').first
                try:
                    if detail_link.count() == 0:
                        detail_link = page.locator(f'a[href*="{formatted_ein}"]').first
                except Exception:
                    pass
            try:
                if not detail_link or detail_link.count() == 0:
                    detail_link = page.locator("a[href*='FederalID=']").first
            except Exception:
                detail_link = None
            if not detail_link or detail_link.count() == 0:
                result.status = checker.STATUS_NOT_REGISTERED
                result.raw_status_text = "No matching EIN result"
                result.source_note = "Minnesota Attorney General charity search did not expose a matching FederalID detail link for the requested EIN."
                result.success = True
                continue
            try:
                detail_link.click(timeout=5000)
                checker.safe_wait_for_network_idle(page, timeout=10000)
                time.sleep(1)
            except Exception:
                pass
            detail_text = readable_page_text(page)
            if ein_digits and ein_digits not in re.sub(r"\D", "", detail_text):
                result.status = checker.STATUS_NOT_REGISTERED
                result.raw_status_text = "No matching EIN result"
                result.source_note = "Minnesota search returned a possible record, but the public detail did not confirm the requested EIN."
                result.success = True
                continue
            year_match = re.search(r"(?:Fiscal\s+Year\s+Ending|For\s+Fiscal\s+Year\s+Ending)\s*:?\s*(?:\d{1,2}[/-]\d{1,2}[/-])?(20\d{2})", detail_text, re.I)
            year = int(year_match.group(1)) if year_match else None
            result.status = mn_status_from_fiscal_year(year)
            result.raw_status_text = f"Fiscal Year Ending {year}" if year else "Minnesota registry record found"
            result.source_note = "MN uses the latest fiscal year ending shown by the Attorney General charity search. CharityClarity tried both undashed and dashed EIN formats when needed."
            result.matched_registry_name = useful_registry_name(checker.extract_labeled_value_from_text(detail_text, ["Organization Name", "Charity Name", "Name"]))
            result.matched_registry_identifier = checker.extract_registry_identifier_from_text(detail_text, org.ein) if hasattr(checker, "extract_registry_identifier_from_text") else ""
            result.success = True
            return result
        safe_targets = organization_match_target_variants(org.organization_name, org.ein)
        for variant in organization_name_variants(
            org.organization_name,
            org.ein,
            include_ein_aliases=True,
            include_name_segments=True,
            include_compact_legal_suffixes=True,
            include_leading_article_variants=True,
            include_broad_query_prefixes=False,
        )[:10]:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            checker.safe_wait_for_network_idle(page, timeout=8000)
            org_box = checker.find_visible_input(page, ["#txtOrg", 'input[name="txtOrg"]'])
            if not org_box:
                break
            org_box.fill("")
            org_box.fill(variant)
            try:
                page.locator('input[name="cmdSearch"], input[type="submit"]').last.click(timeout=5000)
            except Exception:
                page.keyboard.press("Enter")
            checker.safe_wait_for_network_idle(page, timeout=10000)
            time.sleep(1)
            text = readable_page_text(page)
            if no_registry_results_seen(text):
                continue
            try:
                row_candidates = page.evaluate(
                    """
                    () => Array.from(document.querySelectorAll('table tr, tr')).map((row, index) => {
                        const text = (row.innerText || row.textContent || '').replace(/\\s+/g, ' ').trim();
                        const link = row.querySelector('a[href*="CHR_GeneralInfo"]');
                        return { index, text, linkText: link ? (link.innerText || link.textContent || '').replace(/\\s+/g, ' ').trim() : '' };
                    }).filter((row) => row.linkText && row.text);
                    """
                )
            except Exception:
                row_candidates = []
            best_index = None
            best_score = -10000
            best_name = ""
            safe_target_norms = [normalized_match_name(target) for target in safe_targets]
            short_exact_targets = {
                target_norm for target_norm in safe_target_norms
                if target_norm and len(target_norm.split()) <= 1 and len(target_norm) <= 8
            }
            for candidate in row_candidates:
                row_text = candidate.get("text") or ""
                link_text = candidate.get("linkText") or ""
                if short_exact_targets and normalized_match_name(link_text) not in short_exact_targets:
                    continue
                score = target_name_score(link_text, safe_targets)
                try:
                    checker_score = checker.candidate_selection_score_for_targets(row_text, safe_targets, row_text)
                    if checker_score[0] >= 0:
                        score = max(score, 520 + checker_score[0] * 20 + checker_score[1])
                except Exception:
                    pass
                if score > best_score:
                    best_score = score
                    best_index = candidate.get("index")
                    best_name = candidate.get("linkText") or ""
            if best_index is None or best_score < 450:
                continue
            try:
                link = page.get_by_role("link", name=re.compile(re.escape(best_name), re.I)).first
            except Exception:
                link = page.locator("a[href*='CHR_GeneralInfo']").first
            try:
                link.click(timeout=5000)
                checker.safe_wait_for_network_idle(page, timeout=10000)
                time.sleep(1)
            except Exception:
                continue
            detail_text = readable_page_text(page)
            year_match = re.search(r"(?:Fiscal\s+Year\s+Ending|For\s+Fiscal\s+Year\s+Ending)\s*:?\s*(?:\d{1,2}[/-]\d{1,2}[/-])?(20\d{2})", detail_text, re.I)
            year = int(year_match.group(1)) if year_match else None
            status_line = text_between_labels(detail_text, "Status", ["Extension", "Financial Information", "For Fiscal Year Ending"])
            if re.search(r"\binactive|closed|withdrawn|cancel", status_line or "", re.I):
                result.status = "Closed / Withdrawn / Canceled"
            else:
                result.status = mn_status_from_fiscal_year(year)
            result.raw_status_text = " | ".join(item for item in [
                f"Status: {status_line}" if status_line else "",
                f"Fiscal Year Ending {year}" if year else "",
                "Matched by organization name after EIN search returned no exact result",
            ])
            result.source_note = "MN tried EIN search first, then used the public organization-name search when the EIN field returned no exact result."
            result.matched_registry_name = clean_registry_name(best_name or checker.extract_labeled_value_from_text(detail_text, ["Organization Name", "Charity Name", "Name"]))
            federal_match = re.search(r"FEDERAL\s+ID#?\s*([0-9-]+)", detail_text, re.I)
            result.matched_registry_identifier = federal_match.group(1) if federal_match else ""
            result.success = True
            return result
        return result
    except Exception as exc:
        result.error = f"MN error: {exc}"
        return result


def ohio_due_date(most_recent_filing_year: int, fiscal_year_end_month: int) -> date:
    next_fiscal_year = most_recent_filing_year + 1
    _, fiscal_end_day = calendar.monthrange(next_fiscal_year, fiscal_year_end_month)
    fiscal_end_date = date(next_fiscal_year, fiscal_year_end_month, fiscal_end_day)
    due_month_index = fiscal_end_date.month - 1 + 5
    due_year = fiscal_end_date.year + due_month_index // 12
    due_month = due_month_index % 12 + 1
    return date(due_year, due_month, 15)


def ohio_detail_url(page_name: str, detail_id: str) -> str:
    page_name = str(page_name or "").strip()
    detail_id = str(detail_id or "").strip()
    if page_name in {"109", "1716"}:
        return (
            "https://charitableregistration.ohioago.gov/Charities/"
            f"PartiallyExemptOrganization?Id={quote(detail_id)}&ExemptionStatus={quote(page_name)}"
        )
    page_name = page_name or "OrganizationDetails"
    return f"https://charitableregistration.ohioago.gov/Charities/{quote(page_name)}?Id={quote(detail_id)}"


def search_oh(page, org):
    url = "https://charitableregistration.ohioago.gov/Charities/ResearchCharities"
    result = checker.StateResult(org.organization_name or format_ein(org.ein), org.ein, "OH", checker.STATUS_UNKNOWN, url)
    ein_digits = re.sub(r"\D", "", org.ein or "")
    formatted_ein = format_ein(org.ein)
    month_names = {name.lower(): index for index, name in enumerate(calendar.month_name) if name}
    month_names.update({name.lower(): index for index, name in enumerate(calendar.month_abbr) if name})
    search_summary_text = ""
    if len(ein_digits) != 9:
        result.error = "OH: EIN search requires a 9-digit EIN."
        return result
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        checker.safe_wait_for_network_idle(page, timeout=8000)
        page.locator("#EIN").fill("")
        page.locator("#EIN").fill(formatted_ein)
        try:
            page.locator("#ddlEINFilterCriteriaList").select_option(label=re.compile("Equals", re.I))
        except Exception:
            try:
                page.locator("#ddlEINFilterCriteriaList").select_option(value="Equals")
            except Exception:
                pass
        page.locator("#OnSubmit").click(timeout=10000)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        checker.safe_wait_for_network_idle(page, timeout=12000)
        time.sleep(2)
        text = readable_page_text(page)
        search_summary_text = text
        if no_registry_results_seen(text):
            result.status = checker.STATUS_NOT_REGISTERED
            result.raw_status_text = "No matching EIN result"
            result.source_note = "Ohio EIN search returned no matching record."
            result.success = True
            return result
        detail_ref = page.evaluate(
            """
            (einDigits) => {
                const rows = Array.from(document.querySelectorAll('tr'));
                for (const row of rows) {
                    const rowText = (row.innerText || row.textContent || '').replace(/\\D/g, '');
                    if (!rowText.includes(einDigits)) continue;
                    const links = Array.from(row.querySelectorAll('a'));
                    for (const link of links) {
                        const onclick = link.getAttribute('onclick') || '';
                        const match = onclick.match(/OpenDetailsLink\\('([^']+)','(\\d+)'\\)/i);
                        if (match) return { pageName: match[1], id: match[2] };
                    }
                }
                const body = document.body ? document.body.innerHTML : '';
                const match = body.match(/OpenDetailsLink\\('([^']+)','(\\d+)'\\)/i);
                return match ? { pageName: match[1], id: match[2] } : null;
            }
            """,
            ein_digits,
        )
        if not detail_ref:
            safe_targets = organization_match_target_variants(org.organization_name, org.ein)
            for variant in organization_name_variants(
                org.organization_name,
                org.ein,
                include_ein_aliases=True,
                include_name_segments=True,
                include_compact_legal_suffixes=True,
                include_leading_article_variants=True,
                include_broad_query_prefixes=False,
            )[:10]:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                checker.safe_wait_for_network_idle(page, timeout=8000)
                page.locator("#OrgNameOrDBAName").fill("")
                page.locator("#OrgNameOrDBAName").fill(variant)
                try:
                    page.locator("#ddlOrgNameFilterCriteriaList").select_option(label="Contains")
                except Exception:
                    pass
                page.locator("#OnSubmit").click(timeout=10000)
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=15000)
                except Exception:
                    pass
                checker.safe_wait_for_network_idle(page, timeout=12000)
                time.sleep(2)
                search_summary_text = readable_page_text(page)
                detail_ref = page.evaluate(
                    """
                    ({ einDigits, targets }) => {
                        const normalize = (value) => (value || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').replace(/\\b(the|a|an|inc|incorporated|corp|corporation|llc|ltd)\\b/g, ' ').replace(/\\s+/g, ' ').trim();
                        const targetNorms = (targets || []).map(normalize).filter(Boolean);
                        const rows = Array.from(document.querySelectorAll('tr'));
                        let best = null;
                        let bestScore = -1;
                        for (const row of rows) {
                            const text = (row.innerText || row.textContent || '').replace(/\\s+/g, ' ').trim();
                            if (!text) continue;
                            const digits = text.replace(/\\D/g, '');
                            let score = digits.includes(einDigits) ? 1000 : -1;
                            const cells = Array.from(row.querySelectorAll('td')).map((cell) => (cell.innerText || cell.textContent || '').replace(/\\s+/g, ' ').trim());
                            const rowName = cells[0] || text;
                            const rowNorm = normalize(rowName);
                            for (const target of targetNorms) {
                                if (rowNorm && (rowNorm === target || rowNorm.includes(target) || target.includes(rowNorm))) {
                                    score = Math.max(score, 500 + Math.min(rowNorm.length, target.length));
                                }
                            }
                            if (score < bestScore) continue;
                            const link = Array.from(row.querySelectorAll('a')).find((a) => /View Details/i.test((a.innerText || a.textContent || '')));
                            const onclick = link ? (link.getAttribute('onclick') || '') : '';
                            const match = onclick.match(/OpenDetailsLink\\('([^']+)','(\\d+)'\\)/i);
                            if (match) {
                                best = { pageName: match[1], id: match[2] };
                                bestScore = score;
                            }
                        }
                        return best || null;
                    }
                    """,
                    {"einDigits": ein_digits, "targets": safe_targets},
                )
                if detail_ref:
                    break
            if not detail_ref:
                result.status = checker.STATUS_NOT_REGISTERED
                result.raw_status_text = "No matching EIN or organization-name result"
                result.source_note = "Ohio EIN search did not return a detail link, and the organization-name fallback did not find a matching Ohio record."
                result.success = True
                return result
        detail_id = str((detail_ref or {}).get("id") or "")
        detail_page_name = str((detail_ref or {}).get("pageName") or "OrganizationDetails")
        detail_url = ohio_detail_url(detail_page_name, detail_id)
        page.goto(detail_url, wait_until="domcontentloaded", timeout=45000)
        checker.safe_wait_for_network_idle(page, timeout=10000)
        time.sleep(1)
        detail_text = readable_page_text(page)
        if ein_digits not in re.sub(r"\D", "", detail_text):
            result.status = checker.STATUS_NOT_REGISTERED
            result.raw_status_text = "No matching EIN result"
            result.source_note = "Ohio detail page did not confirm the requested EIN."
            result.success = True
            return result
        site_name = text_between_labels(detail_text, "Organization Name", ["Organization Phone", "EIN", "Registration Status"])
        registration_status = text_between_labels(detail_text, "Registration Status", ["Annual Reports Filed", "Most Recent Report Filing Year", "Fiscal Year End"])
        exemption_status = text_between_labels(detail_text, "Exemption Status", ["Annual Reports Filed", "Most Recent Report Filing Year", "Fiscal Year End", "Street Address", "Organization Phone"])
        filing_year_raw = text_between_labels(detail_text, "Most Recent Report Filing Year", ["The financial information below", "Fiscal Year End", "Total Revenue"])
        fiscal_year_end_raw = text_between_labels(detail_text, "Fiscal Year End", ["Street Address", "Organization Phone", "Most Recent Report Filing Year"])
        filing_year_match = re.search(r"\b(20\d{2})\b", filing_year_raw or "")
        fiscal_month = month_names.get((fiscal_year_end_raw or "").split()[0].lower()) if fiscal_year_end_raw else None
        result.source_url = detail_url
        result.matched_registry_name = clean_registry_name(site_name)
        result.matched_registry_identifier = detail_id
        result.raw_status_text = (
            f"Registration Status: {registration_status or 'N/A'} | "
            f"Exemption Status: {exemption_status or 'N/A'} | "
            f"Most Recent Report Filing Year: {filing_year_raw or 'N/A'} | "
            f"Fiscal Year End: {fiscal_year_end_raw or 'N/A'}"
        )
        if re.search(r"\bexempt\b", " ".join([exemption_status or "", registration_status or ""]), re.I):
            result.status = "Exempt"
        elif re.search(r"\bpending\b", registration_status or "", re.I):
            result.status = "Pending"
        elif re.search(r"\b(revoked|suspended)\b", registration_status or "", re.I):
            result.status = registration_status.title()
        elif filing_year_match and fiscal_month:
            due = ohio_due_date(int(filing_year_match.group(1)), fiscal_month)
            result.status = classify_expiration_date(due)
            result.raw_status_text += f" | Next Due: {format_date(due)}"
        elif re.search(r"\bregistered\b|\bin\s+compliance\b|\byes\b", registration_status or "", re.I):
            result.status = checker.STATUS_CURRENT
        else:
            result.status = checker.STATUS_UNKNOWN
        result.source_note = "OH uses EIN search first and computes the next base annual-report due date from the public detail page."
        result.success = True
        return result
    except Exception as exc:
        result.error = f"OH error: {exc}"
        return result


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


def fill_ak_search_form_name_only(page, org, year: int, variant: str) -> None:
    submission = page.locator("#Dq-8")
    if submission.count() == 0:
        submission = page.get_by_label(re.compile(r"Submission", re.I)).first
    try:
        submission.select_option(label=re.compile("Charitable Organization", re.I))
    except Exception:
        try:
            submission.select_option(index=0)
        except Exception:
            pass
    year_select = page.locator("#Dq-9")
    if year_select.count() == 0:
        year_select = page.get_by_label(re.compile(r"Year", re.I)).first
    try:
        year_select.select_option(label=str(year))
    except Exception:
        try:
            year_select.select_option(value=str(year))
        except Exception:
            pass
    name_input = page.locator("#Dq-a")
    if name_input.count() == 0:
        name_input = page.get_by_label(re.compile(r"^Name$", re.I)).first
    name_input.wait_for(state="visible", timeout=8000)
    name_input.fill("")
    name_input.fill(variant)
    fein_input = page.locator("#Dq-b")
    if fein_input.count() == 0:
        fein_input = page.get_by_label(re.compile(r"FEIN", re.I)).first
    try:
        fein_input.fill("")
    except Exception:
        pass
    search_button = page.locator("#Dq-c")
    if search_button.count() == 0:
        search_button = page.get_by_role("button", name=re.compile(r"^Search$", re.I)).first
    search_button.click(timeout=10000, force=True)
    time.sleep(2)


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
    ak_context = browser.new_context(viewport={"width": 1365, "height": 900}, accept_downloads=False)
    configure_browser_context(ak_context)
    ak_page = ak_context.new_page()
    try:
        if not checker.open_ak_public_search(ak_page):
            result.error = "Could not open Alaska Public Search form"
            return result, ""
        for year in years_to_try:
            page_body = ""
            try:
                checker.fill_ak_search_form(ak_page, org, year)
                print_link = find_ak_print_link_relaxed(ak_page, org)
                page_body = registry_page_body(ak_page)
                if not print_link:
                    continue
                row_text = re.sub(r"\s+", " ", (print_link.get("rowText") or "")).strip() if isinstance(print_link, dict) else ""
                if row_text:
                    row_name = useful_registry_name(re.split(r"\b\d{2}[-\s]?\d{7}\b|\bCharitable\b|\bPrint\b", row_text, maxsplit=1, flags=re.I)[0])
                    if row_name and registry_name_is_safe_for_org(row_name, org.organization_name, org.ein):
                        result.matched_registry_name = row_name
                result.status, result.raw_status_text, result.source_note = checker.classify_ak_registration_year(year, None)
                result.success = True
                return result, page_body
            except Exception as e:
                result.error = f"AK error: {e}"
                try:
                    checker.open_ak_public_search(ak_page)
                except Exception:
                    pass
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
    for attempt in range(10):
        time.sleep(0.75)
        try:
            refreshed = registry_page_body(page)
        except Exception:
            continue
        if re.search(r"Form[\s-]*PC", refreshed, re.I):
            body = refreshed
            break
        if attempt >= 5 and re.search(
            r"Annual\s+Filings(?:\s+and\s+Documents)?[\s\S]{0,1200}(?:No documents found|No rows available)",
            refreshed,
            re.I,
        ):
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


def validate_ma_positive_record(org, result, body: str):
    if public_status(result) in {"Not Registered", "Site Not Reachable"}:
        return result
    readable = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body or ""))).strip()
    ein_digits = re.sub(r"\D", "", getattr(org, "ein", "") or "")
    registry_name = useful_registry_name(
        checker.extract_labeled_value_from_text(readable, ["Organization Name", "Charity Name", "Legal Name", "Name"])
    )
    if registry_name and registry_name_is_safe_for_org(registry_name, org.organization_name, org.ein):
        result.matched_registry_name = registry_name
        return result
    has_visible_filing = bool(re.search(r"\bForm[\s-]*PC\b|\b20\d{2}\b", " ".join([result.raw_status_text or "", readable]), re.I))
    ein_confirmed = bool(ein_digits and ein_digits in re.sub(r"\D", "", readable))
    if not has_visible_filing and not ein_confirmed and not registry_name:
        replacement = checker.StateResult(org.organization_name, org.ein, "MA", checker.STATUS_NOT_REGISTERED, getattr(result, "source_url", "") or "")
        replacement.raw_status_text = "No confirmed Massachusetts charity record"
        replacement.source_note = "Massachusetts returned a possible record, but CharityClarity could not confirm the requested EIN, a safe registry name, or a visible Form PC filing year."
        replacement.success = True
        return replacement
    if registry_name and not registry_name_is_safe_for_org(registry_name, org.organization_name, org.ein):
        replacement = checker.StateResult(org.organization_name, org.ein, "MA", checker.STATUS_NOT_REGISTERED, getattr(result, "source_url", "") or "")
        replacement.raw_status_text = "Massachusetts registry name did not safely match"
        replacement.source_note = "Massachusetts returned a record, but its registry name did not safely match the requested organization."
        replacement.success = True
        return replacement
    return result


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
                for ein_value in ([checker.format_ein_with_dash(org.ein), ein_digits, ""] if ein_digits else [""]):
                    if (variant, ein_value) not in attempts:
                        attempts.append((variant, ein_value))
        clicked_result_name = ""
        clicked_result_identifier = ""
        for variant, ein_value in attempts[:4]:
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
                            clicked_result_identifier = ein_digits if ein_digits and ein_digits in row_digits else ""
                            candidate_name = re.sub(r"^\s*\d{9}\s+", "", row_text).strip()
                            candidate_name = re.split(r"\s+\d{2,6}\s+", candidate_name, maxsplit=1)[0].strip()
                            clicked_result_name = clean_registry_name(candidate_name)
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
        registration_type = checker.extract_labeled_value(page, ["Registration Type"]) or checker.extract_labeled_value_from_text(detail_text, ["Registration Type"])
        result.matched_registry_name = useful_registry_name(
            checker.extract_labeled_value(page, ["Primary Name", "Organization Name", "Charity Name", "Legal Name"])
            or checker.extract_labeled_value_from_text(detail_text, ["Primary Name", "Organization Name", "Charity Name", "Legal Name"])
            or clicked_result_name
        )
        result.matched_registry_identifier = detail_ein or clicked_result_identifier
        if not result_registry_name_is_safe(result, org.organization_name, org.ein):
            result.raw_status_text = "No matching organization record"
            result.status = checker.STATUS_NOT_REGISTERED
            result.source_note = "Hawaii search found a row, but the registry name did not safely match the requested organization."
            result.success = True
            return result
        result.raw_status_text = " | ".join(part for part in [
            f"Registration Status: {status_text}" if status_text else "",
            f"Registration Type: {registration_type}" if registration_type else "",
        ]) or status_text
        result.status = status_text if status_text else checker.STATUS_UNKNOWN
        result.source_note = "Registration status and filings from Hawaii detail page."
        result.success = True
        return result
    except Exception as e:
        result.error = f"HI error: {e}"
        return result


def html_to_text(source: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", source or ""))).strip()


def html_input_value(source: str, name: str) -> str:
    match = re.search(
        r"<input[^>]+name=[\"']" + re.escape(name) + r"[\"'][^>]*value=[\"']([^\"']*)[\"']",
        source or "",
        re.I,
    )
    return html.unescape(match.group(1)) if match else ""


def html_table_cells(row_html: str) -> list[str]:
    values = []
    for cell_match in re.finditer(r"<t[dh][^>]*>([\s\S]*?)</t[dh]>", row_html or "", re.I):
        values.append(html_to_text(cell_match.group(1)))
    return values


def wi_http_detail_status(detail_href: str) -> str:
    if not detail_href:
        return ""
    try:
        detail_url = urljoin(WI_SEARCH_URL, html.unescape(detail_href))
        request = urllib.request.Request(detail_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=WI_HTTP_TIMEOUT_SECONDS) as response:
            detail_html = response.read().decode("utf-8", errors="replace")
        detail_text = html_to_text(detail_html)
        status_match = re.search(r"\bStatus\s+(License\s+is\s+(?:not\s+)?current\s*\([^)]+\))", detail_text, re.I)
        return re.sub(r"\s+", " ", status_match.group(1)).strip() if status_match else ""
    except Exception:
        return ""


def wi_reader_url(source_url: str) -> str:
    return f"{WI_READER_BASE_URL}{source_url}"


def wi_reader_text(source_url: str) -> str:
    try:
        request = urllib.request.Request(wi_reader_url(source_url), headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=WI_READER_TIMEOUT_SECONDS) as response:
            return response.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def wi_reader_detail_status(detail_href: str) -> str:
    if not detail_href:
        return ""
    detail_url = urljoin(WI_SEARCH_URL, html.unescape(detail_href))
    detail_text = wi_reader_text(detail_url)
    status_match = re.search(r"\bStatus\s+(License\s+is\s+(?:not\s+)?current\s*\([^)]+\))", detail_text, re.I)
    return re.sub(r"\s+", " ", status_match.group(1)).strip() if status_match else ""


def wi_markdown_link_parts(value: str) -> tuple[str, str]:
    match = re.search(r"\[([^\]]+)\]\(([^)]+)\)", value or "")
    if match:
        return html.unescape(match.group(1)).strip(), html.unescape(match.group(2)).strip()
    return html.unescape(value or "").strip(), ""


def wi_status_from_detail_status(detail_status: str) -> str:
    text = detail_status or ""
    if re.search(r"\bvoluntar(?:y|ily)\s+surrender(?:ed)?\b", text, re.I):
        return "Closed / Withdrawn / Canceled"
    if re.search(r"\brevoked\b", text, re.I):
        return "Revoked"
    if re.search(r"\bsuspended\b", text, re.I):
        return "Suspended"
    if re.search(r"\bLicense\s+is\s+not\s+current\b", text, re.I):
        return "Delinquent"
    if re.search(r"\bLicense\s+is\s+current\s*\(\s*Active\s*\)", text, re.I):
        return "Current"
    return ""


def wi_expiration_suffix(expiration_date: date | None) -> str:
    return f"; License current through {format_date(expiration_date)}" if expiration_date else ""


def wi_request_headers(referer: str = WI_SEARCH_URL) -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": referer,
    }


def wi_search_names_for_org(org) -> list[str]:
    names: list[str] = []

    def add_many(values) -> None:
        for value in values:
            value = re.sub(r"\s+", " ", (value or "").strip())
            if value and value not in names:
                names.append(value)

    original_name = getattr(org, "organization_name", "")
    add_many([original_name])
    add_many(known_names_for_ein(getattr(org, "ein", "")))
    seed_names = list(names)
    seed_has_hyphen = any(re.search(r"[-\u2010-\u2015]", seed or "") for seed in seed_names)

    def generated_hyphen_variant_is_safe(value: str) -> bool:
        if seed_has_hyphen:
            return True
        normalized_value = re.sub(r"\s+", " ", value or "").strip()
        if not re.search(r"[-\u2010-\u2015]", normalized_value):
            return True
        seed_tokens = [
            re.findall(r"[A-Za-z0-9]+", seed or "")
            for seed in seed_names
            if seed
        ]
        value_tokens = re.findall(r"[A-Za-z0-9]+", normalized_value)
        if not value_tokens:
            return False
        generic = {
            "the", "a", "an", "of", "for", "and", "to", "in", "on", "at",
            "by", "inc", "incorporated", "corp", "corporation", "llc",
            "ltd", "limited", "foundation", "fund", "association", "society",
            "center", "centre", "institute", "organization", "charity",
        }
        hyphen_pairs = [
            tuple(part for part in re.split(r"[-\u2010-\u2015]+", token) if part)
            for token in re.split(r"\s+", normalized_value)
            if re.search(r"[-\u2010-\u2015]", token)
        ]
        for pair in hyphen_pairs:
            if len(pair) != 2:
                continue
            left, right = pair
            if left.lower() in generic or right.lower() in generic:
                continue
            if left.isupper() or right.isupper():
                continue
            for tokens in seed_tokens:
                for index in range(len(tokens) - 1):
                    if tokens[index].lower() == left.lower() and tokens[index + 1].lower() == right.lower():
                        return True
        return False

    for seed in list(names):
        add_many(organization_name_variants(
            seed,
            "",
            include_ein_aliases=False,
            include_name_segments=True,
            include_compact_legal_suffixes=True,
            include_leading_article_variants=True,
            include_broad_query_prefixes=False,
        ))
    expanded_names: list[str] = []
    for value in names:
        cleaned = re.sub(r"\s+", " ", (value or "").strip())
        if cleaned and cleaned not in expanded_names:
            expanded_names.append(cleaned)
        structural = cleaned
        structural = re.sub(r"^(?:the|a|an)\s+", "", structural, flags=re.I).strip()
        structural = re.sub(r",\s*(?:the|a|an)\s*$", "", structural, flags=re.I).strip()
        structural = re.sub(r",\s*(inc\.?|incorporated|corp\.?|corporation|llc|ltd\.?|limited)\s*$", "", structural, flags=re.I).strip()
        structural = re.sub(r"\b(inc\.?|incorporated|corp\.?|corporation|llc|ltd\.?|limited)\s*$", "", structural, flags=re.I).strip()
        no_punct = re.sub(r"[^\w\s]", " ", structural)
        no_punct = re.sub(r"\s+", " ", no_punct).strip()
        substantive = [
            word for word in re.findall(r"[A-Za-z0-9]+", no_punct)
            if word.lower() not in {"the", "a", "an", "inc", "incorporated", "corp", "corporation", "llc", "ltd", "limited"}
        ]
        if len(substantive) >= 2 and no_punct and no_punct.lower() != cleaned.lower() and no_punct not in expanded_names:
            expanded_names.append(no_punct)

    def priority(value: str) -> tuple[int, int, str]:
        cleaned = re.sub(r"\s+", " ", (value or "").strip())
        if not cleaned:
            return (99, 99, "")
        compact = re.sub(r"[^A-Za-z0-9]+", "", cleaned)
        if 2 <= len(compact) <= 8 and compact.upper() == compact:
            return (0, len(cleaned.split()), cleaned.lower())
        if re.fullmatch(r"(?i)(inc\.?|incorporated|corp\.?|corporation|llc|ltd\.?|limited|the|a|an)", cleaned):
            return (90, 99, cleaned.lower())
        has_punctuation = bool(re.search(r"[-,/]", cleaned))
        has_legal_suffix = bool(re.search(r"\b(inc\.?|incorporated|corp\.?|corporation|llc|ltd\.?|limited)\b", cleaned, re.I))
        starts_article = bool(re.match(r"^(?:the|a|an)\s+", cleaned, re.I))
        return (
            1 if not (has_punctuation or has_legal_suffix or starts_article) else 2,
            len(cleaned.split()),
            cleaned.lower(),
        )

    filtered_names = []
    for value in expanded_names:
        if re.search(r"[-\u2010-\u2015]", value or "") and not generated_hyphen_variant_is_safe(value):
            continue
        substantive = [
            word for word in re.findall(r"[A-Za-z0-9]+", value or "")
            if word.lower() not in {"the", "a", "an", "inc", "incorporated", "corp", "corporation", "llc", "ltd", "limited"}
        ]
        compact = re.sub(r"[^A-Za-z0-9]+", "", value or "")
        is_short_acronym = 2 <= len(compact) <= 8 and compact.upper() == compact
        is_compact_alnum_name = bool(re.fullmatch(r"(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9]{4,}", compact or ""))
        if (len(substantive) >= 2 or is_short_acronym or is_compact_alnum_name) and value not in filtered_names:
            filtered_names.append(value)
    filtered_names.sort(key=priority)
    return filtered_names


def wi_contains_full_target_name(registry_name: str, target_names: list[str]) -> bool:
    """Allow WI rows where the full target is embedded in a longer legal name."""
    normalize = getattr(checker, "normalize_name", lambda value: re.sub(r"\W+", " ", (value or "").lower()).strip())
    candidate = normalize(registry_name)
    if not candidate:
        return False
    for target_name in target_names or []:
        target = normalize(target_name)
        if target and len(target.split()) >= 4 and target in candidate:
            return True
    return False


def wi_candidate_from_row_html(row_html: str, target_names: list[str]) -> dict | None:
    values = html_table_cells(row_html)
    if len(values) < 6:
        return None
    license_number, profession, registry_name, location, granted_date, expiration_text = values[:6]
    if not re.search(r"Charitable\s+Organization", profession, re.I):
        return None
    score = checker.name_match_priority_for_targets(registry_name, target_names)
    if score < 4 and not wi_contains_full_target_name(registry_name, target_names):
        return None
    href_match = re.search(r"<a[^>]+href=[\"']([^\"']+)[\"']", row_html, re.I)
    href = html.unescape(href_match.group(1)) if href_match else ""
    expiration_date = parse_due_date(expiration_text)
    detail_status = wi_http_detail_status(href)
    if not expiration_date and not wi_status_from_detail_status(detail_status):
        return None
    return {
        "score": score,
        "expiration_date": expiration_date,
        "license_number": license_number,
        "registry_name": registry_name,
        "location": location,
        "granted_date": granted_date,
        "detail_href": href,
        "detail_status": detail_status,
    }


def wi_candidate_from_markdown_row(row_text: str, target_names: list[str]) -> dict | None:
    cells = [cell.strip() for cell in (row_text or "").strip().strip("|").split("|")]
    if len(cells) < 6:
        return None
    license_number, profession, registry_cell, location, granted_date, expiration_text = cells[:6]
    if not re.search(r"Charitable\s+Organization", profession, re.I):
        return None
    if re.match(r"^-+$", license_number) or re.match(r"license#?$", license_number, re.I):
        return None
    registry_name, detail_href = wi_markdown_link_parts(registry_cell)
    score = checker.name_match_priority_for_targets(registry_name, target_names)
    if score < 4 and not wi_contains_full_target_name(registry_name, target_names):
        return None
    expiration_date = parse_due_date(expiration_text)
    detail_status = wi_reader_detail_status(detail_href)
    if not expiration_date and not wi_status_from_detail_status(detail_status):
        return None
    return {
        "score": score,
        "expiration_date": expiration_date,
        "license_number": license_number,
        "registry_name": registry_name,
        "location": location,
        "granted_date": granted_date,
        "detail_href": detail_href,
        "detail_status": detail_status,
    }


def wi_better_candidate(candidate: dict, best_match: dict | None) -> bool:
    if not best_match:
        return True
    if candidate["score"] > best_match["score"]:
        return True
    return (
        candidate["score"] == best_match["score"]
        and (candidate["expiration_date"] or date.min) > (best_match["expiration_date"] or date.min)
    )


def wi_best_match_from_html(result_html: str, target_names: list[str], best_match: dict | None = None) -> dict | None:
    table_match = re.search(
        r"<table[^>]+id=[\"']ctl00_cphMainContent_OrgCredentialSearch_gvCredentialSearchResults[\"'][^>]*>([\s\S]*?)</table>",
        result_html,
        re.I,
    )
    if not table_match:
        return best_match

    for row_match in re.finditer(r"<tr[^>]*>([\s\S]*?)</tr>", table_match.group(1), re.I):
        row_html = row_match.group(1)
        if re.search(r"<th\b", row_html, re.I):
            continue
        candidate = wi_candidate_from_row_html(row_html, target_names)
        if candidate and wi_better_candidate(candidate, best_match):
            best_match = candidate
    return best_match


def wi_best_match_from_markdown(result_text: str, target_names: list[str], best_match: dict | None = None) -> dict | None:
    for line in (result_text or "").splitlines():
        if not line.strip().startswith("|"):
            continue
        candidate = wi_candidate_from_markdown_row(line, target_names)
        if candidate and wi_better_candidate(candidate, best_match):
            best_match = candidate
    return best_match


def wi_reader_search_best_match(search_names: list[str], target_names: list[str], deadline: float | None = None) -> tuple[dict | None, bool]:
    best_match = None
    reader_reached = False
    for search_name in search_names:
        if deadline and time.perf_counter() >= deadline:
            break
        source_url = f"{WI_RESULTS_URL}?{urlencode({'CredentialType': '800', 'FirmName': search_name, 'LicenseNumber': ''})}"
        result_text = wi_reader_text(source_url)
        if re.search(r"Organization Search Results|Search Parameters|Total Search Results", result_text or "", re.I):
            reader_reached = True
        best_match = wi_best_match_from_markdown(result_text, target_names, best_match)
        if best_match and best_match["score"] >= 5:
            break
    return best_match, reader_reached


def wi_http_search_best_match(search_names: list[str], target_names: list[str], deadline: float | None = None) -> tuple[dict | None, bool]:
    best_match = None
    http_reached = False
    try:
        base_request = urllib.request.Request(WI_SEARCH_URL, headers=wi_request_headers())
        with urllib.request.urlopen(base_request, timeout=WI_HTTP_TIMEOUT_SECONDS) as response:
            base_html = response.read().decode("utf-8", errors="replace")
    except Exception:
        return None, http_reached

    for search_name in search_names:
        if deadline and time.perf_counter() >= deadline:
            break
        try:
            direct_url = f"{WI_RESULTS_URL}?{urlencode({'CredentialType': '800', 'LicenseNumber': '', 'FirmName': search_name})}"
            request = urllib.request.Request(direct_url, headers=wi_request_headers())
            with urllib.request.urlopen(request, timeout=WI_HTTP_TIMEOUT_SECONDS) as response:
                result_html = response.read().decode("utf-8", errors="replace")
            http_reached = True
            best_match = wi_best_match_from_html(result_html, target_names, best_match)
            if best_match and best_match["score"] >= 5:
                break
        except Exception:
            pass

        form_data = {
            "__VIEWSTATE": html_input_value(base_html, "__VIEWSTATE"),
            "__VIEWSTATEGENERATOR": html_input_value(base_html, "__VIEWSTATEGENERATOR"),
            "ctl00$cphMainContent$ddlProfesionalList": "800",
            "ctl00$cphMainContent$txtFirmName": search_name,
            "ctl00$cphMainContent$btnSearch": "Search",
        }
        try:
            request = urllib.request.Request(
                WI_SEARCH_URL,
                data=urlencode(form_data).encode("utf-8"),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    **wi_request_headers(),
                    "Origin": "https://apps.dfi.wi.gov",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=WI_HTTP_TIMEOUT_SECONDS) as response:
                result_html = response.read().decode("utf-8", errors="replace")
            http_reached = True
        except Exception:
            continue

        best_match = wi_best_match_from_html(result_html, target_names, best_match)
        if best_match and best_match["score"] >= 5:
            break
    return best_match, http_reached


def search_wi(page, org):
    result = checker.StateResult(org.organization_name, org.ein, "WI", checker.STATUS_UNKNOWN, WI_SEARCH_URL)
    searched_names = wi_search_names_for_org(org) or [org.organization_name]
    started = time.perf_counter()
    deadline = started + WI_LOOKUP_MAX_SECONDS
    direct_names = searched_names[:WI_DIRECT_VARIANT_LIMIT]

    best_match = None
    last_body = ""
    wi_reader_reached = False
    wi_http_reached = False
    target_names = organization_match_target_variants(org.organization_name, org.ein)
    try:
        best_match, wi_reader_reached = wi_reader_search_best_match(direct_names, target_names, deadline)
        if not best_match:
            best_match, wi_http_reached = wi_http_search_best_match(direct_names, target_names, deadline)

        if not best_match and time.perf_counter() < deadline and WI_BROWSER_VARIANT_LIMIT > 0:
            for search_name in searched_names[:WI_BROWSER_VARIANT_LIMIT]:
                if time.perf_counter() >= deadline:
                    break
                page.goto(WI_SEARCH_URL, wait_until="domcontentloaded", timeout=min(30000, int(max(5000, (deadline - time.perf_counter()) * 1000))))
                try:
                    checker.safe_wait_for_network_idle(page, timeout=3000)
                except Exception:
                    pass
                try:
                    page.locator("#ctl00_cphMainContent_ddlProfesionalList").select_option(value="800")
                except Exception:
                    page.locator("select").first.select_option(label="Charitable Organization (800)")

                input_box = checker.find_visible_input(page, [
                    "#ctl00_cphMainContent_txtFirmName",
                    'input[name*="FirmName" i]',
                    'input[id*="FirmName" i]',
                    'input[type="text"]',
                ])
                if not input_box:
                    result.error = "WI: Could not find Firm Name input"
                    return result
                input_box.fill("")
                input_box.fill(search_name)

                try:
                    page.locator("#ctl00_cphMainContent_btnSearch").click(timeout=5000)
                except Exception:
                    page.get_by_role("button", name=re.compile("search", re.I)).click(timeout=5000)
                page.wait_for_load_state("domcontentloaded", timeout=min(30000, int(max(5000, (deadline - time.perf_counter()) * 1000))))
                try:
                    checker.safe_wait_for_network_idle(page, timeout=3000)
                except Exception:
                    pass
                last_body = registry_page_body(page)

                rows = page.locator("#ctl00_cphMainContent_OrgCredentialSearch_gvCredentialSearchResults tr")
                for i in range(1, min(rows.count(), 100)):
                    cells = rows.nth(i).locator("th,td")
                    if cells.count() < 6:
                        continue
                    values = [
                        re.sub(r"\s+", " ", cells.nth(index).inner_text(timeout=1500)).strip()
                        for index in range(6)
                    ]
                    license_number, profession, registry_name, location, granted_date, expiration_text = values
                    if not re.search(r"Charitable\s+Organization", profession, re.I):
                        continue
                    score = checker.name_match_priority_for_targets(registry_name, target_names)
                    if score < 4 and not wi_contains_full_target_name(registry_name, target_names):
                        continue
                    href = ""
                    try:
                        href = rows.nth(i).locator("a").first.get_attribute("href") or ""
                    except Exception:
                        href = ""
                    expiration_date = parse_due_date(expiration_text)
                    detail_status = wi_http_detail_status(href)
                    if not expiration_date and not wi_status_from_detail_status(detail_status):
                        continue
                    candidate = {
                        "score": score,
                        "expiration_date": expiration_date,
                        "license_number": license_number,
                        "registry_name": registry_name,
                        "location": location,
                        "granted_date": granted_date,
                        "detail_href": href,
                        "detail_status": detail_status,
                    }
                    if (
                        not best_match
                        or candidate["score"] > best_match["score"]
                        or (
                            candidate["score"] == best_match["score"]
                            and (candidate["expiration_date"] or date.min) > (best_match["expiration_date"] or date.min)
                        )
                    ):
                        best_match = candidate
                if best_match and best_match["score"] >= 5:
                    break

        if not best_match and time.perf_counter() < deadline and not (wi_reader_reached or wi_http_reached):
            best_match, reached = wi_reader_search_best_match(direct_names, target_names, deadline)
            if not best_match:
                best_match, reached_http = wi_http_search_best_match(direct_names, target_names, deadline)
                wi_http_reached = wi_http_reached or reached_http
            wi_reader_reached = wi_reader_reached or reached

        if not best_match:
            if wi_reader_reached or wi_http_reached:
                result.raw_status_text = "No matching Wisconsin charitable organization credential"
                result.status = checker.STATUS_NOT_REGISTERED
                result.source_note = "Wisconsin DFI returned no matching Charitable Organization credential for the organization name searched."
                result.success = True
                return result
            if re.search(r"\b403\b|forbidden|access\s+is\s+denied", last_body or "", re.I):
                result.raw_status_text = "Wisconsin registry returned 403 Forbidden"
                result.status = "Site Not Reachable"
                result.source_note = "Wisconsin DFI blocked or denied the registry result page during lookup."
                result.success = False
                return result
            result.raw_status_text = "No matching Wisconsin charitable organization credential"
            result.status = checker.STATUS_NOT_REGISTERED
            result.source_note = "Wisconsin DFI returned no matching Charitable Organization credential for the organization name searched."
            result.success = True
            return result

        detail_status = best_match.get("detail_status", "")
        if best_match.get("detail_href") and page is not None:
            try:
                page.goto(
                    urljoin(WI_SEARCH_URL, best_match["detail_href"]),
                    wait_until="domcontentloaded",
                    timeout=min(30000, int(max(5000, (deadline - time.perf_counter()) * 1000))),
                )
                try:
                    checker.safe_wait_for_network_idle(page, timeout=3000)
                except Exception:
                    pass
                detail_text = registry_page_body(page)
                detail_status_match = re.search(r"\bStatus\s+(License\s+is\s+(?:not\s+)?current\s*\([^)]+\))", detail_text, re.I)
                if detail_status_match:
                    detail_status = re.sub(r"\s+", " ", detail_status_match.group(1)).strip()
                    if re.search(r"\brevoked\b", detail_status, re.I):
                        result.status = "Revoked"
                        result.raw_status_text = f"{detail_status}{wi_expiration_suffix(best_match.get('expiration_date'))}"
                        result.source_note = "Wisconsin DFI credential detail page shows the license is not current (Revoked), which CharityClarity treats as an adverse status."
                        result.matched_registry_name = best_match["registry_name"]
                        result.matched_registry_identifier = best_match["license_number"]
                        result.success = True
                        return result
            except Exception:
                pass

        if re.search(r"\bvoluntar(?:y|ily)\s+surrender(?:ed)?\b", detail_status, re.I):
            result.status = "Closed / Withdrawn / Canceled"
            result.raw_status_text = f"{detail_status}{wi_expiration_suffix(best_match.get('expiration_date'))}"
            result.source_note = "Wisconsin DFI credential detail page shows a voluntary surrender, which CharityClarity treats as Closed / Withdrawn / Canceled."
            result.matched_registry_name = best_match["registry_name"]
            result.matched_registry_identifier = best_match["license_number"]
            result.success = True
            return result

        expiration_date = best_match.get("expiration_date")
        if not expiration_date:
            detail_status_result = wi_status_from_detail_status(detail_status)
            result.status = detail_status_result or checker.STATUS_UNKNOWN
            result.raw_status_text = detail_status or "Wisconsin credential matched without a parseable expiration date"
            result.source_note = "Wisconsin DFI public registry returned a matching Charitable Organization credential, but no parseable expiration date was available."
            result.matched_registry_name = best_match["registry_name"]
            result.matched_registry_identifier = best_match["license_number"]
            result.success = bool(detail_status_result)
            return result

        result.status = status_from_calendar_date(expiration_date)
        result.raw_status_text = (
            f"{detail_status}; License current through {format_date(expiration_date)}"
            if detail_status
            else f"Expiration Date {format_date(expiration_date)}"
        )
        result.source_note = (
            "Wisconsin DFI public registry shows a Charitable Organization credential "
            f"expiration date of {format_date(expiration_date)}."
        )
        result.matched_registry_name = best_match["registry_name"]
        result.matched_registry_identifier = best_match["license_number"]
        result.success = True
        return result
    except Exception as e:
        result.error = f"WI error: {e}"
        result.source_note = "Wisconsin DFI public registry lookup could not be completed."
        if last_body:
            result.raw_status_text = "Wisconsin lookup ended after reaching the public registry"
        return result


def search_wi_sidecar(org):
    result = checker.StateResult(org.organization_name, org.ein, "WI", "Site Not Reachable", WI_SEARCH_URL)
    if not (WI_SIDECAR_URL and WI_LOOKUP_SECRET):
        result.raw_status_text = "Wisconsin sidecar is not configured"
        result.source_note = "Wisconsin DFI sidecar lookup is not configured for this environment."
        result.success = False
        return result
    search_names = wi_search_names_for_org(org) or [org.organization_name]
    payload = {
        "organization_name": org.organization_name,
        "ein": org.ein,
        "search_names": search_names[:WI_DIRECT_VARIANT_LIMIT],
        "target_names": organization_match_target_variants(org.organization_name, org.ein),
        "max_seconds": WI_SIDECAR_TIMEOUT_SECONDS,
        "app_version": APP_VERSION,
    }
    data = None
    last_exception = None
    for attempt_index in range(WI_SIDECAR_ATTEMPTS):
        try:
            request = urllib.request.Request(
                WI_SIDECAR_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-CE-WI-Lookup-Secret": WI_LOOKUP_SECRET,
                    "User-Agent": f"CharityClarity/{APP_VERSION}",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=WI_SIDECAR_TIMEOUT_SECONDS + 5) as response:
                response_body = response.read().decode("utf-8", errors="replace")
            candidate_data = json.loads(response_body)
        except Exception as exc:
            last_exception = exc
            if attempt_index + 1 < WI_SIDECAR_ATTEMPTS:
                time.sleep(0.4 * (attempt_index + 1))
            continue

        data = candidate_data
        if candidate_data.get("success") or candidate_data.get("status") != "Site Not Reachable":
            break
        if attempt_index + 1 < WI_SIDECAR_ATTEMPTS:
            time.sleep(0.4 * (attempt_index + 1))

    if data is None:
        result.raw_status_text = "Wisconsin sidecar lookup failed"
        result.source_note = "Wisconsin DFI sidecar lookup could not be completed."
        result.error = str(last_exception or "WI sidecar returned no response")
        result.success = False
        fallback_result = search_wi(None, org)
        if public_status(fallback_result) != "Site Not Reachable":
            fallback_result.source_note = "Wisconsin DFI lookup used the backend reader fallback after the sidecar returned no response."
            return fallback_result
        return result

    if data.get("status") == "Site Not Reachable" and not data.get("success"):
        fallback_result = search_wi(None, org)
        if public_status(fallback_result) != "Site Not Reachable":
            fallback_result.source_note = "Wisconsin DFI lookup used the backend reader fallback after the sidecar could not reach the registry."
            return fallback_result

    if data.get("status") == "Not Registered":
        fallback_result = search_wi(None, org)
        if public_status(fallback_result) != "Site Not Reachable":
            fallback_result.source_note = "Wisconsin DFI lookup used the backend reader fallback to confirm the sidecar no-match result."
            return fallback_result

    result.status = data.get("status") or "Site Not Reachable"
    result.source_url = data.get("source_url") or WI_SEARCH_URL
    result.raw_status_text = data.get("raw_status_text") or result.status
    result.source_note = data.get("source_note") or "Wisconsin DFI lookup was performed through the CharityClarity Wisconsin sidecar."
    result.matched_registry_name = data.get("matched_registry_name") or ""
    result.matched_registry_identifier = data.get("matched_registry_identifier") or ""
    result.error = data.get("error") or ""
    result.success = bool(data.get("success", public_status(result) != "Site Not Reachable"))
    return result


def response_data_for_lookup(result, body: str, org, organization_name: str, ein: str, state: str, lookup_started: float) -> dict:
    if result is None:
        result = checker.StateResult(organization_name or f"EIN {format_ein(ein)}", format_ein(ein), state, "Site Not Reachable", "")
        result.raw_status_text = "Lookup did not produce a registry result"
        result.source_note = "Public registry lookup could not produce a result."
        result.error = "No result"
        result.success = False
    if public_status(result) != "Not Registered":
        fill_registry_match_from_text(result, body, org)
    result.source_note = source_note_for_result(result)
    data = checker.asdict(result)
    if organization_name:
        data["organization_name"] = organization_name
        result.organization_name = organization_name
    elif (data.get("matched_registry_name") or "").strip():
        data["organization_name"] = (data.get("matched_registry_name") or "").strip()
        result.organization_name = data["organization_name"]
    elif not (data.get("organization_name") or "").strip():
        data["organization_name"] = "Organization not identified"
        result.organization_name = data["organization_name"]
    data["status"] = true_status_from_body(result, body)
    data["comments"] = comments_for_result(result, body, data["status"])
    data["evidence_url"] = ""
    data["lookup_seconds"] = round(time.perf_counter() - lookup_started, 2)
    data["checked_at_epoch"] = int(time.time())
    data["app_version"] = APP_VERSION
    log_event(f"{state} lookup for {format_ein(ein)} finished in {data['lookup_seconds']}s with status {data.get('status')}")
    return data


def enrich_me_result_from_body(result, body: str) -> None:
    existing_status = " ".join([result.status or "", result.raw_status_text or ""])
    if re.search(r"\bACTIVE\b", existing_status, re.I) and not re.search(r"\b(FAILED\s+TO\s+RENEW|EXPIRED|REVOKED|SUSPENDED|INACTIVE)\b", existing_status, re.I):
        result.raw_status_text = result.raw_status_text or "Active"
        result.status = "Current" if re.search(r"\bunknown\b|^\s*active\s*$", result.status or "", re.I) else (result.status or "Current")
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
    candidates = []

    def score_nj_candidate(row_text: str, label_text: str = "", index: int = 0) -> tuple[int, int, int, int]:
        haystack = re.sub(r"\s+", " ", f"{row_text} {label_text}").strip()
        row_digits = re.sub(r"\D", "", haystack)
        row_name = normalize_name(haystack)
        if ein_digits and ein_digits not in row_digits and wanted_name not in row_name:
            return (-999, -999, -index)
        try:
            status_priority = checker.active_row_priority(haystack)
        except Exception:
            status_priority = 40
        try:
            name_priority = checker.name_match_priority(haystack, org.organization_name)
        except Exception:
            name_priority = 0
        ein_priority = 3 if ein_digits and ein_digits in row_digits else 0
        return (ein_priority, name_priority, status_priority, -index)

    for selector in ["button.ms-Link", "button[role='link']", "[data-automation-key='name'] button"]:
        try:
            buttons = page.locator(selector)
            for i in range(min(buttons.count(), 20)):
                button = buttons.nth(i)
                try:
                    row = button.locator("xpath=ancestor::*[@role='row'][1]")
                    row_text = re.sub(r"\s+", " ", row.inner_text(timeout=1500)).strip() if row.count() else ""
                    button_text = re.sub(r"\s+", " ", button.inner_text(timeout=1500)).strip()
                    score = score_nj_candidate(row_text, button_text, i)
                    if score[0] < 0:
                        continue
                    candidates.append((score, button))
                except Exception:
                    continue
        except Exception:
            continue

    for selector in ["tbody tr", "tr", "[role='row']", ".card", ".search-result", "a[href]"]:
        try:
            rows = page.locator(selector)
            for i in range(min(rows.count(), 80)):
                row = rows.nth(i)
                try:
                    if not row.is_visible(timeout=750):
                        continue
                    row_text = re.sub(r"\s+", " ", row.inner_text(timeout=1500)).strip()
                    score = score_nj_candidate(row_text, "", i)
                    if score[0] < 0:
                        continue
                    target = row
                    links = row.locator("a[href]")
                    if selector != "a[href]" and links.count():
                        target = links.first
                    candidates.append((score, target))
                except Exception:
                    continue
        except Exception:
            continue

    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        try:
            candidates[0][1].click(timeout=5000)
            clicked = True
        except Exception:
            clicked = False

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
            ("Noncompliant", r"\bnon\W*compliant\b"),
            ("Exempt", r"\bexempt\b"),
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
        if ein_digits and ein_line_has_registry_pattern(body, org.ein, r"\bnon\W*compliant\b"):
            status = "Noncompliant"
        if not status and ein_digits and ein_digits in re.sub(r"\D", "", body):
            compact_body = re.sub(r"\s+", " ", body)
            for match in re.finditer(r"\bnon\W*compliant\b", compact_body, re.I):
                start = max(0, match.start() - 260)
                end = min(len(compact_body), match.end() + 260)
                window = compact_body[start:end]
                if ein_digits in re.sub(r"\D", "", window):
                    status = "Noncompliant"
                    break
        if not status and ein_digits and ein_digits in re.sub(r"\D", "", body):
            try:
                rows = page.locator("tr")
                best_status = ""
                best_score = (-999, -999, -999)
                for i in range(min(rows.count(), 80)):
                    row_text = re.sub(r"\s+", " ", rows.nth(i).inner_text(timeout=1500)).strip()
                    if ein_digits not in re.sub(r"\D", "", row_text):
                        continue
                    row_status = ""
                    for label, pattern in status_patterns:
                        if re.search(pattern, row_text, re.I):
                            row_status = label
                            break
                    if not row_status:
                        continue
                    try:
                        name_priority = checker.name_match_priority(row_text, org.organization_name)
                    except Exception:
                        name_priority = -1
                    status_priority = checker.active_row_priority(row_text)
                    row_score = (name_priority, status_priority, -i)
                    if row_score > best_score:
                        best_score = row_score
                        best_status = row_status
                if best_status:
                    status = best_status
            except Exception:
                pass
        if not status and ein_digits and ein_digits in re.sub(r"\D", "", body):
            body_candidates = []
            compact_body = re.sub(r"\s+", " ", body)
            for label, pattern in status_patterns:
                for match in re.finditer(pattern, compact_body, re.I):
                    start = max(0, match.start() - 220)
                    end = min(len(compact_body), match.end() + 220)
                    window = compact_body[start:end]
                    if ein_digits not in re.sub(r"\D", "", window):
                        continue
                    try:
                        name_priority = checker.name_match_priority(window, org.organization_name)
                    except Exception:
                        name_priority = -1
                    status_priority = checker.active_row_priority(label)
                    body_candidates.append((status_priority, name_priority, -match.start(), label))
            if body_candidates:
                body_candidates.sort(reverse=True)
                status = body_candidates[0][3]
        if not status:
            status_match = re.search(r"Status\s+([A-Za-z][A-Za-z /-]+?)\s+Federal\s+EIN", re.sub(r"\s+", " ", body), re.I)
            if status_match:
                status = status_match.group(1).strip()
        registry_name = useful_registry_name(checker.extract_labeled_value_from_text(body, ["Organization Name", "Charity Name", "Legal Name", "Name"]))
        if not registry_name and ein_digits:
            for line in re.split(r"[\r\n]+", body or ""):
                line_text = re.sub(r"\s+", " ", line).strip()
                if ein_digits not in re.sub(r"\D", "", line_text):
                    continue
                registry_name = useful_registry_name(re.split(r"\b(?:Federal\s+EIN|EIN|Status|Registration)\b", line_text, maxsplit=1, flags=re.I)[0])
                if registry_name:
                    break
        result.matched_registry_name = registry_name
        result.raw_status_text = status or "Status not found"
        if re.search(r"\b(retired|withdrawn|terminated|cancelled|canceled|closed)\b", status, re.I):
            result.status = "Closed / Withdrawn / Canceled"
        elif re.search(r"\bnon\W*compliant\b", status, re.I):
            result.status = "Delinquent"
        else:
            result.status = status or checker.STATUS_UNKNOWN
        result.source_note = "New Jersey uses the public search result Status value."
        result.success = True
        return result
    except Exception as exc:
        result.error = f"NJ error: {exc}"
        return result


def search_nj_with_name_fallback(page, org):
    result = search_nj_direct(page, org)
    if public_status(result) != "Not Registered":
        return result
    for variant in organization_name_variants(
        org.organization_name,
        org.ein,
        include_ein_aliases=True,
        include_name_segments=True,
        include_compact_legal_suffixes=True,
        include_leading_article_variants=True,
        include_broad_query_prefixes=False,
    )[:8]:
        fallback_org = SimpleNamespace(organization_name=variant, ein="")
        fallback = search_nj_direct(page, fallback_org)
        if public_status(fallback) == "Site Not Reachable":
            return copy_name_fallback_result(org, fallback)
        if public_status(fallback) == "Not Registered":
            continue
        if result_registry_name_is_safe(fallback, org.organization_name, org.ein):
            fallback.source_note = (
                (fallback.source_note or "New Jersey public search found a matching organization-name record.")
                + " CharityClarity used a name fallback after the EIN search returned no matching record."
            )
            return copy_name_fallback_result(org, fallback)
    return result


def search_pa_with_name_fallback(page, org):
    result = checker.search_pa(page, org)
    if public_status(result) != "Not Registered":
        return result
    url = "https://www.charities.pa.gov/#/page/searchCharities"
    safe_targets = organization_match_target_variants(org.organization_name, org.ein)
    for variant in organization_name_variants(
        org.organization_name,
        org.ein,
        include_ein_aliases=True,
        include_name_segments=True,
        include_compact_legal_suffixes=True,
        include_leading_article_variants=True,
        include_broad_query_prefixes=False,
    )[:8]:
        fallback = checker.StateResult(org.organization_name, org.ein, "PA", checker.STATUS_UNKNOWN, url)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            checker.safe_wait_for_network_idle(page, timeout=5000)
            time.sleep(1)
            name_input = checker.find_visible_input(page, [
                'input[name*="CharityName" i]',
                'input[ng-model*="name" i]',
                'input[placeholder*="Name" i]',
                'input[name*="name" i]',
                'input[id*="name" i]',
                'input[type="text"]',
            ])
            if not name_input:
                continue
            name_input.fill("")
            name_input.fill(variant)
            if not checker.click_pa_search_button(page):
                continue
            checker.safe_wait_for_network_idle(page, timeout=15000)
            time.sleep(2)
            candidates = []
            for selector in ["tbody tr", "tr", "[role='row']"]:
                try:
                    rows = page.locator(selector)
                    for index in range(min(rows.count(), 100)):
                        row = rows.nth(index)
                        try:
                            if not row.is_visible(timeout=750):
                                continue
                            row_text = re.sub(r"\s+", " ", row.inner_text(timeout=1500)).strip()
                            if not row_text:
                                continue
                            cells = row.locator("td")
                            row_name = ""
                            expiration_raw = ""
                            if cells.count() >= 5:
                                row_name = cells.nth(0).inner_text(timeout=1500).strip()
                                expiration_raw = cells.nth(4).inner_text(timeout=1500).strip()
                            if not row_name:
                                row_name = clean_registry_name(re.split(r"\bEIN\b|\bExpiration\b|\bStatus\b", row_text, maxsplit=1, flags=re.I)[0])
                            score = target_name_score(row_name, safe_targets)
                            if score < 450 and not compatible_ein_alias_for_name(org.organization_name, row_name):
                                continue
                            if not expiration_raw:
                                expiration_raw = checker.extract_labeled_value_from_text(row_text, ["Expiration Date", "Expiration"]) if hasattr(checker, "extract_labeled_value_from_text") else ""
                            candidates.append((score, row_name, row_text, expiration_raw))
                        except Exception:
                            continue
                except Exception:
                    continue
            if not candidates:
                continue
            candidates.sort(key=lambda item: item[0], reverse=True)
            _, row_name, row_text, expiration_raw = candidates[0]
            fallback.matched_registry_name = clean_registry_name(row_name)
            expiration_date = parse_due_date(expiration_raw)
            if re.search(r"\bexempt\b", row_text or "", re.I):
                fallback.raw_status_text = "Exempt"
                fallback.status = "Exempt"
            elif expiration_date:
                fallback.raw_status_text = expiration_raw
                fallback.status = status_from_calendar_date(expiration_date)
            else:
                status_text = checker.extract_labeled_value_from_text(row_text, ["Status", "Registration Status"]) if hasattr(checker, "extract_labeled_value_from_text") else ""
                fallback.raw_status_text = status_text or "Pennsylvania name result found"
                fallback.status = status_text or checker.STATUS_UNKNOWN
            fallback.source_note = "Pennsylvania name search found a matching row after the EIN search returned no matching record."
            fallback.success = True
            return fallback
        except Exception as exc:
            fallback.error = f"PA name fallback error: {exc}"
            continue
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
    filing_evidence_patterns = [
        r"Annual\s+filings?(?:\s+and\s+documents)?[\s\S]{0,4000}\bForm[\s-]*PC\b[\s\S]{0,4000}\b20\d{2}\b",
        r"Annual\s+filings?(?:\s+and\s+documents)?[\s\S]{0,4000}\b20\d{2}\b[\s\S]{0,4000}\bForm[\s-]*PC\b",
        r"Annual\s+filing\s+documents[\s\S]{0,4000}\bFiscal\s+Year\s+End\b[\s\S]{0,4000}\b20\d{2}\b",
        r"Annual\s+renewal\s+data[\s\S]{0,4000}\bStatus\s+of\s+Filing\b[\s\S]{0,4000}\b20\d{2}\b",
        r"Year\s+Represented\s*:?\s*20\d{2}",
        r"Latest\s+FYE\s*:?\s*20\d{2}",
    ]
    if any(re.search(pattern, readable, re.I) for pattern in filing_evidence_patterns):
        return False
    annual_section_patterns = [
        r"Annual\s+filing\s+documents[\s\S]{0,500}?No\s+rows\s+available",
        r"Annual\s+filing\s+documents[\s\S]{0,500}?No\s+documents\s+found",
        r"Annual\s+filing\s+documents[\s\S]{0,500}?No\s+filings?\s+found",
        r"Annual\s+filing\s+documents[\s\S]{0,500}?No\s+results\s+found",
        r"Annual\s+filings?(?:\s+and\s+documents)?[\s\S]{0,500}?No\s+rows\s+available",
        r"Annual\s+filings?(?:\s+and\s+documents)?[\s\S]{0,500}?No\s+documents\s+found",
        r"Annual\s+filings?(?:\s+and\s+documents)?[\s\S]{0,500}?No\s+filings?\s+found",
        r"Annual\s+filings?(?:\s+and\s+documents)?[\s\S]{0,500}?No\s+results\s+found",
        r"Annual\s+Filing\s+Documents\s+did\s+not\s+expose\s+any\s+Fiscal\s+Year\s+End\s+values",
        r"\bNo\s+filings?\s+found\b",
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


def ein_near_registry_pattern(text: str, ein: str, pattern: str, radius: int = 320) -> bool:
    compact = re.sub(r"\s+", " ", text or "")
    ein_digits = re.sub(r"\D", "", ein or "")
    if not ein_digits:
        return False
    for match in re.finditer(pattern, compact, re.I):
        window = compact[max(0, match.start() - radius):match.end() + radius]
        if ein_digits in re.sub(r"\D", "", window):
            return True
    return False


def ein_line_has_registry_pattern(text: str, ein: str, pattern: str) -> bool:
    ein_digits = re.sub(r"\D", "", ein or "")
    if not ein_digits:
        return False
    for line in re.split(r"[\r\n]+", text or ""):
        if ein_digits in re.sub(r"\D", "", line) and re.search(pattern, line, re.I):
            return True
    return False


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
        state == "NJ"
        and re.search(r"\b(active|current|compliant|good\s+standing)\b", primary_status_fields, re.I)
        and not re.search(
            r"\b(non\W*compliant|revoked|suspended|not\s+authorized\s+to\s+solicit|may\s+not\s+(?:solicit|raise\s+funds|operate)|cease\s+and\s+desist|pending|failed\s+to\s+renew|withdrawn|retired|terminated|cancelled|canceled|voluntar(?:y|ily)\s+deactivat(?:ed|ion)|closed|inactive)\b",
            primary_status_fields,
            re.I,
        )
    ):
        return ""
    if (
        state != "NJ"
        and
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
    withdrawn_pattern = r"\b(withdrawn|retired|terminated|cancelled|canceled|voluntar(?:y|ily)\s+(?:deactivat(?:ed|ion)|surrender(?:ed)?))\b"
    closed_pattern = r"\bclosed\b"
    inactive_pattern = r"\binactive\b"
    terminal_pattern = rf"(?:{withdrawn_pattern}|{closed_pattern}|{inactive_pattern})"
    pending_pattern = r"\bpending\b"
    failed_to_renew_pattern = r"\bfailed\s+to\s+renew\b"
    if re.search(inactive_pattern, primary_status_fields, re.I):
        return "Closed / Withdrawn / Canceled"
    if state == "NJ":
        def nj_status_confirmed(pattern: str) -> bool:
            return bool(re.search(pattern, raw_fields, re.I) or ein_line_has_registry_pattern(text, result.ein, pattern))

        if nj_status_confirmed(r"\bnon\W*compliant\b"):
            return "Delinquent"
        if nj_status_confirmed(r"\brevoked\b"):
            return "Revoked"
        if nj_status_confirmed(pending_pattern):
            return "Pending"
        if nj_status_confirmed(r"\b(suspended|not\s+authorized\s+to\s+solicit|may\s+not\s+(?:solicit|raise\s+funds|operate)|cease\s+and\s+desist)\b"):
            return "Suspended"
        if nj_status_confirmed(inactive_pattern):
            return "Closed / Withdrawn / Canceled"
        if nj_status_confirmed(failed_to_renew_pattern):
            return "Failed to Renew"
        if nj_status_confirmed(withdrawn_pattern) or nj_status_confirmed(closed_pattern):
            return "Closed / Withdrawn / Canceled"
    confirmed = organization_record_confirmed(result, text) or md_detail_page_matched(result, text)
    expired_pattern = r"\bexpired\b"
    if not confirmed and not re.search(r"\b(revoked|suspended|not\s+authorized\s+to\s+solicit|may\s+not\s+(?:solicit|raise\s+funds|operate)|cease\s+and\s+desist|pending)\b|" + terminal_pattern + "|" + failed_to_renew_pattern + "|" + expired_pattern, status_evidence, re.I):
        return ""
    if state == "NJ":
        def nj_status_confirmed(pattern: str) -> bool:
            return bool(re.search(pattern, raw_fields, re.I) or ein_line_has_registry_pattern(text, result.ein, pattern))

        if nj_status_confirmed(r"\bnon\W*compliant\b"):
            return "Delinquent"
        if nj_status_confirmed(r"\brevoked\b"):
            return "Revoked"
        if nj_status_confirmed(pending_pattern):
            return "Pending"
        if nj_status_confirmed(r"\b(suspended|not\s+authorized\s+to\s+solicit|may\s+not\s+(?:solicit|raise\s+funds|operate)|cease\s+and\s+desist)\b"):
            return "Suspended"
        if nj_status_confirmed(inactive_pattern):
            return "Closed / Withdrawn / Canceled"
        if nj_status_confirmed(failed_to_renew_pattern):
            return "Failed to Renew"
        if nj_status_confirmed(withdrawn_pattern):
            return "Closed / Withdrawn / Canceled"
        if nj_status_confirmed(closed_pattern):
            return "Closed / Withdrawn / Canceled"
        return ""
    if re.search(r"\brevoked\b", status_evidence, re.I):
        return "Revoked"
    if re.search(pending_pattern, status_evidence, re.I):
        return "Pending"
    if re.search(r"\b(suspended|not\s+authorized\s+to\s+solicit|may\s+not\s+(?:solicit|raise\s+funds|operate)|cease\s+and\s+desist)\b", status_evidence, re.I):
        return "Suspended"
    if re.search(inactive_pattern, status_evidence, re.I):
        return "Closed / Withdrawn / Canceled"
    if re.search(withdrawn_pattern, status_evidence, re.I):
        return "Closed / Withdrawn / Canceled"
    if re.search(closed_pattern, status_evidence, re.I):
        return "Closed / Withdrawn / Canceled"
    if re.search(failed_to_renew_pattern, status_evidence, re.I):
        return "Failed to Renew"
    if re.search(expired_pattern, status_evidence, re.I):
        return "Delinquent"
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
    if state == "MI":
        solicitation_status = classify_mi_solicitation_status(mi_solicitation_raw_from_combined(result.raw_status_text or ""))
        if solicitation_status:
            return solicitation_status
    if state == "MI" and re.search(r"Solicitation\s+Registration\s+Status\s*:\s*Registered", result.raw_status_text or "", re.I):
        registry_date = explicit_registry_date(result, result.raw_status_text or "")
        return status_from_calendar_date(registry_date) if registry_date else base_status
    if result_explicitly_exempt(result):
        return "Exempt"
    if explicit_no_registration_status(result, combined):
        return "Not Registered"
    if state == "CT":
        ct_status_fields = " ".join([
            result.raw_status_text or "",
            result.error or "",
        ])
        if re.search(r"\b(inactive|closed|withdrawn|cancel(?:ed|led))\b", ct_status_fields, re.I):
            return "Closed / Withdrawn / Canceled"
        ct_registry_date = explicit_registry_date(result, combined)
        if ct_registry_date and re.search(r"\bPUBLIC\s+CHARITY\b", result.raw_status_text or "", re.I):
            return status_from_calendar_date(ct_registry_date)
    adverse_status = explicit_adverse_registry_status(result, combined)
    if adverse_status:
        return adverse_status
    primary_registry_fields = " ".join([result.raw_status_text or "", result.source_note or ""])
    if re.search(r"\b(non\W*compliant|delinquent)\b", primary_registry_fields, re.I):
        return "Delinquent"
    if (
        state == "NY"
        and annual_filings_absent(combined)
        and re.search(r"Annual\s+Filing\s+Documents\s+did\s+not\s+expose\s+any\s+Fiscal\s+Year\s+End\s+values", combined, re.I)
        and not result_indicates_no_record(result)
    ):
        return "Delinquent"
    if normalized == "delinquent" and annual_filings_absent(combined) and not result_indicates_no_record(result):
        return "Delinquent"
    if state == "ME" and re.search(r"\bACTIVE\b", " ".join([result.status or "", result.raw_status_text or ""]), re.I) and not explicit_registry_date(result, combined):
        return "Current"
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
    if state == "CT" and record_confirmed and registry_date and re.search(r"\bPUBLIC\s+CHARITY\b", result.raw_status_text or "", re.I):
        return status_from_calendar_date(registry_date)
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
        latest_pending_year = ca_years.get("latest_pending_year")
        latest_not_submitted_year = ca_years.get("latest_not_submitted_year")
        latest_submitted_year = ca_years.get("latest_submitted_year")
        if latest_pending_year and (not latest_submitted_year or latest_pending_year > latest_submitted_year):
            return "Pending"
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


def comments_for_result_base(result, body: str, public_facing_status: str) -> str:
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
    if state == "CA" and normalized_status == "pending":
        ca_years = ca_annual_renewal_years_from_text(body)
        latest_pending_year = ca_years.get("latest_pending_year")
        latest_pending_status = ca_years.get("latest_pending_status") or "In Process"
        latest_submitted_year = ca_years.get("latest_submitted_year")
        submitted_sentence = (
            f" The latest accepted annual renewal year identified is {latest_submitted_year}."
            if latest_submitted_year else
            " CharityClarity did not identify a later accepted annual renewal year."
        )
        if latest_pending_year:
            return (
                f"The CA Annual Renewal Data shows the {latest_pending_year} annual renewal with Status of Filing: {latest_pending_status}. "
                f"CharityClarity treats that as Pending because the public registry indicates the filing is still being processed.{submitted_sentence}"
            )
        return (
            "The CA public registry shows an In Process or Pending registration/filing status. "
            "CharityClarity treats that registry status as Pending because the filing appears to still be under review."
        )
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
    if normalized_status == "delinquent" and re.search(r"\bnon\W*compliant\b", registry_noncompliant_text, re.I):
        return f"The {state} public registry shows a Noncompliant status, which CharityClarity treats as Delinquent."
    registry_status_text = " ".join([result.raw_status_text or "", result.source_note or ""])
    if normalized_status == "delinquent" and re.search(r"\bexpired\b", registry_status_text, re.I):
        return f"The {state} public registry shows the organization registration status as Expired, which CharityClarity treats as Delinquent."
    if normalized_status == "delinquent" and state == "PA" and organization_record_confirmed(result, combined_result_text(result, body)) and not explicit_registry_date(result, body):
        return "The PA public registry returned a matching organization record but did not show a current usable expiration date, so CharityClarity treats the record as Delinquent."
    if state == "CO" and normalized_status == "delinquent" and re.search(r"\b(expired|may not solicit)\b", combined_result_text(result, body), re.I):
        registry_date = explicit_registry_date(result, body)
        if registry_date:
            return f"The CO public registry shows an expiration date of {format_date(registry_date)}, which is overdue."
        return "The CO public registry shows an expired registration status, which CharityClarity treats as Delinquent."
    if (
        state == "NY"
        and normalized_status == "delinquent"
        and re.search(r"Annual\s+Filing\s+Documents\s+did\s+not\s+expose\s+any\s+Fiscal\s+Year\s+End\s+values", combined_result_text(result, body), re.I)
    ):
        return (
            "The NY public registry detail page shows the organization record, but the annual filing section shows no annual filings available. "
            "Because the record does not show an exempt registration status, CharityClarity treats the organization as Delinquent."
        )
    if state == "CA" and normalized_status == "delinquent":
        context = filing_context(result, body)
        ca_years = ca_annual_renewal_years_from_text(body)
        latest_not_submitted_year = ca_years.get("latest_not_submitted_year")
        latest_not_submitted_status = ca_years.get("latest_not_submitted_status") or "Not Submitted"
        latest_submitted_year = ca_years.get("latest_submitted_year")
        if latest_not_submitted_year and (not latest_submitted_year or latest_not_submitted_year > latest_submitted_year):
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
    if normalized_status == "delinquent" and not context.get("represented_year") and annual_filings_absent(combined_result_text(result, body)):
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
            due_label = "extended due date" if state == "MA" and context.get("uses_extension_scenario") else "initial due date"
            return (
                f"{context['represented_year']} appears to be the most recent {state} {filing_label} year identified in the CharityClarity check. "
                f"Based on a {context['fiscal_end'][0]}/{context['fiscal_end'][1]} fiscal year end, the {context['next_report_year']} {filing_label} due date used by CharityClarity is {format_date(context['due_date'])}. "
                f"CE Status is Current based on the {due_label}.{extension_sentence}"
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
        elif state in {"CO", "PA", "WI"}:
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
                elif state == "NY":
                    status_sentence = (
                        f"CE Status is {base_status} based on the base due date. "
                        f"If the {extension_label} was granted, the extended deadline would be {format_date(extended_due)} and the status would be {extended_status}."
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


def append_registry_match_comment(result, comment: str, public_facing_status: str) -> str:
    match_name = useful_registry_name(getattr(result, "matched_registry_name", ""))
    match_identifier = (getattr(result, "matched_registry_identifier", "") or "").strip()
    if public_facing_status.lower() in {"not registered", "site not reachable"}:
        return comment
    if re.search(r"\bRegistry\s+match\s*:", comment or "", re.I):
        return comment
    if not match_name and not match_identifier:
        return comment
    spacer = "" if (comment or "").endswith((" ", "\n")) else " "
    if not match_name:
        return f"{comment}{spacer}Registry match ID: {match_identifier}."
    id_text = f" (ID: {match_identifier})" if match_identifier else ""
    return f"{comment}{spacer}Registry match: {match_name}{id_text}."


def comments_for_result(result, body: str, public_facing_status: str) -> str:
    return append_registry_match_comment(
        result,
        comments_for_result_base(result, body, public_facing_status),
        public_facing_status,
    )


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
            if latest_not_submitted_year and (not latest_submitted_year or latest_not_submitted_year > latest_submitted_year):
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


def run_state_lookup(organization_name: str, ein: str, state: str, capture_source_snapshot: bool = False, confirm_single_no_match: bool = True) -> dict:
    lookup_started = time.perf_counter()
    artifact_name = organization_name or f"EIN {format_ein(ein)}"
    lookup_name = organization_name
    org = checker.Organization(organization_name=lookup_name, ein=ein)
    if hasattr(org, "evidence_mode"):
        org.evidence_mode = capture_source_snapshot
    body = ""
    proof_url = None

    if state == "WI" and WI_SIDECAR_URL and WI_LOOKUP_SECRET:
        result = search_wi_sidecar(org)
        if confirm_single_no_match and public_status(result) == "Not Registered" and BATCH_NO_MATCH_CONFIRMATION_DELAY_SECONDS > 0:
            for _ in range(2):
                time.sleep(min(BATCH_NO_MATCH_CONFIRMATION_DELAY_SECONDS, 5.0))
                confirmed_result = search_wi_sidecar(org)
                if public_status(confirmed_result) != "Not Registered":
                    confirmed_result.source_note = " ".join(part for part in [
                        confirmed_result.source_note or "",
                        "A delayed confirmation lookup replaced an initial Wisconsin no-record response.",
                    ]).strip()
                    result = confirmed_result
                    break
        body = " ".join(part for part in [
            result.raw_status_text or "",
            result.source_note or "",
            result.matched_registry_name or "",
            result.matched_registry_identifier or "",
        ])
        return response_data_for_lookup(result, body, org, organization_name, ein, state, lookup_started)

    result = None
    BROWSER_LOOKUP_SEMAPHORE.acquire()
    lookup_started = time.perf_counter()
    with checker.sync_playwright() as p:
        browser = None
        context = None
        page = None
        try:
            browser = p.chromium.launch(headless=True)
            if state == "AK":
                result, body = search_ak_with_registration_evidence(browser, org, artifact_name)
            else:
                context = browser.new_context(user_agent=BROWSER_USER_AGENT, locale="en-US")
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
                result = validate_ma_positive_record(org, result, body)
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
                body = registry_page_body(page)
                if not (getattr(result, "matched_registry_name", "") or "").strip():
                    co_name = checker.extract_labeled_value_from_text(body, ["Name"])
                    if co_name:
                        result.matched_registry_name = co_name
            elif state == "CT":
                result = search_ct(page, org)
                body = registry_page_body(page)
            elif state == "FL":
                result = search_fl(page, org)
                if (
                    confirm_single_no_match
                    and public_status(result) in {"Not Registered", "Site Not Reachable"}
                    and FL_NOT_REGISTERED_CONFIRMATION_DELAY_SECONDS > 0
                ):
                    time.sleep(FL_NOT_REGISTERED_CONFIRMATION_DELAY_SECONDS)
                    confirmed_result = search_fl(page, org)
                    if public_status(confirmed_result) not in {"Not Registered", "Site Not Reachable"}:
                        confirmed_result.source_note = " ".join(part for part in [
                            confirmed_result.source_note or "",
                            "A delayed confirmation lookup replaced an initial Florida no-record response.",
                        ]).strip()
                        result = confirmed_result
                body = " ".join(part for part in [
                    result.raw_status_text or "",
                    result.source_note or "",
                    result.matched_registry_name or "",
                    result.matched_registry_identifier or "",
                ]).strip()
            elif state == "NY":
                result = search_with_name_variants(
                    page,
                    org,
                    checker.search_ny,
                    max_variants=10,
                    max_elapsed_seconds=min(NAME_SEARCH_VARIANT_MAX_SECONDS, 30.0),
                )
            elif state == "NJ":
                result = search_nj_direct(page, org)
                if public_status(result) != "Not Registered":
                    body = nj_detail_body(page, org)
            elif state == "PA":
                result = checker.search_pa(page, org)
            elif state == "VA":
                reachable, _, preflight_result = preflight_name_search_registry(org, "VA")
                if not reachable:
                    result = preflight_result
                else:
                    result = search_with_name_variants(
                        page,
                        org,
                        search_va_bounded,
                        max_variants=8,
                        max_elapsed_seconds=NAME_SEARCH_VARIANT_MAX_SECONDS,
                        reject_va_suspended_from_leading_the_drop=False,
                        include_ein_aliases=True,
                        include_name_segments=True,
                        include_and_segments=False,
                        include_compact_legal_suffixes=False,
                        include_leading_article_variants=True,
                        prioritize_institution_reductions=True,
                    )
            elif state == "SC":
                reachable, _, preflight_result = preflight_name_search_registry(org, "SC")
                if not reachable:
                    result = preflight_result
                else:
                    result = search_with_name_variants(
                        page,
                        org,
                        checker.search_sc,
                        max_variants=10,
                        max_elapsed_seconds=SC_NAME_VARIANT_MAX_SECONDS,
                        include_ein_aliases=True,
                        include_name_segments=True,
                        include_compact_legal_suffixes=True,
                        include_leading_article_variants=True,
                    )
            elif state == "HI":
                result = search_hi_precise(page, org)
                if public_status(result) != "Not Registered":
                    body = hi_detail_body(page)
            elif state == "MI":
                mi_started = time.perf_counter()
                result = search_bundled_extension_state(page, org, "MI")
                mi_elapsed = time.perf_counter() - mi_started
                if MI_ENABLE_NAME_FALLBACK and public_status(result) == "Not Registered" and mi_elapsed < (LOOKUP_SOFT_MAX_SECONDS - 6):
                    fallback_result = search_mi_name_fallback(page, org)
                    if public_status(fallback_result) != "Not Registered":
                        result = fallback_result
                if (
                    confirm_single_no_match
                    and public_status(result) in {"Not Registered", "Site Not Reachable"}
                    and BATCH_NO_MATCH_CONFIRMATION_DELAY_SECONDS > 0
                    and re.search(r"No results frame|Could not find the Michigan results frame|Could not load the Michigan detail page", " ".join([result.raw_status_text or "", result.source_note or "", result.error or ""]), re.I)
                ):
                    time.sleep(min(BATCH_NO_MATCH_CONFIRMATION_DELAY_SECONDS, 5.0))
                    confirmed_result = search_bundled_extension_state(page, org, "MI")
                    if public_status(confirmed_result) not in {"Not Registered", "Site Not Reachable"}:
                        confirmed_result.source_note = " ".join(part for part in [
                            confirmed_result.source_note or "",
                            "A delayed confirmation lookup replaced an initial Michigan incomplete-results response.",
                        ]).strip()
                        result = confirmed_result
                    elif re.search(r"No results frame|Could not find the Michigan results frame|Could not load the Michigan detail page", " ".join([confirmed_result.raw_status_text or "", confirmed_result.source_note or "", confirmed_result.error or ""]), re.I):
                        result.status = "Site Not Reachable"
                        result.raw_status_text = "Michigan results frame did not load after confirmation"
                        result.source_note = "Michigan's registry search page loaded, but the results/detail frame did not load on two attempts."
                        result.success = False
                body = registry_page_body(page)
            elif state == "MN":
                result = search_mn(page, org)
                body = registry_page_body(page)
            elif state == "OH":
                result = search_oh(page, org)
                body = registry_page_body(page)
            elif state == "WI":
                result = search_wi(page, org)
                body = registry_page_body(page)
            elif state == "ME":
                result = search_me_serialized(page, org)
                me_status_source = " ".join([result.raw_status_text or "", result.source_note or ""])
                if public_status(result) == "Site Not Reachable":
                    body = ""
                elif re.search(r"Maine uses the Status shown|No matching organization|No record found|no matching", me_status_source, re.I):
                    body = registry_page_body(page)
                else:
                    body = me_detail_body(page, org)
                    enrich_me_result_from_body(result, body)
            elif state == "ND":
                reachable, _, preflight_result = preflight_name_search_registry(org, "ND")
                if not reachable:
                    result = preflight_result
                else:
                    result = search_with_name_variants(
                        page,
                        org,
                        checker.search_nd,
                        max_variants=18,
                        max_elapsed_seconds=NAME_SEARCH_VARIANT_MAX_SECONDS,
                        include_ein_aliases=True,
                        include_name_segments=True,
                        include_compact_legal_suffixes=False,
                        include_leading_article_variants=True,
                        prioritize_institution_reductions=True,
                    )
            elif state == "OR":
                result = search_bundled_extension_state(page, org, "OR")
                body = registry_page_body(page)
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
            BROWSER_LOOKUP_SEMAPHORE.release()

    return response_data_for_lookup(result, body, org, organization_name, ein, state, lookup_started)


def fragile_batch_result_needs_confirmation(result: dict) -> bool:
    """Identify results that should not be trusted from a busy multi-state batch alone."""
    state = (result.get("state") or "").upper()
    status = (result.get("status") or "").strip().lower()
    name_registry_states = {"CO", "CT", "FL", "ME", "MI", "ND", "NY", "OR", "SC", "VA", "WI"}
    if state in name_registry_states and status in {"site not reachable", "error", ""}:
        return True
    if state in {"CO", "FL", "ME", "ND", "NY", "OR", "SC", "VA"}:
        return status == "not registered"
    if state == "MI":
        return status == "not registered"
    if state == "WI":
        return status in {"not registered", "pending", "delinquent"}
    return False


def confirm_fragile_batch_results(results: list[dict]) -> list[dict]:
    if not CONFIRM_FRAGILE_BATCH_RESULTS:
        return results
    jobs = [
        (index, result)
        for index, result in enumerate(results)
        if fragile_batch_result_needs_confirmation(result)
    ]
    if not jobs:
        return results

    def run_confirmation(job: tuple[int, dict]) -> tuple[int, dict | None]:
        index, original = job
        name = (original.get("organization_name") or "").strip()
        ein = original.get("ein") or ""
        state = (original.get("state") or "").upper()
        if not name or not ein or not state:
            return index, None
        try:
            original_status_lower = (original.get("status") or "").strip().lower()
            original_is_no_match = original_status_lower == "not registered"
            original_is_unreachable = original_status_lower == "site not reachable"
            if state in {"CO", "FL", "ME", "MI", "WI"} and (original_is_no_match or original_is_unreachable) and BATCH_NO_MATCH_CONFIRMATION_DELAY_SECONDS > 0:
                time.sleep(BATCH_NO_MATCH_CONFIRMATION_DELAY_SECONDS)
            confirmed = run_state_lookup(name, ein, state)
            if (
                state in {"CO", "FL", "ME", "MI", "WI"}
                and (original_is_no_match or original_is_unreachable)
                and (confirmed.get("status") or "").strip().lower() in {"not registered", "site not reachable"}
                and BATCH_NO_MATCH_CONFIRMATION_DELAY_SECONDS > 0
            ):
                time.sleep(min(BATCH_NO_MATCH_CONFIRMATION_DELAY_SECONDS, 5.0))
                second_confirmed = run_state_lookup(name, ein, state)
                if (second_confirmed.get("status") or "").strip().lower() not in {"not registered", "site not reachable"}:
                    confirmed = second_confirmed
        except Exception as exc:
            log_error(f"{state} batch confirmation for {format_ein(ein)} failed: {exc}")
            return index, None
        confirmed["batch_confirmation"] = "isolated_retry"
        original_status = (original.get("status") or "").strip()
        confirmed_status = (confirmed.get("status") or "").strip()
        if confirmed_status and confirmed_status.lower() != "site not reachable" and confirmed_status != original_status:
            note = (
                f"Batch reliability note: the initial multi-state result was {original_status or 'blank'}; "
                f"an isolated confirmation lookup returned {confirmed_status}."
            )
            confirmed["comments"] = "\n\n".join(part for part in [confirmed.get("comments") or "", note] if part)
            return index, confirmed
        return index, None

    calm_no_match_states = {"FL", "ME", "WI"}
    serial_jobs = [
        job for job in jobs
        if (job[1].get("state") or "").upper() in calm_no_match_states
        and (job[1].get("status") or "").strip().lower() in {"not registered", "site not reachable"}
    ]
    parallel_jobs = [job for job in jobs if job not in serial_jobs]

    for index, confirmed in map(run_confirmation, serial_jobs):
        if confirmed is not None:
            results[index] = confirmed

    if parallel_jobs:
        worker_count = min(BATCH_CONFIRMATION_WORKERS, len(parallel_jobs))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            for index, confirmed in executor.map(run_confirmation, parallel_jobs):
                if confirmed is not None:
                    results[index] = confirmed
    return results


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
        results = list(executor.map(lambda args: run_state_lookup(*args, confirm_single_no_match=False), lookup_requests))

    results = confirm_fragile_batch_results(results)

    submitted_names_by_ein = {
        re.sub(r"\D", "", ein or ""): (name or "").strip()
        for name, ein, _ in lookup_requests
    }
    name_only_states = {"CT", "FL", "ME", "ND", "OR", "SC", "VA", "WI"}
    trusted_discovery_states = {"AK", "CA", "CO", "HI", "MA", "MD", "MI", "MN", "NJ", "NY", "OH", "PA"}
    discovered_names: dict[str, str] = {}
    for result in results:
        ein_key = re.sub(r"\D", "", result.get("ein") or "")
        state = (result.get("state") or "").upper()
        matched_name = (result.get("matched_registry_name") or "").strip()
        submitted_name = submitted_names_by_ein.get(ein_key, "")
        if (
            ein_key
            and state in trusted_discovery_states
            and matched_name
            and normalized_match_name(matched_name) != normalized_match_name(submitted_name)
        ):
            discovered_names.setdefault(ein_key, matched_name)

    retry_jobs = []
    for index, result in enumerate(results):
        ein_key = re.sub(r"\D", "", result.get("ein") or "")
        original_name = submitted_names_by_ein.get(ein_key, "")
        discovered_name = discovered_names.get(ein_key, "")
        if discovered_name and not (result.get("organization_name") or "").strip():
            result["organization_name"] = discovered_name
        state = (result.get("state") or "").upper()
        if state not in name_only_states or (result.get("status") or "").lower() != "not registered":
            continue
        retry_names = []
        for name in [discovered_name, *known_names_for_ein(result.get("ein") or "")]:
            cleaned = re.sub(r"\s+", " ", (name or "").strip())
            if not cleaned:
                continue
            if normalized_match_name(cleaned) == normalized_match_name(original_name):
                continue
            if cleaned.lower() not in {existing.lower() for existing in retry_names}:
                retry_names.append(cleaned)
        if retry_names:
            retry_jobs.append((index, result.get("ein") or "", state, retry_names))

    if retry_jobs and ENABLE_CROSS_STATE_NAME_RETRY:
        retry_worker_count = min(MAX_PARALLEL_LOOKUPS, len(retry_jobs))

        def run_retry_job(job):
            index, ein, state, retry_names = job
            last_retry = None
            for retry_name in retry_names:
                last_retry = run_state_lookup(retry_name, ein, state)
                if (last_retry.get("status") or "").lower() != "not registered":
                    return index, last_retry
            return index, last_retry

        with ThreadPoolExecutor(max_workers=retry_worker_count) as executor:
            for index, retry_result in executor.map(run_retry_job, retry_jobs):
                if retry_result is not None:
                    results[index] = retry_result
    return results


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


def payload_missing_required_organization_name(payload: dict) -> bool:
    organization_name = (payload.get("organization_name") or "").strip()
    raw_organizations = payload.get("organizations")
    if isinstance(raw_organizations, list):
        for item in raw_organizations:
            if not isinstance(item, dict):
                continue
            if len(re.sub(r"\D", "", format_ein(item.get("ein") or ""))) != 9:
                continue
            item_name = (item.get("organization_name") or organization_name).strip()
            if not item_name:
                return True
        return False
    if len(re.sub(r"\D", "", format_ein(payload.get("ein") or ""))) == 9:
        return not organization_name
    return False


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
            audit_context = request_audit_context(self, payload)

            requested_states = payload.get("states")
            state = (payload.get("state") or "").strip().upper()
            domain = email_domain(email)
            admin_passcode = (payload.get("admin_passcode") or "").strip()
            staging_error = staging_access_error(email, admin_passcode)
            if staging_error:
                self._send_json(403, {"error": staging_error})
                return
            if is_exempt_domain(domain) and admin_passcode != ADMIN_PASSCODE:
                self._send_json(401, {"error": "Enter the Compliance Express passcode to use internal features."})
                return
            privileged = is_privileged_request(email, domain)
            if payload_missing_required_organization_name(payload):
                self._send_json(400, {"error": "Enter the organization name as registered, if known."})
                return
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

            limit_ein = organizations[0]["ein"] if organizations else ""
            is_batch = isinstance(requested_states, list)
            if is_batch and not privileged and domain_is_limited(domain, limit_ein):
                self._send_json(429, {"error": "A complimentary snapshot was already requested for this email domain."})
                return
            if is_batch and not privileged and device_is_limited(device_id, limit_ein):
                self._send_json(429, {"error": "A complimentary snapshot was already requested from this browser."})
                return

            append_submission_log(email, organizations, states, audit_context)
            results = run_state_lookups_parallel(organizations, states)
            append_lead_log(email, results, audit_context)
            if is_batch:
                if not privileged and should_record_domain_check(results):
                    record_domain_check(domain, limit_ein)
                    record_device_check(device_id, limit_ein)
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

