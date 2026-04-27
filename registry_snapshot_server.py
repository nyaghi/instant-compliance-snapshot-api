ARTIFACTS_DIR = Path(os.environ.get("CE_ARTIFACTS_DIR", str(BASE_DIR / "artifacts")))
PORT = int(os.environ.get("PORT", "8765"))
HOST = os.environ.get("HOST") or ("0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
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
