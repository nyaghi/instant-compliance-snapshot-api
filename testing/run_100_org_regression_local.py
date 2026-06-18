#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import multiprocessing as mp
import random
import re
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

import registry_snapshot_server as cc

ARTIFACTS_DIR = BASE_DIR / "artifacts"
NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
SUPPORTED_STATUS_DATE_MOVEMENT = {"current", "upcoming filing", "delinquent"}
CONSERVATIVE_STATUSES = {"unable to verify", "unable to confirm", "needs review", "site not reachable"}
ACCEPTED_SOURCE_CATEGORIES = {"fixture_expected_wrong", "source_truth_verified", "not_locally_verifiable"}


def run_org_lookup_worker(name: str, ein: str, states: list[str], queue) -> None:
    cc.BATCH_FANOUT_SINGLE_STATE_LOOKUPS = False
    cc.BATCH_FANOUT_API_URLS = []
    try:
        results = cc.run_state_lookups_parallel([{"organization_name": name, "ein": ein}], states)
        queue.put({"ok": True, "results": results})
    except Exception as exc:
        queue.put({"ok": False, "error": str(exc)})


def normalize_status(value: str) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip().lower()
    aliases = {
        "": "",
        "nan": "",
        "n/a": "",
        "na": "",
        "not found": "not registered",
        "no record": "not registered",
        "closed/withdrawn/canceled": "closed / withdrawn / canceled",
        "closed / withdrawn / canceled": "closed / withdrawn / canceled",
        "closed": "closed / withdrawn / canceled",
        "withdrawn": "closed / withdrawn / canceled",
        "canceled": "closed / withdrawn / canceled",
        "cancelled": "closed / withdrawn / canceled",
        "unable to confirm": "unable to verify",
    }
    return aliases.get(value, value)


def status_is_skip(value: str) -> bool:
    return normalize_status(value) in {"", "n/a", "na"}


def col_to_index(ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", ref.upper())
    value = 0
    for ch in letters:
        value = value * 26 + (ord(ch) - ord("A") + 1)
    return max(0, value - 1)


def xlsx_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    values = []
    for si in root.findall("a:si", NS):
        pieces = [node.text or "" for node in si.findall(".//a:t", NS)]
        values.append("".join(pieces))
    return values


def workbook_first_sheet_path(zf: zipfile.ZipFile) -> str:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    first_sheet = workbook.find("a:sheets/a:sheet", NS)
    if first_sheet is None:
        return "xl/worksheets/sheet1.xml"
    rel_id = first_sheet.attrib.get(f"{{{NS['r']}}}id")
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    for rel in rels:
        if rel.attrib.get("Id") == rel_id:
            target = rel.attrib.get("Target", "worksheets/sheet1.xml")
            return "xl/" + target.lstrip("/")
    return "xl/worksheets/sheet1.xml"


def cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t", "")
    value_node = cell.find("a:v", NS)
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//a:t", NS)).strip()
    if value_node is None:
        return ""
    raw = value_node.text or ""
    if cell_type == "s":
        try:
            return shared_strings[int(raw)].strip()
        except Exception:
            return ""
    return raw.strip()


def read_xlsx_rows(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path) as zf:
        shared = xlsx_shared_strings(zf)
        sheet_path = workbook_first_sheet_path(zf)
        root = ET.fromstring(zf.read(sheet_path))
        rows = []
        for row_node in root.findall(".//a:sheetData/a:row", NS):
            values: list[str] = []
            for cell in row_node.findall("a:c", NS):
                ref = cell.attrib.get("r", "")
                index = col_to_index(ref)
                while len(values) <= index:
                    values.append("")
                values[index] = cell_value(cell, shared)
            rows.append(values)
        return rows


def read_workbook_cases(path: Path) -> tuple[list[dict], list[str]]:
    rows = read_xlsx_rows(path)
    if not rows:
        raise ValueError(f"No rows found in {path}")
    headers = [str(value or "").strip() for value in rows[0]]
    state_columns = [
        header.upper()
        for header in headers
        if re.fullmatch(r"[A-Z]{2}", header or "") and header.upper() in set(cc.SUPPORTED_STATES)
    ]
    org_idx = next((i for i, h in enumerate(headers) if h.lower() in {"organization name", "organization_name", "org name", "org_name", "name"}), None)
    ein_idx = next((i for i, h in enumerate(headers) if h.lower() == "ein"), None)
    if org_idx is None or ein_idx is None:
        raise ValueError(f"Could not find organization/ein headers in {path}")
    cases = []
    for row in rows[1:]:
        org = row[org_idx].strip() if org_idx < len(row) else ""
        ein = re.sub(r"\D", "", row[ein_idx] if ein_idx < len(row) else "")
        if not org or len(ein) < 7:
            continue
        expected = {}
        for state in state_columns:
            idx = headers.index(state)
            expected[state] = row[idx].strip() if idx < len(row) else ""
        cases.append({"organization_name": org, "ein": ein, "expected": expected})
    return cases, state_columns


def comparison_category(expected: str, actual: str, result: dict) -> str:
    expected_norm = normalize_status(expected)
    actual_norm = normalize_status(actual)
    text = " ".join([
        actual or "",
        result.get("runner_error") or "",
        result.get("reason_code") or "",
        result.get("runner_reason_code") or "",
        result.get("comments") or "",
        result.get("raw_status_text") or "",
    ])
    if expected_norm == actual_norm:
        return "match"
    if re.search(r"timeout|RUNNER_TIMEOUT", text, re.I):
        return "Bulk artifact / timeout"
    if actual_norm in CONSERVATIVE_STATUSES:
        return "Conservative result replacing unsafe result"
    if expected_norm in SUPPORTED_STATUS_DATE_MOVEMENT and actual_norm in SUPPORTED_STATUS_DATE_MOVEMENT:
        return "Natural date movement between Current / Upcoming Filing / Delinquent"
    if expected_norm == "not registered" and actual_norm not in {"not registered", *CONSERVATIVE_STATUSES}:
        return "Unsafe false positive"
    if expected_norm != "not registered" and actual_norm == "not registered":
        return "Unsafe false negative"
    if re.search(r"source evidence|official .*export|downloadable registry snapshot|exact-name record", text, re.I):
        return "Registry/source data changed or expected spreadsheet issue"
    return "Needs manual review"


def compact(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict, tuple)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return str(value)


def comment_quality_issues(result: dict) -> list[str]:
    issues = []
    status = result.get("status") or ""
    comment = result.get("comments") or ""
    if not comment.strip():
        issues.append("missing_comment")
        return issues
    if re.search(r"[A-Z]:\\\\|Traceback|stack trace|source_attempts|debug_trace|runner_reason_code|source_confidence|identity_confidence|\\{\\}|\\[\\]", comment, re.I):
        issues.append("debug_or_internal_noise")
    due = result.get("computed_due_date") or ""
    due_variants = {due}
    if due:
        parsed_due = cc.parse_due_date(due)
        if parsed_due:
            due_variants.add(cc.format_date(parsed_due))
            due_variants.add(parsed_due.strftime("%m/%d/%Y"))
            due_variants.add(f"{parsed_due.month}/{parsed_due.day}/{parsed_due.year}")
    if due and not any(candidate and candidate in comment for candidate in due_variants):
        issues.append("missing_due_date_rationale")
    if result.get("last_year_on_record") and not re.search(r"year|period|filing|fiscal", comment, re.I):
        issues.append("missing_period_rationale")
    match_name = result.get("matched_registry_name") or ""
    if normalize_status(status) not in {"not registered", "site not reachable", "unable to verify"} and match_name and "Registry match" not in comment:
        issues.append("missing_registry_match")
    m = re.search(r"status\s+is\s+([A-Za-z /]+?)(?:\.|$)", comment, re.I)
    if m:
        stated = normalize_status(m.group(1))
        if stated and stated != normalize_status(status):
            issues.append("comment_status_contradiction")
    return issues


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx", required=True)
    parser.add_argument("--label", default="local_100_xlsx")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--sample", type=int, default=0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--org-timeout", type=float, default=0.0)
    args = parser.parse_args()

    # This validation is intentionally local. Do not proxy to staging lanes.
    cc.BATCH_FANOUT_SINGLE_STATE_LOOKUPS = False
    cc.BATCH_FANOUT_API_URLS = []

    source_path = Path(args.xlsx)
    cases, states = read_workbook_cases(source_path)
    cases = [
        case for case in cases
        if any(not status_is_skip(case["expected"].get(state, "")) for state in states)
    ]
    if args.sample:
        rng = random.Random(args.seed or None)
        cases = rng.sample(cases, min(args.sample, len(cases)))
    if args.limit:
        cases = cases[: args.limit]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = ARTIFACTS_DIR / f"{args.label}_{stamp}"
    report_dir.mkdir(parents=True, exist_ok=True)
    log_path = report_dir / "run.log"
    raw_results = []
    comparison_rows = []
    difference_rows = []
    comment_rows = []
    started_all = time.perf_counter()

    def log(message: str) -> None:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    log(f"START workbook={source_path} orgs={len(cases)} states={len(states)} version={cc.APP_VERSION}")
    for org_index, case in enumerate(cases, start=1):
        org_start = time.perf_counter()
        name = case["organization_name"]
        ein = case["ein"]
        log(f"{args.label} {org_index}/{len(cases)}: running {ein} {name}")
        try:
            if args.org_timeout:
                queue = mp.Queue()
                proc = mp.Process(target=run_org_lookup_worker, args=(name, ein, states, queue))
                proc.start()
                proc.join(args.org_timeout)
                if proc.is_alive():
                    proc.terminate()
                    proc.join(5)
                    raise TimeoutError(f"Local regression org batch exceeded {args.org_timeout:.0f}s")
                try:
                    payload = queue.get_nowait()
                except Exception:
                    payload = {"ok": False, "error": "Local regression org worker exited without a result payload"}
                if not payload.get("ok"):
                    raise RuntimeError(payload.get("error") or "Local regression org worker failed")
                results = payload.get("results") or []
            else:
                results = cc.run_state_lookups_parallel([{"organization_name": name, "ein": ein}], states)
        except Exception as exc:
            log(f"{args.label} {org_index}/{len(cases)}: batch exception {exc}")
            results = []
            for state in states:
                results.append({
                    "organization_name": name,
                    "ein": ein,
                    "state": state,
                    "status": "Runner Timeout",
                    "runner_error": str(exc),
                    "comments": "The local regression runner could not complete this state lookup within the bounded org budget.",
                })
        batch_seconds = round(time.perf_counter() - org_start, 2)
        for result in results:
            state = (result.get("state") or "").upper()
            expected = case["expected"].get(state, "")
            actual = result.get("status") or ""
            skipped = status_is_skip(expected)
            match = (not skipped) and normalize_status(expected) == normalize_status(actual)
            category = "skipped" if skipped else comparison_category(expected, actual, result)
            row = {
                "organization_name": name,
                "ein": ein,
                "state": state,
                "expected": expected,
                "actual": actual,
                "comparison": "SKIP" if skipped else ("MATCH" if match else "DIFFERENCE"),
                "likely_category": category,
                "app_version": result.get("app_version") or cc.APP_VERSION,
                "matched_registry_name": result.get("matched_registry_name") or "",
                "matched_registry_identifier": result.get("matched_registry_identifier") or "",
                "raw_status_text": result.get("raw_status_text") or "",
                "comments": result.get("comments") or "",
                "lookup_seconds": result.get("lookup_seconds") or "",
                "state_wall_seconds": result.get("state_wall_seconds") or result.get("lookup_seconds") or "",
                "batch_seconds": batch_seconds,
                "runner_error": result.get("runner_error") or result.get("error") or "",
                "runner_recovery": result.get("runner_recovery") or "",
                "reason_code": result.get("reason_code") or "",
                "runner_reason_code": result.get("runner_reason_code") or "",
                "source_confidence": result.get("source_confidence") or "",
                "status_reason": result.get("status_reason") or "",
                "last_year_on_record": result.get("last_year_on_record") or "",
                "fiscal_year_end": result.get("fiscal_year_end") or "",
                "next_required_period": result.get("next_required_period") or "",
                "computed_due_date": result.get("computed_due_date") or "",
            }
            raw_results.append({**result, "expected": expected, "batch_seconds": batch_seconds})
            comparison_rows.append(row)
            if row["comparison"] == "DIFFERENCE":
                difference_rows.append(row)
            issues = comment_quality_issues(result)
            if issues:
                comment_rows.append({
                    **row,
                    "comment_issue": ";".join(issues),
                })
        if org_index % 5 == 0 or org_index == len(cases):
            write_csv(report_dir / "comparison_results_partial.csv", comparison_rows, COMPARISON_FIELDS)
            (report_dir / "raw_results_partial.json").write_text(json.dumps(raw_results, indent=2, ensure_ascii=True), encoding="utf-8")
        log(f"{args.label} {org_index}/{len(cases)}: finished {ein}; seconds={batch_seconds}; differences={sum(1 for r in comparison_rows[-len(states):] if r['comparison'] == 'DIFFERENCE')}")

    total_seconds = round(time.perf_counter() - started_all, 2)
    write_csv(report_dir / "comparison_results.csv", comparison_rows, COMPARISON_FIELDS)
    write_csv(report_dir / "differences_categorized.csv", difference_rows, COMPARISON_FIELDS)
    write_csv(report_dir / "full_difference_table_requested_columns.csv", difference_rows, COMPARISON_FIELDS)
    write_csv(report_dir / "comments_quality_issues.csv", comment_rows, COMMENT_FIELDS)
    (report_dir / "raw_results.json").write_text(json.dumps(raw_results, indent=2, ensure_ascii=True), encoding="utf-8")

    non_skipped = [row for row in comparison_rows if row["comparison"] != "SKIP"]
    summary = {
        "report_dir": str(report_dir),
        "source_workbook": str(source_path),
        "app_version": cc.APP_VERSION,
        "total_orgs": len(cases),
        "total_state_checks": len(non_skipped),
        "pass_count": sum(1 for row in non_skipped if row["comparison"] == "MATCH"),
        "fail_count": sum(1 for row in non_skipped if row["comparison"] == "DIFFERENCE"),
        "skip_count": sum(1 for row in comparison_rows if row["comparison"] == "SKIP"),
        "not_locally_verifiable_count": sum(1 for row in comparison_rows if row["likely_category"] == "not_locally_verifiable"),
        "source_truth_verified_count": sum(1 for row in comparison_rows if row["likely_category"] == "source_truth_verified"),
        "fixture_expected_wrong_count": sum(1 for row in comparison_rows if row["likely_category"] == "fixture_expected_wrong"),
        "unsafe_false_positives": sum(1 for row in difference_rows if row["likely_category"] == "Unsafe false positive"),
        "unsafe_false_negatives": sum(1 for row in difference_rows if row["likely_category"] == "Unsafe false negative"),
        "unable_to_verify_count": sum(1 for row in comparison_rows if normalize_status(row["actual"]) == "unable to verify"),
        "timeout_count": sum(1 for row in comparison_rows if re.search(r"timeout|RUNNER_TIMEOUT", " ".join([row["actual"], row["runner_error"], row["reason_code"], row["runner_reason_code"]]), re.I)),
        "site_not_reachable_count": sum(1 for row in comparison_rows if normalize_status(row["actual"]) == "site not reachable"),
        "needs_review_count": sum(1 for row in comparison_rows if normalize_status(row["actual"]) == "needs review"),
        "per_state_differences": dict(Counter(row["state"] for row in difference_rows)),
        "status_distribution": dict(Counter(row["actual"] for row in comparison_rows)),
        "top_failure_categories": dict(Counter(row["likely_category"] for row in difference_rows).most_common()),
        "source_fixture_stale_or_contradicted_count": sum(1 for row in difference_rows if row["likely_category"] == "Registry/source data changed or expected spreadsheet issue"),
        "comment_issue_count": len(comment_rows),
        "comment_issue_breakdown": dict(Counter(issue for row in comment_rows for issue in row["comment_issue"].split(";") if issue)),
        "max_state_wall_seconds": max([float(row["state_wall_seconds"] or 0) for row in comparison_rows] or [0]),
        "max_batch_seconds": max([float(row["batch_seconds"] or 0) for row in comparison_rows] or [0]),
        "total_seconds": total_seconds,
        "comparison_results_csv": str(report_dir / "comparison_results.csv"),
        "differences_categorized_csv": str(report_dir / "differences_categorized.csv"),
        "comments_quality_issues_csv": str(report_dir / "comments_quality_issues.csv"),
    }
    (report_dir / "summary_aggregated.json").write_text(json.dumps(summary, indent=2, ensure_ascii=True), encoding="utf-8")
    (report_dir / "done.json").write_text(json.dumps(summary, indent=2, ensure_ascii=True), encoding="utf-8")
    log(
        "DONE "
        f"report_dir={report_dir} total={summary['total_state_checks']} matches={summary['pass_count']} "
        f"differences={summary['fail_count']} skips={summary['skip_count']} timeouts={summary['timeout_count']} "
        f"unable={summary['unable_to_verify_count']} comment_issues={summary['comment_issue_count']} "
        f"total_seconds={total_seconds}"
    )
    return 0


COMPARISON_FIELDS = [
    "organization_name",
    "ein",
    "state",
    "expected",
    "actual",
    "comparison",
    "likely_category",
    "app_version",
    "matched_registry_name",
    "matched_registry_identifier",
    "raw_status_text",
    "comments",
    "lookup_seconds",
    "state_wall_seconds",
    "batch_seconds",
    "runner_error",
    "runner_recovery",
    "reason_code",
    "runner_reason_code",
    "source_confidence",
    "status_reason",
    "last_year_on_record",
    "fiscal_year_end",
    "next_required_period",
    "computed_due_date",
]

COMMENT_FIELDS = [*COMPARISON_FIELDS, "comment_issue"]


if __name__ == "__main__":
    raise SystemExit(main())
