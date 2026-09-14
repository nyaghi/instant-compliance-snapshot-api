"""Deterministic presentation of completed master-backend snapshots; no registry access."""
from collections import Counter
from datetime import date, datetime, timezone
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

REPORT_VERSION = "1.1.0"
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
ADVERSE = HIGH | {"Closed / Withdrawn / Canceled"}
DISCLAIMER = ("CharityClarity provides preliminary results for diagnostic purposes only, not legal or tax advice. "
               "Its compliance statuses generally apply a more conservative interpretation than the state's displayed "
               "status, which may not reflect the latest filing position. Confirm relevant records and requirements "
               "before making legal, tax or fundraising decisions.")


def snapshot_due_date(row):
    """Read an existing effective deadline; never calculate a new state deadline."""
    def parse(value):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                pass
        return None
    computed = parse(row.get("computed_due_date") or "")
    if computed:
        return computed
    # Only the interpreted comment's labeled deadline, before aliases/source dates.
    body = (row.get("comments") or "").split("Registry match:", 1)[0].split("Data freshness note:", 1)[0]
    token = r"(\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})"
    extension = re.findall(r"(?:extension (?:runs )?through|extension applies and uses|extended (?:due date|deadline)(?: is| of|:)?)[ ]+" + token, body, re.I)
    if extension:
        return parse(extension[-1])
    # If an extension is mentioned but its effective date cannot be read, do not
    # accidentally promote an earlier base deadline as the effective deadline.
    if re.search(r"base (?:due date|deadline)", body, re.I):
        return None
    found = re.findall(r"(?:expiration(?: date)?|renewal date|(?:next filing |annual report )?due date|deadline)(?:\s*\([^)]*\))?(?:\s+(?:is|of))?\s*:?\s*" + token, body, re.I)
    found += re.findall(r"(?:is due|certificate expires)\s+" + token, body, re.I)
    dates = {parse(value) for value in found} - {None}
    return next(iter(dates)) if len(dates) == 1 else None


def action_items(rows):
    """Action priority changes presentation only; returned state statuses stay intact."""
    urgent = []
    for row in rows:
        checked = row.get("checked_at_epoch")
        due = snapshot_due_date(row)
        if checked and due and row["status"] in {"Current", "Upcoming Filing"}:
            days = (due - datetime.fromtimestamp(checked, timezone.utc).date()).days
            if 0 <= days <= 60:
                urgent.append((due, row["state"], days))
    urgent.sort()
    urgent_states = {state for _, state, _ in urgent}
    groups = [
        ("Resolve adverse, overdue or closed records", [r["state"] for r in rows if r["status"] in ADVERSE],
         "Prioritize suspended, revoked and closed/withdrawn/canceled records as well as overdue filings. Confirm the restriction or lapse, any accepted renewal or reinstatement, and the steps required before relying on the registration."),
        ("Renewals due within 60 days", [f"{state}: {due.strftime('%b %d, %Y')} ({'today' if days == 0 else str(days) + ' days'})" for due,state,days in urgent],
         "Prioritized by the earliest returned deadline, as of each state check. Assign an owner, confirm the deadline and any extension qualification, and assemble the renewal materials now."),
        ("Complete unresolved checks", [r["state"] for r in rows if r["status"] in INCOMPLETE],
         "Retry or confirm directly with the registry. A failed or inconclusive search does not establish that the organization is unregistered."),
        ("Follow up on pending registrations", [r["state"] for r in rows if r["status"] == "Pending"],
         "Review state emails, letters and portal messages for missing items or questions. If the next step is unclear, contact the state for the application's status."),
        ("Schedule upcoming filings", [r["state"] for r in rows if r["status"] == "Upcoming Filing" and r["state"] not in urgent_states],
         "Confirm the returned due date or expiration and assign a filing owner. Where no usable deadline was supplied, verify it directly with the state."),
        ("Confirm registration obligations", [r["state"] for r in rows if r["status"] == "Not Registered"],
         "Review fundraising activity and applicable registration or exemption requirements. No record found does not, by itself, establish a violation or a filing obligation."),
        ("Maintain current and exempt records", [r["state"] for r in rows if r["status"] in LOW and r["state"] not in urgent_states],
         "Retain supporting evidence, monitor renewal dates and confirm that exemption conditions continue to apply."),
    ]
    return [(title, states, detail) for title, states, detail in groups if states]


def operational_insights(rows):
    insights = []
    by_status = lambda statuses: [r["state"] for r in rows if r["status"] in statuses]
    footprint = by_status((LOW | MODERATE | HIGH) - {"Not Registered", "Closed / Withdrawn / Canceled"})
    missing = by_status({"Not Registered"})
    if len(footprint) > 15 and missing:
        insights.append(("Broad registration footprint: review coverage gaps",
            f"Records were identified in {len(footprint)} checked states, suggesting a broad, potentially national footprint. No registration was found in {', '.join(missing)}. Compare these states with actual solicitation activity and document whether registration or an exemption applies. The snapshot does not establish where the organization operates."))
    exempt = by_status({"Exempt"})
    review = by_status({"Not Registered", "Pending", "Current", "Upcoming Filing", "Delinquent", "Expired", "Failed to Renew"})
    if exempt and review:
        insights.append(("Investigate exemption opportunities",
            f"Exemption is recorded in {', '.join(exempt)}. Review state-specific eligibility in {', '.join(review)}"
            + (f", starting with the no-record states {', '.join(missing)}" if missing else "")
            + ". An exemption in one state does not establish eligibility elsewhere. Keep required filings current while any exemption request is being considered."))
    pending = by_status({"Pending"})
    if pending:
        insights.append(("Pending applications need an assigned follow-up",
            f"For {', '.join(pending)}, check state communications for outstanding information and confirm receipt of any response. Contact the state if the application's next step is unclear; Pending does not establish approval."))
    urgent = next((states for title,states,_ in action_items(rows) if title == "Renewals due within 60 days"), [])
    if len(urgent) >= 3:
        insights.append(("Coordinate a cluster of near-term renewals",
            f"{len(urgent)} states have returned deadlines within 60 days of their checks. Use the dated action list to sequence work, assign owners and prepare shared financial materials once."))
    unresolved = by_status(INCOMPLETE)
    if unresolved:
        insights.append(("Close evidence gaps before relying on the full picture",
            f"The registration position remains unconfirmed in {', '.join(unresolved)}. These states are excluded from conclusions about registration coverage or exemption eligibility until verification is complete."))
    if not insights:
        insights.append(("Keep the filing calendar aligned with the snapshot",
            "No cross-state pattern requiring an additional recommendation was identified in this snapshot. Use the state findings and prioritized action items to maintain the filing calendar and supporting evidence."))
    return insights


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
    page_count = 3 + (len(rows) + 7) // 8
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
    for number, (title, states, detail) in enumerate(action_items(rows), 1):
        story.extend([p(f"{number}. {title}", "h3"), p("; ".join(states), "small"), p(detail, "small"), Spacer(1, 5)])
    story.extend([PageBreak(), p("Operational Insights", "title"),
                  p("Patterns in the checked states, with practical follow-up. These observations do not create new state statuses or determine legal obligations.", "small"), Spacer(1, 10)])
    for title, detail in operational_insights(rows):
        story.extend([p(title, "h2"), p(detail), Spacer(1, 9)])
    story.extend([Spacer(1, 8), p("Basis and limits", "h3"), p(DISCLAIMER, "small"),
                  p("This report summarizes the completed snapshot; generating it does not refresh the registry evidence. Deadline priorities use each state's check date. Evidence excerpts are shortened; linked records and full snapshot comments provide supporting detail. Unchecked states are outside this report's scope.", "small")])
    for start in range(0, len(rows), 8):
        section = rows[start:start+8]
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
        # Keep source timing beside the affected findings, without a standalone section.
        notes = freshness(section)
        if notes:
            story.append(Spacer(1, 8))
            for state, when, source_date in notes:
                try:
                    downloaded = datetime.fromisoformat(when)
                    if downloaded.tzinfo is not None:
                        when = downloaded.astimezone(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
                except ValueError:
                    pass
                story.append(p(f"{state}: scheduled download {when}. State source date: {source_date}.", "small"))
            story.append(p("Downloads may lag registry changes. Confirm time-sensitive decisions directly with the state. These dates are from the snapshot.", "small"))
        for row in section:
            if row["state"] == "OK":
                cached = re.search(r"Certificate freshness note: reused the verified certificate retrieved (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC)", row["comments"] + " " + row["source_note"])
                if cached:
                    story.append(p(f"OK certificate: verified copy retrieved {cached.group(1)} and reused within 24 hours at lookup. Report generation does not refresh this evidence.", "small"))
        story.extend([Spacer(1, 12), p("Report template " + REPORT_VERSION + " | Snapshot version(s): " + ", ".join(sorted({r["app_version"] or "not supplied" for r in section})), "small")])
    doc.build(list(story), onFirstPage=page_frame, onLaterPages=page_frame)
    if doc.page != page_count:
        page_count = doc.page
        output = BytesIO()
        doc = SimpleDocTemplate(output, pagesize=(612, 792), leftMargin=42, rightMargin=42, topMargin=94, bottomMargin=53, title=f"CharityClarity - {org}", author="Compliance Express")
        doc.build(list(story), onFirstPage=page_frame, onLaterPages=page_frame)
    return output.getvalue()
