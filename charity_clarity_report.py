"""Deterministic presentation of completed master-backend snapshots; no registry access."""
from collections import Counter
from datetime import datetime, timezone
from html import escape
from io import BytesIO
from pathlib import Path
import re
from urllib.parse import urlparse

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

REPORT_VERSION = "1.0.1"
NAVY = colors.HexColor("#0B2A5B")
INK = colors.HexColor("#172B45")
MUTED = colors.HexColor("#536274")
PALE = colors.HexColor("#F3F6FA")
ASSETS = Path(__file__).resolve().parent / "report-assets"
LOW = {"Current", "Exempt"}
MODERATE = {"Upcoming Filing", "Not Registered", "Pending", "Closed / Withdrawn / Canceled"}
HIGH = {"Delinquent", "Suspended", "Revoked", "Failed to Renew", "Expired"}
INCOMPLETE = {"Site Not Reachable", "Needs Review", "Unable to Confirm", "Unable to Verify", "Unknown", "No Confirmed Match"}
DOWNLOADABLE = {"KS", "KY", "LA", "NH", "OR"}


def text(value, limit=10000):
    value = str(value or "")
    if len(value) > limit:
        raise ValueError("A report field exceeds the supported length.")
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value).strip()


def validate_results(payload, supported_states):
    rows = payload.get("results")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 30:
        raise ValueError("Generate a report from 1 to 30 completed state results for one organization.")
    clean, seen, identity = [], set(), None
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid report result.")
        state = text(row.get("state"), 2).upper()
        name = text(row.get("organization_name"), 250)
        ein = re.sub(r"\D", "", text(row.get("ein"), 20))
        if state not in supported_states or state in seen or not name or len(ein) != 9:
            raise ValueError("Report results need unique supported states and a valid organization/EIN.")
        if identity is not None and identity != (name, ein):
            raise ValueError("Generate separate reports for different organizations.")
        identity = (name, ein)
        seen.add(state)
        status = text(row.get("status"), 100)
        if status not in LOW | MODERATE | HIGH | INCOMPLETE:
            raise ValueError("A result status is not supported by this report template.")
        checked = row.get("checked_at_epoch")
        if checked is not None:
            if isinstance(checked, bool) or not isinstance(checked, (int, float)) or not 0 < checked < 4102444800:
                raise ValueError("Invalid snapshot timestamp.")
        clean.append({
            **{k: text(row.get(k), 10000) for k in ("comments", "raw_status_text", "source_note")},
            **{k: text(row.get(k), 500) for k in ("source_url", "matched_registry_identifier", "app_version", "computed_due_date")},
            "organization_name": name, "ein": ein, "state": state, "status": status,
            "checked_at_epoch": checked,
        })
    return sorted(clean, key=lambda r: r["state"])


def risk_level(row):
    status = row["status"]
    if status in HIGH:
        return 3
    if status in MODERATE:
        return 2
    if status in LOW:
        return 1
    return None


def risk_summary(rows):
    levels = [risk_level(row) for row in rows]
    incomplete = levels.count(None)
    highest = max((n for n in levels if n), default=0)
    # Missing checks must never produce an overall low-risk conclusion.
    label = "Not assessed" if highest < 2 and incomplete else {0: "Not assessed", 1: "Low (1 of 3)", 2: "Moderate (2 of 3)", 3: "High (3 of 3)"}[highest]
    if incomplete and highest >= 2:
        label += " - provisional"
    return label, incomplete, Counter(levels)


def shortened(value, length=200):
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(value) <= length:
        return value
    return value[:length].rsplit(" ", 1)[0] + "..."


def evidence(row):
    # Copy a concise excerpt. Do not recalculate deadlines or infer a new state status.
    body = row["comments"].split("Data freshness note:", 1)[0]
    body = body.split("Registry match:", 1)[0].strip()
    if body.startswith("Official state records show active registration or current filing evidence") and row["raw_status_text"]:
        body = "Registry excerpt: " + row["raw_status_text"]
    body = re.sub(r", so the status is (?:Current|Delinquent|Upcoming Filing)\.", ".", body)
    return shortened(body or row["raw_status_text"] or row["source_note"] or "No supporting detail returned.", 225)


def freshness(rows):
    notes = []
    for row in rows:
        if row["state"] not in DOWNLOADABLE:
            continue
        comment = row["comments"]
        downloaded = re.search(r"dataset last downloaded:\s*([^\s.]+(?:\.[0-9]+)?(?:\+00:00|Z)?)", comment)
        source_date = re.search(r"State source date:\s*(.*?)\.\s*(?:Downloads|$)", comment)
        # Preserve the actual result's timestamp, not today's manifest or generation time.
        when = downloaded.group(1).rstrip(".") if downloaded else "not supplied in this snapshot"
        notes.append((row["state"], when, source_date.group(1) if source_date else "not supplied"))
    return notes


def safe_source(value):
    try:
        parsed = urlparse(value)
        if parsed.scheme in {"https", "http"} and parsed.hostname and not parsed.username and not parsed.password:
            return value, parsed.hostname
    except ValueError:
        pass
    return "", "Source link unavailable"


def generate_report(payload, supported_states):
    rows = validate_results(payload, set(supported_states))
    risk, incomplete, counts = risk_summary(rows)
    page_count = 2 + (len(rows) + 9) // 10
    org, ein = rows[0]["organization_name"], rows[0]["ein"]
    ein = ein[:2] + "-" + ein[2:]
    styles = {
        "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=24, leading=29, textColor=NAVY, spaceAfter=12),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=NAVY, spaceAfter=9),
        "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=NAVY, spaceAfter=4),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=14, textColor=INK, spaceAfter=8),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8.2, leading=11, textColor=MUTED, spaceAfter=4),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.2, leading=11, textColor=INK),
        "head": ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=colors.white),
    }

    def p(value, style="body", markup=False):
        return Paragraph(value if markup else escape(str(value)), styles[style])

    def evidence_cell(value):
        # Bound excerpts to three lines so every ten-state section stays on one page.
        limit = len(value)
        cell = p(value, "cell")
        while cell.wrap(266, 1000)[1] > 33 and limit > 40:
            limit -= 10
            cell = p(shortened(value, limit), "cell")
        return cell

    def table(data, widths, header=True):
        grid = Table(data, colWidths=widths, hAlign="LEFT")
        commands = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("LINEBELOW", (0, 0), (-1, -1), .4, colors.HexColor("#DCE3EB"))]
        if header:
            commands += [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE])]
        grid.setStyle(TableStyle(commands))
        return grid

    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=(612, 792), leftMargin=42, rightMargin=42, topMargin=94, bottomMargin=53, title=f"CharityClarity - {org}", author="Compliance Express")
    logo = ImageReader(str(ASSETS / "compliance-express.png"))
    brand = ImageReader(str(ASSETS / "charityclarity.png"))

    def page_frame(canvas, document):
        canvas.saveState()
        canvas.drawImage(logo, 42, 747, width=150, height=36.15, mask="auto")
        canvas.drawImage(brand, 443, 747, width=127, height=42.33, mask="auto")
        canvas.setStrokeColor(colors.HexColor("#DCE3EB"))
        canvas.line(42, 719, 570, 719)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(42, 33, "www.compliance-express.com  |  info@compliance-express.com")
        canvas.drawRightString(570, 33, f"CharityClarity  |  {document.page} / {page_count}")
        canvas.restoreState()

    checked = [r["checked_at_epoch"] for r in rows if r["checked_at_epoch"]]
    def stamp(epoch):
        return datetime.fromtimestamp(epoch, timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    period = stamp(min(checked)) if checked else "Check time not supplied"
    if checked and max(checked) != min(checked):
        period += " to " + stamp(max(checked))
    story = [p("Charity registration snapshot", "title"), p(org, "h2"), p(f"EIN {ein}  |  {len(rows)} states checked", "small"), p(period, "small"), Spacer(1, 17), p("Executive summary", "h2"), p(f"Compliance risk indicator: {risk}", "h2")]
    if counts[3]:
        summary = f"{counts[3]} states show overdue or adverse registration signals. Prioritize those findings for confirmation and corrective follow-up."
    elif counts[2]:
        summary = f"{counts[2]} states show an upcoming filing or another registration question that needs follow-up."
    elif incomplete:
        summary = "The available results do not support an overall risk assessment until the incomplete checks are resolved."
    else:
        summary = "All checked states returned Current or Exempt. Continue routine monitoring of the recorded registration position."
    story.append(p(summary))
    if incomplete:
        story.append(p(f"{incomplete} checks are incomplete. Their registration status remains unconfirmed; the overall indicator cannot establish the organization's complete position."))
    metrics = [[p("High signals", "head"), p("Moderate signals", "head"), p("Low signals", "head"), p("Not assessed", "head")], [p(counts[3], "h2"), p(counts[2], "h2"), p(counts[1], "h2"), p(incomplete, "h2")]]
    story.extend([table(metrics, [132]*4), Spacer(1, 18), p("Risk legend", "h2")])
    legend = [
        ("3 - High", "Delinquent, suspended, revoked, expired or failed to renew. Confirm the adverse/overdue signal and required next steps promptly."),
        ("2 - Moderate", "Upcoming filing, pending, no registration found, or closed/withdrawn/canceled. Confirm the deadline, record or applicable filing obligation."),
        ("1 - Low", "Current or Exempt in the returned snapshot. Keep supporting evidence and monitor for changes."),
        ("Not assessed", "Registry unavailable or evidence inconclusive. Complete verification before relying on the affected state result."),
    ]
    for title, detail in legend:
        story.extend([p(title, "h3"), p(detail, "small")])
    story.append(p("The overall indicator uses the highest returned risk signal, not an average. It is a follow-up priority, not a finding that a filing obligation or violation exists. Unchecked states are outside this report's scope.", "small"))
    story.extend([PageBreak(), p("Prioritized action items", "title")])
    groups = [
        ("1. Verify adverse or overdue records", lambda r: r["status"] in HIGH, "Confirm the cited record and any accepted renewal, extension or reinstatement. Ask the state what filing or correction is needed before relying on the current registration position."),
        ("2. Complete unresolved checks", lambda r: risk_level(r) is None, "Retry or confirm directly with the registry. Obtain a completed search and identity match; do not treat a failed lookup as evidence of no registration."),
        ("3. Prepare upcoming filings", lambda r: r["status"] == "Upcoming Filing", "Confirm the returned due date or certificate expiration, assemble the filing materials and assign an owner. Check any accepted extension before changing the deadline."),
        ("4. Confirm registration obligations", lambda r: r["status"] in MODERATE - {"Upcoming Filing"}, "Reconcile the national entity and any relevant affiliates. Confirm fundraising activity, applicable registration or exemption requirements, and whether a pending or closed record needs follow-up."),
        ("5. Maintain current and exempt records", lambda r: r["status"] in LOW, "Retain evidence and monitor the next filing or exemption conditions as applicable."),
    ]
    action_number = 0
    for title, predicate, action in groups:
        states = ", ".join(r["state"] for r in rows if predicate(r))
        if states:
            action_number += 1
            title = f"{action_number}. " + title.split(". ", 1)[1]
            story.extend([p(title, "h3"), p(states, "small"), p(action, "small"), Spacer(1, 6)])
    notes = freshness(rows)
    if notes:
        story.extend([Spacer(1, 7), p("Downloadable data freshness", "h2")])
        for state, when, source_date in notes:
            try:
                downloaded = datetime.fromisoformat(when)
                if downloaded.tzinfo is not None:
                    when = downloaded.astimezone(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
            except ValueError:
                pass
            story.append(p(f"{state}: scheduled download {when}. State source date: {source_date}.", "small"))
        story.append(p("Downloads may lag registry changes. Confirm time-sensitive decisions directly with the state. These dates are from the checked results; generating this report does not refresh the data.", "small"))
    story.extend([Spacer(1, 7), p("Basis and limits", "h3"), p("This report summarizes CharityClarity output for the listed organization and states. It does not independently verify the output, determine where registration is legally required, or replace a complete compliance review. Evidence excerpts are shortened; linked registry records and the full snapshot comments provide the supporting detail.", "small")])
    for start in range(0, len(rows), 10):
        section = rows[start:start+10]
        story.extend([PageBreak(), p("State findings", "title"), p(f"States {start+1}-{start+len(section)} of {len(rows)}. Statuses and evidence are copied from the snapshot.", "small"), Spacer(1, 8)])
        data = [[p("State / status", "head"), p("Evidence excerpt", "head"), p("Registry source", "head")]]
        for row in section:
            url, host = safe_source(row["source_url"])
            link = f'<link href="{escape(url, quote=True)}" color="#0B2A5B">Open {escape(row["state"])} registry</link>' if url else escape(host)
            if row["matched_registry_identifier"]:
                link += "<br/>ID: " + escape(shortened(row["matched_registry_identifier"], 35))
            source = p(link, "cell", markup=True)
            status_text = f'<b>{escape(row["state"])}</b><br/>{escape(row["status"])}'
            data.append([p(status_text, "cell", markup=True), evidence_cell(evidence(row)), source])
        story.append(table(data, [112, 282, 134]))
        story.extend([Spacer(1, 12), p("Report template " + REPORT_VERSION + " | Snapshot version(s): " + ", ".join(sorted({r["app_version"] or "not supplied" for r in section})), "small")])
    doc.build(story, onFirstPage=page_frame, onLaterPages=page_frame)
    return output.getvalue()
