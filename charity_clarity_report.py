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

REPORT_VERSION = "1.3.3"
INSIGHT_VERSION = "2.0.0"
NAVY = colors.HexColor("#0B2A5B")
INK = colors.HexColor("#172B45")
MUTED = colors.HexColor("#536274")
PALE = colors.HexColor("#F3F6FA")
ASSETS = Path(__file__).resolve().parent / "report-assets"
LOW = {"Current", "Exempt"}
IL_COMBINED = "Not Registered / Non-Compliant"
NO_LISTING = {"Not Registered", IL_COMBINED}
MODERATE = {"Upcoming Filing", "Not Registered", IL_COMBINED, "Pending", "Closed / Withdrawn / Canceled"}
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
DISCLAIMER = ("CharityClarity Aurora provides preliminary results for diagnostic purposes only, not legal or tax advice. "
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
                             filed_period=filed_period(row) if row["status"] not in INCOMPLETE | NO_LISTING else None,
                             year_label=filing_year_label(row) if row["status"] not in INCOMPLETE | NO_LISTING else None))
    return findings


def summary_groups(findings):
    groups = [("Potentially overdue filings / lapses", OVERDUE), ("Suspended / revoked", RESTRICTED),
              ("Closed / withdrawn / canceled", CLOSED), ("No registration found", {"Not Registered"}),
              ("Not registered / non-compliant (Illinois)", {IL_COMBINED}),
              ("Pending", {"Pending"}), ("Upcoming filing", {"Upcoming Filing"}),
              ("Exempt", {"Exempt"}), ("Current", {"Current"}), ("Unresolved checks", INCOMPLETE)]
    return [(label, [f["state"] for f in findings if f["status"] in statuses]) for label, statuses in groups
            if any(f["status"] in statuses for f in findings)]


def verification_needed(row):
    status = row["status"]
    if status == IL_COMBINED:
        return "Illinois lists compliant charities. Confirm with Illinois whether the absent listing reflects non-registration or non-compliance, and obtain any registration or recent filing acknowledgment."
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
        ("Resolve the Illinois compliant-directory gap", states({IL_COMBINED}),
         "Confirm whether the absent Illinois listing reflects non-registration or non-compliance before choosing registration or remediation work."),
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
    footprint = by_status((LOW | MODERATE | HIGH) - NO_LISTING - CLOSED)
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
    if not isinstance(rows, list) or not 1 <= len(rows) <= len(supported_states):
        raise ValueError(f"Generate a report from 1 to {len(supported_states)} completed state results for one organization.")
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
        if status == IL_COMBINED and state != "IL":
            raise ValueError("The combined non-registration/non-compliance status is Illinois-only.")
        if row.get("success") is not None and not isinstance(row["success"], bool):
            raise ValueError("Snapshot success must retain its boolean meaning.")
        returned_status = status
        unsuccessful = row.get("success") is False
        if unsuccessful and status not in INCOMPLETE:
            status = "Unable to Confirm"
        checked = row.get("checked_at_epoch")
        registration_date = text(row.get("registration_date"), 10)
        registration_type = text(row.get("registration_date_type"), 50)
        if registration_date and (not re.fullmatch(r"\d{4}-\d{2}-\d{2}", registration_date)
                                  or not parse_date(registration_date)
                                  or registration_type not in {"initial_registration_date", "registry_registration_date", "initial_credential_issue_date", "initial_registration_filing_date"}):
            raise ValueError("Registration Date must preserve a valid state-supplied date and its meaning.")
        renewal_date = text(row.get("renewal_date"), 10)
        renewal_type = text(row.get("renewal_date_type"), 50)
        if renewal_date and (not re.fullmatch(r"\d{4}-\d{2}-\d{2}", renewal_date)
                             or not parse_date(renewal_date)
                             or renewal_type not in {"last_registration_date", "current_issue_date", "current_effective_date", "renewal_filing_date", "annual_registration_submitted_date", "last_renewal_date"}):
            raise ValueError("Last Renewal Date must preserve a valid state-supplied date and its meaning.")
        combined_value = text(row.get("renewal_filing_value"), 10)
        combined_type = text(row.get("renewal_filing_type"), 50)
        combined_label = text(row.get("renewal_filing_label"), 100)
        combined_note = text(row.get("renewal_filing_note"), 500)
        combined_url = text(row.get("renewal_filing_source_url"), 500)
        if combined_value:
            year_type = combined_type in {"filed_year", "filed_tax_year"}
            date_type = combined_type in {"filed_period_end", "last_registration_date", "current_issue_date", "current_effective_date", "renewal_filing_date", "annual_registration_submitted_date", "last_renewal_date"}
            valid_year = year_type and re.fullmatch(r"(?:19|20)\d{2}", combined_value) and int(combined_value) <= date.today().year
            valid_date = date_type and re.fullmatch(r"\d{4}-\d{2}-\d{2}", combined_value) and parse_date(combined_value) and parse_date(combined_value) <= date.today()
            if not combined_label or not (valid_year or valid_date):
                raise ValueError("Last Renewal / Filed Year must preserve its source value and meaning.")
        elif renewal_date:
            # Older completed snapshots remain exportable.
            combined_value, combined_type = renewal_date, renewal_type
            combined_label = text(row.get("renewal_date_source_label"), 100)
            combined_note = text(row.get("renewal_date_note"), 500)
            combined_url = text(row.get("renewal_date_source_url"), 500)
        else:
            combined_type = combined_label = combined_note = combined_url = ""
        if checked is not None:
            if isinstance(checked, bool) or not isinstance(checked, (int, float)) or not 0 < checked < 4102444800:
                raise ValueError("Invalid snapshot timestamp.")
        clean.append({
            **{k: text(row.get(k), 10000) for k in ("comments", "raw_status_text", "source_note")},
            **{k: text(row.get(k), 500) for k in ("source_url", "matched_registry_identifier", "app_version", "computed_due_date")},
            **{k: text(row.get(k), 500) for k in ("registration_date_source_label", "registration_date_source_url", "registration_date_note")},
            **{k: text(row.get(k), 500) for k in ("renewal_date_source_label", "renewal_date_source_url", "renewal_date_note")},
            "registration_date": registration_date, "registration_date_type": registration_type,
            "renewal_date": renewal_date, "renewal_date_type": renewal_type,
            "renewal_filing_value": combined_value, "renewal_filing_type": combined_type,
            "renewal_filing_label": combined_label, "renewal_filing_note": combined_note,
            "renewal_filing_source_url": combined_url,
            "organization_name": name, "ein": ein, "state": state, "status": status,
            "returned_status": returned_status, "unsuccessful": unsuccessful,
            "lookup_error": text(row.get("error"), 10000),
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


HEAD_START_STATES = set("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())
HEAD_START_FILINGS = {None, "none", "optional", "application", "annual", "simplified", "verify"}


def validate_head_start(value, identity=None):
    """Validate a user-supplied assessment snapshot, never certify its legal facts."""
    from copy import deepcopy
    import uuid
    if not isinstance(value, dict) or value.get("schema_version") != "cc.head-start/1":
        raise ValueError("Use a supported Head Start assessment file.")
    item = deepcopy(value)
    name = text(item.get("organization_name"), 250)
    ein = re.sub(r"\D", "", text(item.get("ein"), 20))
    if not name or len(ein) != 9 or ein == "000000000":
        raise ValueError("The Head Start assessment needs the organization name and EIN.")
    try:
        item["assessment_id"] = str(uuid.UUID(item.get("assessment_id", "")))
        assessed = datetime.fromisoformat(item.get("assessed_at", "").replace("Z", "+00:00"))
        if assessed.tzinfo is None:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ValueError("The Head Start assessment identifier or date is invalid.") from None
    if identity:
        normalized = lambda s: " ".join(s.split()).casefold()
        if ein != identity[1] or normalized(name) != normalized(identity[0]):
            raise ValueError("Head Start and Aurora must describe the same organization and EIN.")
    profile = item.get("profile")
    if not isinstance(profile, dict) or profile.get("taxStatus") != "recognized501c3":
        raise ValueError("Insight supports Head Start assessments for recognized 501(c)(3) nonprofits.")
    requirements = item.get("requirements")
    if not isinstance(requirements, list) or len(requirements) != 51:
        raise ValueError("The Head Start file must preserve all 50 states and DC.")
    seen = set()
    for r in requirements:
        if not isinstance(r, dict) or r.get("code") not in HEAD_START_STATES or r["code"] in seen:
            raise ValueError("The Head Start assessment has an invalid or duplicated state.")
        seen.add(r["code"])
        if r.get("status") not in {"required", "exemption", "none", "review", "outside"} or r.get("filing") not in HEAD_START_FILINGS:
            raise ValueError("The Head Start assessment has an unsupported finding or filing route.")
        for key in ("name", "why", "action"):
            if not isinstance(r.get(key), str) or len(r[key]) > 15000:
                raise ValueError("The Head Start assessment is missing its finding explanation.")
        for key in ("approvalRequired", "discretionaryRequest", "deferred", "nexusPending", "possible_exemption"):
            if key in r and not isinstance(r[key], bool):
                raise ValueError("The Head Start assessment has an invalid eligibility flag.")
        if r.get("exemption_evidence") not in {None, "answers"}:
            raise ValueError("The Head Start assessment has an invalid eligibility basis.")
        if r.get("exemption_evidence") == "answers" and (r["status"] not in {"none", "exemption"} or r.get("discretionaryRequest")):
            raise ValueError("Missing eligibility or a waiver request cannot be declared confirmed.")
        sources = r.get("sources", [])
        if not isinstance(sources, list) or len(sources) > 40 or any(not isinstance(s, dict) or not isinstance(s.get("url"), str) for s in sources):
            raise ValueError("The Head Start assessment has invalid source references.")
    item["organization_name"], item["ein"] = name, ein
    item["engine_version"] = text(item.get("engine_version"), 100)
    return item


def reconcile_head_start(rows, assessment):
    """Join requirements and completed evidence; do not change either input."""
    indexed = {r["state"]: r for r in rows}
    findings = []
    procedures = {"none": "No exemption filing indicated", "optional": "State confirmation optional", "application": "Submit an exemption claim", "annual": "Annual exemption filing", "simplified": "Annual small-charity paperwork", "verify": "Filing procedure to confirm"}
    for h in assessment["requirements"]:
        code, status = h["code"], h["status"]
        row = indexed.get(code)
        actual = row["status"] if row else "Not checked"
        outside = status == "outside" or h.get("deferred", False)
        supported = not outside and not h.get("discretionaryRequest") and h.get("exemption_evidence") == "answers"
        possible = not outside and (h.get("possible_exemption") or status == "exemption" or supported)
        requirement = "No reported connection" if outside else "Registration indicated" if status == "required" else "Eligibility supported" if supported else "Potential exemption" if possible else "No registration indicated" if status == "none" else "Requirement needs clarification"
        if supported:
            requirement += ": " + ("state approval needed" if h.get("approvalRequired") else procedures.get(h.get("filing"), "filing procedure to confirm"))
        priority, finding = 4, "No immediate action indicated"
        action = "Reassess if fundraising, donor gifts or operations change."
        why = "The supplied assessment does not identify a present filing task; this is not clearance for future activity."
        if actual in HIGH:
            priority, finding = 1, "Existing registration needs attention"
            action = verification_needed(row)
            why = "Aurora returned an adverse registration signal. Check acknowledgments, accepted extensions and the applicable period before deciding which correction is needed."
            if possible:
                action += " Review the exemption route separately; keep applicable filings current while relief is unresolved."
        elif actual in CLOSED:
            priority, finding = 2, "Closed registration needs review"
            action = "Confirm whether closure was intentional, whether activity continues, and whether an exemption or replacement registration applies."
            why = "A closed record is not a current registration and does not by itself establish that reinstatement is necessary."
        elif actual in INCOMPLETE:
            priority, finding = 2, "Registration status unresolved"
            action = "Resolve the registry access, identity or evidence issue shown in Aurora before treating this state as unregistered."
            why = "An incomplete or ambiguous search is not a negative registration result."
        elif actual == "Not checked" and not outside and (status in {"required", "review", "exemption"} or supported):
            priority, finding = 2, "Registration status not checked"
            action = "Check the existing registration or exemption record through Aurora where supported, otherwise with the state directly."
            why = "Head Start has a relevant finding, but no completed Aurora result was supplied for this state."
        elif status == "required" and not outside:
            if actual in NO_LISTING:
                priority, finding = 1, "Registration gap indicated"
                action = "Confirm no recent submission or applicable exemption explains the missing record, then complete registration if the requirement still applies."
                why = "The supplied Head Start facts indicate registration, and Aurora completed its search without finding a qualifying registration."
            elif actual == "Exempt":
                priority, finding = 2, "Requirement and recorded exemption differ"
                action = "Verify the exemption determination and whether it covers the same entity, activity and registration regime identified by Head Start."
                why = "A recorded exemption can have narrower scope than the registration or trust requirement in the assessment."
            elif actual == "Pending":
                priority, finding = 2, "Registration pending"
                action = "Confirm the pending submission and whether fundraising is authorized while the state reviews it."
                why = "Head Start indicates registration, but a pending record is not an approved current registration."
            else:
                finding, action, why = "Registration record found", "Confirm the record covers the requirement identified by Head Start; maintain applicable filings.", "Head Start indicates registration and Aurora returned a record. Confirm its entity, activity and registration regime before relying on it."
        elif h.get("discretionaryRequest"):
            priority, finding = 3, "Discretionary waiver opportunity"
            action = h["action"] + " Keep existing obligations current while the request is reviewed."
            why = "Head Start identifies a waiver-request route. Relief depends on the agency's decision, not the category or request alone."
        elif supported:
            if actual in {"Current", "Upcoming Filing", "Pending"}:
                priority, finding = 3, "Exemption opportunity"
                action = h["action"] + " Keep existing obligations current until the exemption procedure and its scope are established."
                why = "Your answers support an exemption route, while Aurora returned an existing registration or pending record. Review whether relief could reduce future filing work."
            elif actual == "Exempt":
                finding, action, why = "Exemption findings align", "Retain the determination and check its scope, continuing eligibility and any exemption paperwork.", "Head Start supports eligibility and Aurora reports an exemption; the determination still governs its actual scope."
            elif actual in NO_LISTING:
                if h.get("approvalRequired") or h.get("filing") in {"application", "annual", "simplified", "verify"}:
                    priority, finding = 2, "Exemption filing or approval to confirm"
                else:
                    finding = "Eligibility supports registration relief"
                action, why = h["action"], "The missing registration does not alone establish a gap when the supplied facts support relief. Verify the actual filing or approval procedure."
        elif possible:
            priority, finding = 3 if actual in {"Current", "Upcoming Filing", "Exempt"} else 2, "Exemption eligibility to confirm"
            action = "Answer the missing eligibility facts in Head Start, then review the applicable filing or approval procedure."
            why = "An organizational category or waiver possibility does not establish eligibility or state approval."
        elif actual in {"Current", "Upcoming Filing", "Pending", "Exempt"}:
            priority, finding = 3, "Review registration context"
            action = "Confirm ongoing state activity and the record's scope before changing existing registrations or filings."
            why = "Aurora returned a record, while the assessment does not establish a current registration task for the reported activity. Historical and separate obligations can still apply."
        elif not outside and status == "review":
            priority, finding = 2, "Registration requirement to clarify"
            action, why = h["action"], h["why"]
        if actual == "Upcoming Filing":
            priority = min(priority, 2)
            action += " Confirm and plan the upcoming filing or expiration shown in the workload forecast."
        if actual == "Pending":
            priority = min(priority, 2)
            action += " Confirm the pending submission's disposition; it is not an approved current registration."
        findings.append({"state": code, "name": h["name"], "requirement": requirement, "aurora_status": actual,
                         "finding": finding, "priority": priority, "action": action, "why": why,
                         "head_start": h, "aurora_row": row})
    return sorted(findings, key=lambda f: (f["priority"], f["name"]))


def executive_metrics(combined):
    """Count actionable findings, not hypothetical obligations or missing evidence."""
    definitions = [
        ("Potential exemption opportunities", "Eligibility and procedure to confirm", lambda f: f["finding"] in {"Exemption opportunity", "Exemption eligibility to confirm", "Discretionary waiver opportunity"}, False),
        ("Registration gaps indicated", "Requirement indicated; no record found", lambda f: f["finding"] == "Registration gap indicated", True),
        ("Potential withdrawal reviews", "Confirm activity before changing filings", lambda f: f["finding"] == "Review registration context" and f["aurora_status"] in {"Current", "Upcoming Filing"} and (f["head_start"]["status"] in {"outside", "none"} or f["head_start"].get("deferred")), False),
        ("Delinquencies", "Returned delinquent status needs follow-up", lambda f: f["aurora_status"] == "Delinquent", True),
        ("Upcoming filings", "Plan the returned filing or expiration", lambda f: f["aurora_status"] == "Upcoming Filing", False),
        ("Unresolved status checks", "Incomplete or relevant states not checked", lambda f: f["finding"] in {"Registration status unresolved", "Registration status not checked"}, False),
    ]
    return [{"label": label, "note": note, "states": [f["state"] for f in combined if include(f)], "urgent": urgent}
            for label, note, include, urgent in definitions]


def profile_summary(profile):
    """Display the real intake values, including normalized numeric strings."""
    from decimal import Decimal, InvalidOperation
    types = {"charity":"Public charity / community nonprofit", "religious":"House of worship / religious organization",
             "school":"Elementary or secondary school", "university":"College / university", "hospital":"Nonprofit hospital",
             "educationalFoundation":"Educational foundation", "hospitalFoundation":"Hospital foundation",
             "foundation":"Other institutional foundation", "privateFoundation":"Private foundation",
             "veterans":"Veterans organization", "membership":"Membership organization", "other":"Other nonprofit", "unknown":"Type to confirm"}
    value = profile.get("fiscalActual")
    amount = "Not supplied"
    try:
        if value is not None and value != "" and not isinstance(value, bool):
            number = Decimal(str(value).replace(",", "").removeprefix("$"))
            if number.is_finite() and number >= 0:
                amount = f"${number:,.2f}".removesuffix(".00")
    except (InvalidOperation, ValueError):
        pass
    online = {"public":"Public donation page", "selected":"Specific states", "nationwide":"Nationwide requests", "targeted":"Targeted online fundraising"}.get(profile.get("onlineReach"), "Online activity to confirm")
    if profile.get("online") == "no": online = "No online donation requests"
    elif profile.get("online") == "unknown": online = "Online activity to confirm"
    return types.get(profile.get("type"), "Type to confirm"), amount, online


def generate_report(payload, supported_states):
    from copy import deepcopy
    rows = validate_results(payload, set(supported_states))
    findings = report_findings(rows)
    groups = summary_groups(findings)
    risk, incomplete, counts = risk_summary(rows)
    org, ein = rows[0]["organization_name"], rows[0]["ein"]
    linked = validate_head_start(payload["head_start"], (org, re.sub(r"\D", "", ein))) if payload.get("head_start") is not None else None
    combined = reconcile_head_start(rows, linked) if linked else []
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
        "metric_number": ParagraphStyle("metric_number", fontName="Helvetica-Bold", fontSize=27, leading=30, textColor=NAVY, spaceAfter=4),
        "metric_urgent": ParagraphStyle("metric_urgent", fontName="Helvetica-Bold", fontSize=27, leading=30, textColor=colors.HexColor("#C62828"), spaceAfter=4),
        "metric_label": ParagraphStyle("metric_label", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=NAVY, spaceAfter=4),
        "metric_note": ParagraphStyle("metric_note", fontName="Helvetica", fontSize=7.5, leading=10, textColor=MUTED),
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

    def metric_cards(metrics):
        cells = [[p(len(m["states"]), "metric_urgent" if m["urgent"] and m["states"] else "metric_number"),
                  p(m["label"], "metric_label"), p(m["note"], "metric_note")] for m in metrics]
        grid = Table([cells[:3], cells[3:]], colWidths=[176]*3, hAlign="LEFT")
        grid.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (-1, -1), PALE),
            ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#DCE3EB")),
            ("INNERGRID", (0, 0), (-1, -1), 2, colors.white),
            ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
        ]))
        return KeepTogether([grid, Spacer(1, 6), p("Counts describe state findings and can overlap. Exemption and withdrawal opportunities require review; keep existing obligations current until the applicable procedure is confirmed.", "small")])

    checked = [r["checked_at_epoch"] for r in rows if r["checked_at_epoch"]]
    def stamp(epoch):
        return datetime.fromtimestamp(epoch, timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    period = stamp(min(checked)) if checked else "Check time not supplied"
    if checked and max(checked) != min(checked):
        period += " to " + stamp(max(checked))
    versions = ", ".join(sorted({r["app_version"] or "not supplied" for r in rows}))
    story = [p("CharityClarity Insight" if linked else "Charity registration snapshot", "title"), p(org, "h2"),
             p(f"EIN {ein}  |  {len(rows)} {'illustrative registry results' if payload.get('illustrative_example') else 'states checked'}", "small"), p(period, "small"), Spacer(1, 12),
             p("Executive summary", "h2"), p("The findings at a glance", "h3")]
    if linked:
        counts = Counter(f["priority"] for f in combined)
        story.insert(0, p("Illustrative example - fictional organization and registry results", "small")) if payload.get("illustrative_example") else None
        assessment_date = stamp(datetime.fromisoformat(linked['assessed_at'].replace('Z', '+00:00')).timestamp())
        finding_word = "finding" if counts[1] == 1 else "findings"
        story.extend([metric_cards(executive_metrics(combined)),
                      p(f"The combined assessment identifies {counts[1]} state {finding_word} to address first, {counts[2]} to clarify or plan next, and {counts[3]} opportunities or registration-context reviews. Findings with no present task remain in the state coverage table."),
                      p(f"Head Start: {assessment_date} | Aurora: {period}. The requirements assessment covers 50 states and DC; {len(rows)} registry results were supplied. Dates and coverage remain separate.", "small"),
                      p("Head Start eligibility is based on supplied organizational facts. It is not verified state approval. No reported activity is not a statutory clearance, and a missing or unchecked registry result is not proof of a violation.", "small")])
        profile = linked["profile"]
        type_label, amount, online_label = profile_summary(profile)
        story.append(p(f"Reported profile: {type_label}; principal office {profile.get('base', 'Not supplied')}; last completed fiscal-year contributions {amount}; online reach {online_label}. Other periods and definitions are preserved in the Head Start assessment.", "small"))
    story.append(table([["Finding", "Count", "States"]] + [[label, str(len(states)), ", ".join(states)] for label, states in groups], [236, 48, 244]))
    record_count = sum(f["status"] not in INCOMPLETE | NO_LISTING for f in findings)
    closed_count = sum(f["status"] in CLOSED for f in findings)
    missing_count = sum(f["status"] == "Not Registered" for f in findings)
    il_count = sum(f["status"] == IL_COMBINED for f in findings)
    il_coverage = f", {il_count} Illinois not-registered / non-compliant result" if il_count else ""
    story.extend([Spacer(1, 10), p(f"Coverage reconciles to {len(rows)} checked states: {record_count} record-based results (including {closed_count} closed), {missing_count} no-registration-found results{il_coverage}, and {incomplete} unresolved checks.", "small"),
                  p(f"{'Aurora status follow-up indicator' if linked else 'Follow-up risk indicator'}: {risk}", "h3"),
                  p("This uses the highest returned signal, not an average or a legal conclusion. High covers overdue, suspended, revoked, expired or failed-to-renew results. Moderate covers upcoming, pending, closed or no-record results. Low covers Current and Exempt. Incomplete checks cannot support an overall Low assessment.", "small"),
                  p('No registration found describes the completed registry search. Head Start supplies a separate requirements assessment; review recent submissions, exemption scope and actual activity before acting on an indicated gap.' if linked else 'In this report, "No registration found" is the presentation label for the snapshot status "Not Registered." Registration obligation remains Unknown until activity and applicable requirements are reviewed.', "small"),
                  p(DISCLAIMER, "small"), p("Generating this report does not refresh the registry evidence. " + ("Unchecked states have no verified Aurora status in this report." if linked else "Unchecked states are outside its scope."), "small")])
    action_start = len(story)
    story.extend([section_break(force=True), p("Prioritized action items", "title"), p("Assign an owner to each applicable item. The state findings preserve the evidence and qualifications needed to act.", "small")])
    for number, (title, states, detail) in enumerate(action_items(rows, findings), 1):
        story.extend([p(f"{number}. {title}", "h3"), p("; ".join(states), "small"), p(detail, "detail")])

    forecast_start = len(story)
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

    operational_start = len(story)
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

    coverage_start = len(story)
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

    if linked:
        key_story = [section_break(force=True), p("Key findings", "title"),
                     p("What the requirements and completed registry evidence mean together.", "small")]
        categories = {}
        for f in combined:
            if f["priority"] < 4:
                categories.setdefault(f["finding"], []).append(f["state"])
        key_story.append(table([["Finding", "States"]] + [[k, ", ".join(v)] for k, v in categories.items()], [260, 268]))
        if not categories:
            key_story.append(p("No immediate follow-up task is indicated by the supplied comparison. Continue maintaining established obligations."))
        plan = [section_break(force=True), p("Prioritized action items", "title"),
                p("Address first, then clarify upcoming obligations, then review opportunities. Assign an owner and retain the evidence that resolves each item.", "small")]
        for i, f in enumerate((f for f in combined if f["priority"] < 4), 1):
            priority_label = {1: "Address first", 2: "Plan or clarify next", 3: "Review opportunity or context"}[f["priority"]]
            plan.extend([CondPageBreak(110), p(f"{i}. {f['name']} - {f['finding']}", "h3"), p(priority_label, "small"),
                         labeled("Action:", f["action"]), labeled("Reason:", f["why"])])
        if not any(f["priority"] < 4 for f in combined):
            plan.append(p("Maintain current registrations and documented exemptions; reassess when facts change."))
        story = story[:action_start] + key_story + story[operational_start:coverage_start] + plan + story[forecast_start:operational_start]
        story.extend([section_break(force=True), p("Detailed state review", "title"),
                      p("All 50 states and DC are retained. Not checked is distinct from an incomplete search or no registration found.", "small"),
                      table([["State", "Head Start", "Aurora", "Insight"]] +
                            [[f["name"], f["requirement"], f["aurora_status"], f["finding"]] for f in combined], [80, 166, 112, 170])])
    story.extend([section_break(), p("State findings and evidence", "h2" if linked else "title"),
                  p("Each finding separates the returned evidence, CharityClarity Aurora's interpretation and the verification needed. Evidence may include filing information assembled by CharityClarity Aurora; it is not necessarily a status displayed on the public page. Comments and source notes are retained without excerpt truncation.", "small")])
    detail_findings = sorted(findings, key=lambda f: next(j["priority"] for j in combined if j["state"] == f["state"])) if linked else findings
    for f in detail_findings:
        row = f["row"]
        start = len(story)
        story.extend([CondPageBreak(155), p(f"{f['state']}  |  {f['label']}", "h2")])
        if linked:
            joined = next(j for j in combined if j["state"] == f["state"])
            h = joined["head_start"]
            story.extend([labeled("Head Start requirement:", joined["requirement"]), labeled("Basis:", h["why"]),
                          labeled("Insight recommendation:", joined["action"])])
            for source in h.get("sources", []):
                rule_url, _ = safe_source(source["url"])
                if rule_url:
                    story.append(p(f'<link href="{escape(rule_url, quote=True)}" color="#0B2A5B">Head Start rule source: {escape(source.get("title", "Official guidance"))}</link>', "small", markup=True))
        url, host = safe_source(row["source_url"])
        link = f'<link href="{escape(url, quote=True)}" color="#0B2A5B">Open {escape(row["state"])} registry</link>' if url else escape(host)
        if row["matched_registry_identifier"]:
            link += " | Record ID: " + escape(row["matched_registry_identifier"])
        story.append(p(link, "small", markup=True))
        date_cells = []
        for value, label, note in ((row["registration_date"], row["registration_date_source_label"], row["registration_date_note"]),
                                   (row["renewal_filing_value"], row["renewal_filing_label"], row["renewal_filing_note"])):
            content = ""
            if value:
                content = "<b>" + escape(value) + "</b><br/>" + escape(label)
                if note:
                    content += "<br/>" + escape(note)
            date_cells.append(p(content, "small", markup=True))
        dates_table = Table([[p("Initial Registration Date", "small"), p("Last Renewal / Filed Year", "small")], date_cells], colWidths=[252, 252])
        dates_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), PALE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        story.append(dates_table)
        story.append(labeled("Evidence returned with the check:", row["raw_status_text"] or "No separate registry excerpt supplied."))
        if row["unsuccessful"]:
            story.append(labeled("Lookup qualification:", "The snapshot marked this lookup unsuccessful. Its returned status was " + row["returned_status"] + "; it cannot establish registration or non-registration."))
            if row["lookup_error"]:
                story.append(labeled("Reported lookup issue:", row["lookup_error"]))
        if row["source_note"]:
            story.append(labeled("Evidence context:", row["source_note"]))
        story.append(labeled("CharityClarity Aurora interpretation:", row["comments"] or "No explanatory comment supplied with the returned status."))
        verification = verification_needed(row)
        if linked:
            verification = verification.replace("Registration obligation: Unknown. ", "Aurora alone does not establish the registration obligation. ")
        story.append(labeled("Verification needed:", verification))
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
        evidence_size = sum(len(row[k]) for k in ("comments", "raw_status_text", "source_note"))
        if linked:
            evidence_size += len(h["why"]) + len(joined["action"]) + sum(len(source.get("title", "Official guidance")) + 45 for source in h.get("sources", []))
        if evidence_size <= (2800 if linked else 3000):
            story[start:] = [KeepTogether(story[start + 1:])]
    if linked:
        for f in combined:
            if f["aurora_row"] is None and f["head_start"]["status"] != "outside" and not f["head_start"].get("deferred"):
                story.extend([CondPageBreak(100), p(f["name"] + " - registration status not checked", "h3"),
                              labeled("Head Start:", f["head_start"]["why"]), labeled("Next step:", f["action"])])
        story.append(p(f"Head Start assessment {linked['assessment_id']} | Engine {linked['engine_version']}. Supplied activity and eligibility facts must be reassessed when they change.", "small"))
    story.append(p("Report template " + (INSIGHT_VERSION if linked else REPORT_VERSION) + " | Snapshot version(s): " + versions, "small"))

    logo = ImageReader(str(ASSETS / "compliance-express.png"))
    brand = ImageReader(str(ASSETS / ("charityclarity.png" if linked else "charityclarity-aurora.png")))
    brand_width, brand_height = brand.getSize()
    page_count = 0
    def page_frame(canvas, document):
        canvas.saveState()
        canvas.drawImage(logo, 42, 747, width=150, height=36.15, mask="auto")
        canvas.drawImage(brand, 400, 731 if linked else 724, width=170, height=170 * brand_height / brand_width, mask="auto")
        if linked:
            canvas.setFillColor(NAVY)
            canvas.setFont("Helvetica-Bold", 10)
            canvas.drawRightString(570, 722, "Insight")
        canvas.setStrokeColor(colors.HexColor("#DCE3EB"))
        canvas.line(42, 719, 570, 719)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(42, 33, "www.compliance-express.com  |  info@compliance-express.com")
        if payload.get("illustrative_example"):
            canvas.drawString(42, 44, "Illustrative example - no registry checks performed")
        canvas.drawRightString(570, 33, f"CharityClarity {'Insight' if linked else 'Aurora'}  |  {document.page} / {page_count}")
        canvas.restoreState()
    # Two fresh layout passes preserve variable-length evidence and correct page totals.
    for _ in range(2):
        output = BytesIO()
        doc = SimpleDocTemplate(output, pagesize=(612, 792), leftMargin=42, rightMargin=42,
                                topMargin=94, bottomMargin=53, title=f"CharityClarity {'Insight' if linked else 'Aurora'} - {org}", author="Compliance Express")
        doc.build(deepcopy(story), onFirstPage=page_frame, onLaterPages=page_frame)
        if page_count:
            assert page_count == doc.page, "Report pagination changed between layout passes"
        page_count = doc.page
    return output.getvalue()
