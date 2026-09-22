"""Deterministic presentation of completed master-backend snapshots; no registry access."""
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from html import escape
from io import BytesIO
from pathlib import Path
import re
from urllib.parse import urlparse

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, CondPageBreak, KeepTogether

REPORT_VERSION = "1.3.0"
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
CLOSED = {"Closed / Withdrawn / Canceled"}
RESTRICTED = {"Suspended", "Revoked"}
OVERDUE = HIGH - RESTRICTED
CALENDAR = {"Current", "Upcoming Filing"} | OVERDUE
DATE_TOKEN = r"(\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})"
BUCKETS = ("Overdue", "0-30 days", "31-60 days", "61-90 days", "91-180 days", "Beyond 180 days", "Date unconfirmed")
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
    extension = re.findall(r"(?:extension (?:runs )?through|extension applies and uses|extension moves (?:that|the) deadline to|extended (?:due date|deadline)(?: is| of|:)?)[ ]+" + token, body, re.I)
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


def parse_date(value):
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(str(value or "").strip(), fmt).date()
        except ValueError:
            pass
    return None


def check_date(row):
    checked = row.get("checked_at_epoch")
    return datetime.fromtimestamp(checked, timezone.utc).date() if checked else None


def date_text(value):
    return value.strftime("%b %d, %Y") if value else "Not supplied"


def display_status(row):
    return "No registration found" if row["status"] == "Not Registered" else row["status"]


def deadline_details(row):
    """Describe dates already returned by the master; no state-rule calculations."""
    body = (row.get("comments") or "").split("Registry match:", 1)[0].split("Data freshness note:", 1)[0]
    base_match = re.search(r"base (?:due date|deadline)(?: is| of|:)?\s+" + DATE_TOKEN, body, re.I)
    base = parse_date(base_match.group(1)) if base_match else None
    effective = snapshot_due_date(row)
    extension = bool(re.search(r"extension (?:runs )?through|extension applies and uses|extension moves (?:that|the) deadline to|extended (?:due date|deadline)", body, re.I))
    if re.search(r"expiration|certificate expires|registrations? expire", body, re.I):
        kind = "Registration expiration"
    elif re.search(r"(?:filing|annual report|report due|renewal).*(?:due|deadline)|renewal date", body, re.I):
        kind = "Filing / renewal deadline"
    else:
        kind = "Date type unconfirmed"
    return dict(effective=effective, base=base, extended=effective if extension else None, kind=kind)


def filed_period(row):
    """Compare only explicitly filed fiscal periods, never a year label or next period."""
    body = (row.get("comments") or "").split("Registry match:", 1)[0].split("Data freshness note:", 1)[0]
    patterns = [
        r"latest (?:submitted Form PC covers the |filed )fiscal year (?:ending|ended)\s+",
        r"was submitted for the fiscal year ending\s+",
        r"latest (?:submitted |filed )?(?:annual report|filing)(?: covers| is for)?(?: the)? (?:fiscal year|period) (?:ending|ended)\s+",
    ]
    dates = set()
    for pattern in patterns:
        dates.update(parse_date(v) for v in re.findall(pattern + DATE_TOKEN, body, re.I))
    # This label describes an already-filed period; plain FYE and next-required FYE do not.
    dates.update(parse_date(v) for v in re.findall(r"\bFiled FYE:\s*" + DATE_TOKEN, row.get("raw_status_text") or "", re.I))
    dates.discard(None)
    return next(iter(dates)) if len(dates) == 1 else None


def filing_year_label(row):
    body = (row.get("comments") or "").split("Registry match:", 1)[0]
    patterns = [r"latest filing year identified is (\d{4})", r"shows (\d{4}) as the last filing year on record"]
    labels = {v for pattern in patterns for v in re.findall(pattern, body, re.I)}
    return next(iter(labels)) if len(labels) == 1 else None


def report_findings(rows):
    """One presentation model for counts, calendars, insights and state detail."""
    findings = []
    for row in rows:
        deadline = deadline_details(row)
        asof = check_date(row)
        days = (deadline["effective"] - asof).days if deadline["effective"] and asof else None
        eligible = row["status"] in CALENDAR
        bucket = None
        if eligible:
            bucket = "Date unconfirmed" if days is None else next((name for limit, name in [(-1, "Overdue"), (30, "0-30 days"), (60, "31-60 days"), (90, "61-90 days"), (180, "91-180 days")] if days <= limit), "Beyond 180 days")
        findings.append(dict(row=row, state=row["state"], status=row["status"], label=display_status(row),
                             obligation="Unknown", deadline=deadline, asof=asof, days=days, bucket=bucket,
                             filed_period=filed_period(row) if row["status"] not in INCOMPLETE | {"Not Registered"} else None,
                             year_label=filing_year_label(row) if row["status"] not in INCOMPLETE | {"Not Registered"} else None))
    return findings


def summary_groups(findings):
    groups = [("Potentially overdue filings / lapses", OVERDUE), ("Suspended / revoked", RESTRICTED),
              ("Closed / withdrawn / canceled", CLOSED), ("No registration found", {"Not Registered"}),
              ("Pending", {"Pending"}), ("Upcoming filing", {"Upcoming Filing"}),
              ("Exempt", {"Exempt"}), ("Current", {"Current"}), ("Unresolved checks", INCOMPLETE)]
    return [(label, [f["state"] for f in findings if f["status"] in statuses]) for label, statuses in groups
            if any(f["status"] in statuses for f in findings)]


def verification_needed(row):
    status = row["status"]
    if status in CLOSED:
        return "Confirm the closure date and reason, whether withdrawal was intentional, current solicitation activity, and any replacement registration or exemption. Reinstatement depends on those facts."
    if status in RESTRICTED:
        return "Confirm the restriction, its effective date, any later state action, and the conditions for restoring the registration before relying on it."
    if status in OVERDUE:
        return "Check for a later submission, an accepted extension, or processing delay. Reconcile the covered fiscal period and returned deadline before treating the finding as an unresolved lapse."
    if status == "Not Registered":
        return "Registration obligation: Unknown. Check verified former names/DBAs, any exemption determination, recent submission acknowledgment, and solicitation activity in this state."
    if status in INCOMPLETE:
        return "Complete the state check or obtain direct confirmation. This result cannot establish the absence of a registration."
    if status == "Pending":
        return "Review state communications for outstanding information, confirm receipt of submitted items, and contact the state for the next step. Pending does not establish approval."
    if status == "Exempt":
        return "Retain the exemption determination; confirm its basis, whether it covers registration, annual reporting or both, and any renewal conditions."
    return "Confirm the returned deadline and any stated extension conditions; retain the filing acknowledgment or registration evidence."


def action_items(rows, findings=None):
    """Prioritize follow-up without changing a returned state status."""
    findings = report_findings(rows) if findings is None else findings
    urgent = sorted((f for f in findings if f["status"] in {"Current", "Upcoming Filing"}
                     and f["days"] is not None and 0 <= f["days"] <= 60),
                    key=lambda f: (f["deadline"]["effective"], f["state"]))
    urgent_states = {f["state"] for f in urgent}
    states = lambda statuses: [f["state"] for f in findings if f["status"] in statuses]
    groups = [
        ("Confirm suspended or revoked records", states(RESTRICTED),
         "Confirm the restriction and any later state action; determine the steps needed before relying on the registration."),
        ("Reconcile potentially overdue filings", states(OVERDUE),
         "Locate filing acknowledgments and any accepted extension. Compare the covered fiscal period with other states, then determine whether this is a missed submission, processing delay or public-record gap."),
        ("Renewals due within 60 days", [f"{f['state']}: {date_text(f['deadline']['effective'])} ({'today' if f['days'] == 0 else str(f['days']) + ' days'})" for f in urgent],
         "Assign an owner and confirm the applicable filing deadline or registration expiration now. Keep any extension qualification with the calendar entry."),
        ("Review closed registrations", states(CLOSED),
         "Establish whether withdrawal was intentional, when and why the record closed, whether relevant activity continues, and whether a replacement or exemption exists. Do not assume reinstatement is necessary."),
        ("Complete unresolved checks", states(INCOMPLETE),
         "Retry or confirm directly with the registry. A failed or inconclusive search does not establish that the organization is unregistered."),
        ("Follow up on pending registrations", states({"Pending"}),
         "Review state emails, letters and portal messages for missing items. Contact the state if the application's next step is unclear."),
        ("Plan the next filing cycle", [f["state"] for f in findings if f["status"] == "Upcoming Filing" and f["state"] not in urgent_states],
         "Use the workload forecast to assign preparation dates and coordinate shared financial documents. Confirm dates marked unconfirmed directly with the state."),
        ("Resolve the no-record states", states({"Not Registered"}),
         "Review applicable registration or exemption requirements against actual solicitation activity. Work through the coverage review below; a missing record alone does not establish a filing obligation or violation."),
        ("Document exemption conditions", states({"Exempt"}),
         "Obtain the determination letters and establish their basis, scope and renewal conditions. Use that evidence to focus any review in other states."),
    ]
    if not any(s for _, s, _ in groups):
        groups.append(("Maintain current records", states({"Current"}),
                       "Retain supporting evidence and use the returned dates to maintain the renewal calendar."))
    return [(title, state_list, detail) for title, state_list, detail in groups if state_list]


def insight_records(findings):
    """Every recommendation states the observation, implication, limit and next step."""
    insights = []
    def add(title, observed, significance, unknown, action):
        insights.append(dict(title=title, observed=observed, significance=significance, unknown=unknown, action=action))
    by_status = lambda statuses: [f["state"] for f in findings if f["status"] in statuses]
    footprint = by_status((LOW | MODERATE | HIGH) - {"Not Registered"} - CLOSED)
    closed = by_status(CLOSED)
    missing = by_status({"Not Registered"})
    if len(footprint) > 15 and missing:
        add("Broad registration footprint: focus the coverage review",
            f"{len(footprint) + len(closed)} states returned record-based results: {len(footprint)} other records and {len(closed)} closed records. No registration was found in {', '.join(missing)}.",
            "The pattern suggests a broad registration footprint and makes the no-record states a focused review list.",
            "The snapshot does not establish solicitation activity or legal obligations in those states.",
            "Start with the coverage decision process below; document the reason each state does or does not require follow-up.")
    exempt = by_status({"Exempt"})
    if exempt:
        add("Use documented exemptions to target the next review",
            f"Exemption is recorded in {', '.join(exempt)}.",
            "The documented basis may help identify where a separate exemption review would be useful.",
            "An exemption in one state does not establish eligibility elsewhere. The organization's name is not evidence of eligibility; basis and scope are not established by this report.",
            (f"Obtain the determination letters and screen {', '.join(missing)} first. " if missing else "Obtain the determination letters before selecting additional states. ") +
            "Confirm the category, supporting facts, scope and procedure under each target state's official rules; keep existing filings current while a request is considered.")
    period_groups = {}
    for f in findings:
        period = f["filed_period"]
        if period:
            period_groups.setdefault((period.month, period.day), []).append(f)
    for comparable in period_groups.values():
        latest = max(f["filed_period"] for f in comparable)
        peers = [f["state"] for f in comparable if f["filed_period"] == latest]
        older = [f for f in comparable if f["filed_period"] < latest]
        if len(peers) >= 2 and older:
            add("Reconcile different filed fiscal periods",
                f"{', '.join(peers)} show a filed period ending {date_text(latest)}. " +
                "; ".join(f"{f['state']} shows {date_text(f['filed_period'])}" for f in older) + ".",
                "These explicit period ends share the same month and day, so the older filings warrant a focused comparison.",
                "Different state requirements, processing delays or later submissions may explain the difference; it does not establish a missing filing.",
                "Compare the filing receipts and requirements for the corresponding fiscal period in the flagged states.")
    year_only = [f for f in findings if f["year_label"] and not f["filed_period"]]
    dated = [f for f in findings if f["filed_period"]]
    if year_only and dated:
        add("Align year labels before comparing filing histories",
            "; ".join(f"{f['state']}: filing-year label {f['year_label']}" for f in year_only) +
            ". Explicit filed period ends are available in " + ", ".join(f["state"] for f in dated) + ".",
            "The year-only records need a period check before they can support a comparison across states.",
            "A tax-year label may refer to a fiscal year ending in the following calendar year. These are not confirmed filing-period outliers.",
            "Identify the actual fiscal period covered in the year-only records, then compare acknowledgments and any later submissions with the dated records below.")
    clusters = {}
    for f in findings:
        if f["bucket"] and f["days"] is not None and 0 <= f["days"] <= 180:
            clusters.setdefault(f["deadline"]["effective"], []).append(f)
    for deadline, group in sorted(clusters.items()):
        if len(group) < 2:
            continue
        add("Coordinate the " + date_text(deadline) + " deadline cluster",
            f"{len(group)} states share this returned date: {', '.join(f['state'] for f in group)}.",
            "Shared preparation can reduce repeated work and prevent a concentrated filing workload.",
            "The date may represent a filing deadline or an expiration; extension conditions and required materials may differ by state.",
            "Assign one coordinator, prepare common documents, and confirm each state's deadline type and qualification in the forecast and findings.")
    pending = by_status({"Pending"})
    if pending:
        add("Assign a follow-up for pending records", f"Pending results: {', '.join(pending)}.",
            "Outstanding information or processing may require follow-up.", "The snapshot does not establish approval or the next required response.",
            "Contact the state after checking portal messages, emails and submission acknowledgments; assign an owner to any requested response.")
    unresolved = by_status(INCOMPLETE)
    if unresolved:
        add("Complete the evidence gaps", f"Unresolved checks: {', '.join(unresolved)}.",
            "The report cannot establish the registration position in these states.", "An incomplete search is not a negative registration result.",
            "Retry the affected checks or confirm directly with the registry before drawing a coverage conclusion.")
    conflicts = [f["state"] for f in findings if f["status"] in {"Current", "Upcoming Filing"} and f["days"] is not None and f["days"] < 0]
    if conflicts:
        add("Reconcile a status and date discrepancy", f"{', '.join(conflicts)} returned Current or Upcoming Filing with a date before the check date.",
            "The calendar and status need reconciliation before use.", "The report preserves the snapshot status and does not determine which field should change.",
            "Confirm the effective deadline and any later filing or extension directly with the state.")
    if not insights:
        add("Maintain the evidence and filing calendar", "No additional cross-state pattern was established in the supplied results.",
            "The state findings remain the basis for follow-up.", "Unchecked states and later registry changes are outside the snapshot.",
            "Retain supporting records and confirm any returned dates before updating the filing calendar.")
    return insights


def operational_insights(rows):
    # Retain the existing helper contract for callers and control tests.
    return [(i["title"], " ".join(i[k] for k in ("observed", "significance", "unknown", "action")))
            for i in insight_records(report_findings(rows))]


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
        registration_date = text(row.get("registration_date"), 10)
        registration_type = text(row.get("registration_date_type"), 50)
        if registration_date and (not re.fullmatch(r"\d{4}-\d{2}-\d{2}", registration_date)
                                  or not parse_date(registration_date)
                                  or registration_type not in {"initial_registration_date", "registry_registration_date"}):
            raise ValueError("Registration Date must preserve a valid state-supplied date and its meaning.")
        if checked is not None:
            if isinstance(checked, bool) or not isinstance(checked, (int, float)) or not 0 < checked < 4102444800:
                raise ValueError("Invalid snapshot timestamp.")
        clean.append({
            **{k: text(row.get(k), 10000) for k in ("comments", "raw_status_text", "source_note")},
            **{k: text(row.get(k), 500) for k in ("source_url", "matched_registry_identifier", "app_version", "computed_due_date")},
            **{k: text(row.get(k), 500) for k in ("registration_date_source_label", "registration_date_source_url", "registration_date_note")},
            "registration_date": registration_date, "registration_date_type": registration_type,
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
    from copy import deepcopy
    rows = validate_results(payload, set(supported_states))
    findings = report_findings(rows)
    groups = summary_groups(findings)
    risk, incomplete, counts = risk_summary(rows)
    org, ein = rows[0]["organization_name"], rows[0]["ein"]
    ein = ein[:2] + "-" + ein[2:]
    styles = {
        "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=23, leading=28, textColor=NAVY, spaceAfter=12, keepWithNext=True),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=NAVY, spaceAfter=8, keepWithNext=True),
        "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=NAVY, spaceBefore=5, spaceAfter=5, keepWithNext=True),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=14, textColor=INK, spaceAfter=8),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8.5, leading=11.5, textColor=MUTED, spaceAfter=6),
        "detail": ParagraphStyle("detail", fontName="Helvetica", fontSize=9.2, leading=12.6, textColor=INK, spaceAfter=7),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, leading=11.5, textColor=INK),
        "head": ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=8.5, leading=11.5, textColor=colors.white),
    }

    def section_break(force=False):
        return PageBreak() if force and len(rows) > 8 else CondPageBreak(235)

    def p(value, style="body", markup=False):
        return Paragraph(value if markup else escape(str(value)), styles[style])

    def labeled(label, value, style="detail"):
        return p("<b>" + escape(label) + "</b> " + escape(str(value)), style, markup=True)

    def table(data, widths):
        grid = Table([[p(c, "head" if i == 0 else "cell") for c in row] for i, row in enumerate(data)],
                     colWidths=widths, hAlign="LEFT", repeatRows=1)
        grid.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("LINEBELOW", (0, 0), (-1, -1), .4, colors.HexColor("#DCE3EB")),
            ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ]))
        return grid

    checked = [r["checked_at_epoch"] for r in rows if r["checked_at_epoch"]]
    def stamp(epoch):
        return datetime.fromtimestamp(epoch, timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    period = stamp(min(checked)) if checked else "Check time not supplied"
    if checked and max(checked) != min(checked):
        period += " to " + stamp(max(checked))
    versions = ", ".join(sorted({r["app_version"] or "not supplied" for r in rows}))
    story = [p("Charity registration snapshot", "title"), p(org, "h2"),
             p(f"EIN {ein}  |  {len(rows)} states checked", "small"), p(period, "small"), Spacer(1, 12),
             p("Executive summary", "h2"), p("The findings at a glance", "h3")]
    story.append(table([["Finding", "Count", "States"]] + [[label, str(len(states)), ", ".join(states)] for label, states in groups], [236, 48, 244]))
    record_count = sum(f["status"] not in INCOMPLETE | {"Not Registered"} for f in findings)
    closed_count = sum(f["status"] in CLOSED for f in findings)
    missing_count = sum(f["status"] == "Not Registered" for f in findings)
    story.extend([Spacer(1, 10), p(f"Coverage reconciles to {len(rows)} checked states: {record_count} record-based results (including {closed_count} closed), {missing_count} no-registration-found results, and {incomplete} unresolved checks.", "small"),
                  p(f"Follow-up risk indicator: {risk}", "h3"),
                  p("This uses the highest returned signal, not an average or a legal conclusion. High covers overdue, suspended, revoked, expired or failed-to-renew results. Moderate covers upcoming, pending, closed or no-record results. Low covers Current and Exempt. Incomplete checks cannot support an overall Low assessment.", "small"),
                  p('In this report, "No registration found" is the presentation label for the snapshot status "Not Registered." Registration obligation remains Unknown until activity and applicable requirements are reviewed.', "small"),
                  p(DISCLAIMER, "small"), p("Generating this report does not refresh the registry evidence. Unchecked states are outside its scope.", "small")])
    story.extend([section_break(force=True), p("Prioritized action items", "title"), p("Assign an owner to each applicable item. The state findings preserve the evidence and qualifications needed to act.", "small")])
    for number, (title, states, detail) in enumerate(action_items(rows, findings), 1):
        story.extend([p(f"{number}. {title}", "h3"), p("; ".join(states), "small"), p(detail, "detail")])

    story.extend([section_break(force=True), p("Workload forecast", "title"),
                  p("Dates are copied from the completed snapshot, not independently revalidated. Day counts use each state's check date. The preparation target is a planning suggestion: 30 days before the returned date, or the check date when already inside that window. It is not an additional filing deadline.", "small")])
    calendar = [f for f in findings if f["bucket"]]
    if calendar:
        forecast = [["Window", "States", "Returned date / type", "Days", "Preparation target"]]
        for bucket in BUCKETS:
            grouped = {}
            for f in calendar:
                if f["bucket"] == bucket:
                    d = f["deadline"]
                    grouped.setdefault((d["effective"], d["kind"], f["days"], f["asof"]), []).append(f["state"])
            for (due, kind, days, asof), state_list in sorted(grouped.items(), key=lambda item: (item[0][0] or date.max, item[1])):
                target = max(asof, due - timedelta(days=30)) if asof and due else None
                forecast.append([bucket, ", ".join(state_list), date_text(due) + " / " + kind,
                                 "Unknown" if days is None else (str(abs(days)) + " overdue" if days < 0 else str(days)),
                                 date_text(target) if target else "Confirm date / check time"])
        story.append(table(forecast, [65, 73, 165, 61, 164]))
        bucket_counts = Counter(f["bucket"] for f in calendar)
        story.extend([Spacer(1, 10), p("Calendar coverage: " + "; ".join(f"{b}: {bucket_counts[b]}" for b in BUCKETS) + f". Total: {len(calendar)} states.", "small")])
    else:
        story.append(p("No filing or renewal calendar can be established from these returned statuses."))
    excluded = [f["state"] for f in findings if not f["bucket"]]
    if excluded:
        story.append(p(f"No renewal assigned to {', '.join(excluded)} ({len(excluded)} states). Exempt, closed, restricted, pending, no-record and unresolved results require their own follow-up before assigning a routine renewal.", "small"))
    extensions = [f for f in calendar if f["deadline"]["base"] or f["deadline"]["extended"]]
    if extensions:
        story.extend([p("Base and extended dates", "h3"), table([["State", "Base date", "Effective extended date"]] +
                     [[f["state"], date_text(f["deadline"]["base"]), date_text(f["deadline"]["extended"])] for f in extensions], [64, 232, 232]),
                     p("The forecast uses the returned effective date. Extension eligibility and any inferred dates remain qualified in the state findings; report generation does not establish eligibility.", "small")])

    story.extend([section_break(), p("Operational Insights", "title"),
                  p("Patterns in the checked states, with the evidence limits and a specific next step.", "small")])
    for insight in insight_records(findings):
        story.extend([CondPageBreak(155), p(insight["title"], "h2"), labeled("Observed:", insight["observed"]),
                      labeled("Why it matters:", insight["significance"]), labeled("Still unknown:", insight["unknown"]),
                      labeled("Next step:", insight["action"]), Spacer(1, 9)])
    periods = [f for f in findings if f["filed_period"] or f["year_label"]]
    if periods:
        story.extend([CondPageBreak(135), p("Filing-period comparison", "h2"),
                      table([["States", "Latest filed period / label", "Comparison basis"]] +
                            [[f["state"], date_text(f["filed_period"]) if f["filed_period"] else "Year label " + f["year_label"],
                              "Explicit filed fiscal period end" if f["filed_period"] else "Period unconfirmed; not an outlier finding"] for f in periods], [60, 220, 248]),
                      p("Only explicit filed period ends with the same month and day are aligned. A next-required period, submission date or tax-year label is not substituted for the latest filed period. Other states did not return a usable period for this comparison.", "small")])

    missing = [f["state"] for f in findings if f["status"] == "Not Registered"]
    exempt = [f["state"] for f in findings if f["status"] == "Exempt"]
    if missing or exempt:
        story.extend([section_break(), p("Coverage and exemption review", "title")])
    if missing:
        story.extend([p("No registration found: " + ", ".join(missing), "h2"),
                      labeled("Registration obligation assessment:", "Unknown in these states. The search outcome alone does not determine whether registration is required."),
                      p("Use the existing results and your records first. Answer only the questions that remain unresolved.", "small")])
        process = [
            ("1. Verify identity", "If prior names or DBAs are not documented, identify them and compare the EIN and known names with the registry. The absence of search details in this report does not mean a fallback search was skipped."),
            ("2. Check exemption evidence", "If there is no determination on file, establish the relevant organizational facts and check any separate exemption record. Confirm the exemption's scope and whether an application or acknowledgment is required."),
            ("3. Check submissions and timing", "If a filing was recently sent, locate its acknowledgment, submission date and state communications. Downloaded public data may lag an accepted or pending filing."),
            ("4. Assess the activity", "If no registration or exemption explains the result, compare actual solicitation activity with the state's official requirements. Record the rule source and facts supporting the conclusion."),
            ("5. Resolve any remaining gap", "A possible registration gap warrants action only after the identity, exemption, submission and activity questions are resolved. Assign a responsible person and document the next step."),
        ]
        for title, detail in process:
            story.extend([p(title, "h3"), p(detail, "detail")])
    if exempt:
        story.extend([CondPageBreak(170), p("Targeted exemption review", "h2"),
                      p("Start with the documented determinations in " + ", ".join(exempt) + ". " +
                        ("Then screen the no-record states " + ", ".join(missing) + "." if missing else "Select additional states only after the exemption basis and relevant activity are known."), "detail"),
                      table([["Review field", "Evidence or next information needed"],
                             ["Recorded exemption states", ", ".join(exempt)],
                             ["Category and supporting facts", "Not established by this snapshot. Obtain the determination letters and supporting organizational evidence; do not infer eligibility from the name."],
                             ["Scope", "Confirm registration, annual reporting, or both, including any continuing conditions."],
                             ["Target-state procedure", "Not assessed. Check application, acknowledgment and renewal requirements after identifying a potentially applicable category."],
                             ["Official rule source", "Not supplied for an eligibility assessment. Use the target state's official exemption guidance; the registry links in the findings are evidence links, not a completed legal rules review."]], [150, 378]),
                      p("Keep existing registrations and required filings current while exemption eligibility or a request is being reviewed.", "small")])

    story.extend([section_break(), p("State findings and evidence", "title"),
                  p("Each finding separates the returned evidence, CharityClarity's interpretation and the verification needed. Evidence may include filing information assembled by CharityClarity; it is not necessarily a status displayed on the public page. Comments and source notes are retained without excerpt truncation.", "small")])
    for f in findings:
        row = f["row"]
        start = len(story)
        story.extend([CondPageBreak(155), p(f"{f['state']}  |  {f['label']}", "h2")])
        url, host = safe_source(row["source_url"])
        link = f'<link href="{escape(url, quote=True)}" color="#0B2A5B">Open {escape(row["state"])} registry</link>' if url else escape(host)
        if row["matched_registry_identifier"]:
            link += " | Record ID: " + escape(row["matched_registry_identifier"])
        story.append(p(link, "small", markup=True))
        registration_text = row["registration_date"] or "Unavailable"
        if row["registration_date"]:
            registration_text += " | " + (row["registration_date_source_label"] or "Registration Date")
        registration_text += ". " + (row["registration_date_note"] or "No confirmed registration date was supplied; no renewal, filing or expiration date was substituted.")
        story.append(labeled("Registration Date:", registration_text))
        story.append(labeled("Evidence returned with the check:", row["raw_status_text"] or "No separate registry excerpt supplied."))
        if row["source_note"]:
            story.append(labeled("Evidence context:", row["source_note"]))
        story.append(labeled("CharityClarity interpretation:", row["comments"] or "No explanatory comment supplied with the returned status."))
        story.append(labeled("Verification needed:", verification_needed(row)))
        for state, when, source_date in freshness([row]):
            try:
                downloaded = datetime.fromisoformat(when)
                if downloaded.tzinfo is not None:
                    when = downloaded.astimezone(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
            except ValueError:
                pass
            story.append(p(f"{state}: scheduled download {when}. State source date: {source_date}. Confirm time-sensitive decisions directly with the state. These dates are from the snapshot.", "small"))
        if row["state"] == "OK":
            cached = re.search(r"Certificate freshness note: reused the verified certificate retrieved (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC)", row["comments"] + " " + row["source_note"])
            if cached:
                story.append(p(f"OK certificate: verified copy retrieved {cached.group(1)} and reused within 24 hours at lookup. Report generation does not refresh this evidence.", "small"))
        story.append(Spacer(1, 12))
        # Normal findings stay together so a qualification is not stranded on the
        # next page. Unusually long source fields remain splittable and complete.
        if sum(len(row[k]) for k in ("comments", "raw_status_text", "source_note")) <= 3000:
            story[start:] = [KeepTogether(story[start + 1:])]
    story.append(p("Report template " + REPORT_VERSION + " | Snapshot version(s): " + versions, "small"))

    logo = ImageReader(str(ASSETS / "compliance-express.png"))
    brand = ImageReader(str(ASSETS / "charityclarity.png"))
    page_count = 0
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
    # Two fresh layout passes preserve variable-length evidence and correct page totals.
    for _ in range(2):
        output = BytesIO()
        doc = SimpleDocTemplate(output, pagesize=(612, 792), leftMargin=42, rightMargin=42,
                                topMargin=94, bottomMargin=53, title=f"CharityClarity - {org}", author="Compliance Express")
        doc.build(deepcopy(story), onFirstPage=page_frame, onLaterPages=page_frame)
        if page_count:
            assert page_count == doc.page, "Report pagination changed between layout passes"
        page_count = doc.page
    return output.getvalue()
