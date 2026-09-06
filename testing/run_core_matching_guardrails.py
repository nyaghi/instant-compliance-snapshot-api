#!/usr/bin/env python3
from __future__ import annotations

import csv
from datetime import date
from unittest.mock import patch
import sys
from pathlib import Path
from types import SimpleNamespace

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

import CharityClarity_WA_NM_checker as nm_checker
import registry_snapshot_server as cc


FIXTURE = Path(__file__).with_name("core_matching_regression_cases.csv")
LATEST_FIXTURE = Path(__file__).with_name("latest_failure_regression_cases.csv")
SERVER_SOURCE = BASE_DIR / "registry_snapshot_server.py"


def norm(value: str) -> str:
    return cc.normalized_match_name(value or "")


def assert_name_variants(rows: list[dict[str, str]], failures: list[str]) -> None:
    for row in rows:
        expected = (row.get("expected_variant") or "").strip()
        if not expected:
            continue
        variants = [
            *cc.organization_name_variants(row["organization_name"], row.get("ein", "")),
            *cc.category_preferred_name_variants(row["organization_name"]),
        ]
        normalized_variants = {norm(variant) for variant in variants}
        if norm(expected) not in normalized_variants:
            failures.append(
                f"{row['case_id']}: missing variant {expected!r}; got {variants[:12]!r}"
            )


def assert_false_positive_guards(rows: list[dict[str, str]], failures: list[str]) -> None:
    for row in rows:
        forbidden = (row.get("forbidden_registry_name") or "").strip()
        if not forbidden:
            continue
        if cc.registry_name_is_safe_for_org(forbidden, row["organization_name"], row.get("ein", "")):
            failures.append(
                f"{row['case_id']}: weak registry name {forbidden!r} was accepted for {row['organization_name']!r}"
            )


def assert_shared_query_builder(rows: list[dict[str, str]], failures: list[str]) -> None:
    for row in rows:
        expected = (row.get("expected_query") or "").strip()
        if not expected:
            continue
        queries = cc.build_search_queries(
            row["organization_name"],
            row.get("ein", ""),
            include_ein=False,
            include_ein_aliases=True,
            include_name_segments=True,
            max_queries=40,
        )
        normalized_queries = {norm(query) for query in queries}
        if norm(expected) not in normalized_queries:
            failures.append(
                f"latest_{row['state']}_{row['ein']}: missing shared query {expected!r}; got {queries[:16]!r}"
            )


def assert_latest_false_positive_categories(rows: list[dict[str, str]], failures: list[str]) -> None:
    for row in rows:
        if row.get("failure_category") != "false_positive":
            continue
        weak_name = (row.get("forbidden_registry_name") or "").strip()
        if not weak_name:
            continue
        decision = cc.score_candidate(
            row["organization_name"],
            row.get("ein", ""),
            {"name": weak_name},
        )
        if decision.get("decision") == "accepted" and int(decision.get("score") or 0) >= 70:
            failures.append(
                f"latest_false_positive_{row['state']}_{row['ein']}: weak candidate {weak_name!r} accepted with {decision!r}"
            )


def assert_alias_segment_guards(failures: list[str]) -> None:
    good_cases = [
        ("Umbrella Charity dba River Scholars", "River Scholars"),
        ("Community Health Fund AKA Clinic Partners", "Clinic Partners"),
        ("Legal Organization also soliciting as Reading Partners", "Reading Partners"),
        ("Former Legal Name / Bright Futures Project", "Bright Futures Project"),
    ]
    for registry_text, requested_name in good_cases:
        if not cc.registry_alias_segment_matches_requested(registry_text, requested_name):
            failures.append(
                f"alias_segment: expected {registry_text!r} to safely match requested alias {requested_name!r}"
            )

    bad_cases = [
        ("Umbrella Charity dba River Scholars", "Bridge Fund"),
        ("America Inc", "BMW Car Club Of America Foundation"),
        ("Outreach Inc", "Christian World Outreach"),
    ]
    for registry_text, requested_name in bad_cases:
        if cc.registry_alias_segment_matches_requested(registry_text, requested_name):
            failures.append(
                f"alias_segment: weak/unrelated registry text {registry_text!r} was accepted for {requested_name!r}"
            )


def assert_state_specific_variant_order(failures: list[str]) -> None:
    ar_org = SimpleNamespace(
        organization_name="THE MARIAN A. SMITH FUND INC. (COMMUNITY SCHOLARS)",
        ein="000000000",
    )
    ar_variants = cc.ar_preferred_name_variants(ar_org)[:12]
    ar_norms = {norm(variant) for variant in ar_variants}
    for expected in ["COMMUNITY SCHOLARS", "MARIAN"]:
        if norm(expected) not in ar_norms:
            failures.append(
                f"ar_variant_order: expected {expected!r} inside bounded AR variants; got {ar_variants!r}"
            )

    ms_variants = cc.ms_preferred_search_variants(
        "Wilkes Barre Community Foundation Incorporated",
        "000000000",
    )[:6]
    ms_norms = {norm(variant) for variant in ms_variants}
    for expected in ["Wilkes-Barre Community Foundation", "Wilkes-Barre Community"]:
        if norm(expected) not in ms_norms:
            failures.append(
                f"ms_variant_order: expected {expected!r} inside bounded MS variants; got {ms_variants!r}"
            )


def assert_deadline_helpers(failures: list[str]) -> None:
    # The approved scenarios describe June 2026. Freeze their clock rather than
    # letting an unchanged expected Upcoming result expire as wall time passes.
    class FixtureDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 6, 25)
    with patch.object(nm_checker, "date", FixtureDate):
        _assert_deadline_helpers_at_fixture_date(failures)


def _assert_deadline_helpers_at_fixture_date(failures: list[str]) -> None:
    give2asia = nm_checker.SearchResult(
        "Give2Asia",
        "943373670",
        "NM",
        nm_checker.STATUS_UNKNOWN,
        "",
        nm_checker.NM_SEARCH_URL,
        "",
    )
    nm_checker.apply_nm_rows_to_result(
        give2asia,
        [
            (2025, "Registration Submitted 1234567890", "10/20/2025"),
            (2025, "Extension Granted", "03/30/2026"),
        ],
        fye_text="09/30/2025",
    )
    if give2asia.status != nm_checker.STATUS_UPCOMING or "Due: 08/15/2026" not in give2asia.raw_status_text:
        failures.append(
            "nm_extension_upcoming: expected Upcoming Filing with Due: 08/15/2026; "
            f"got {give2asia.status!r} / {give2asia.raw_status_text!r}"
        )

    un_women = nm_checker.SearchResult(
        "U.S. NATIONAL COMMITTEE FOR UN WOMEN",
        "541244401",
        "NM",
        nm_checker.STATUS_UNKNOWN,
        "",
        nm_checker.NM_SEARCH_URL,
        "",
    )
    nm_checker.apply_nm_rows_to_result(
        un_women,
        [
            (2025, "Tax Year Registration Open", "06/01/2025"),
            (2024, "Registration Submitted 1234567890", "04/30/2025"),
        ],
        fye_text="11/30/2024",
    )
    if un_women.status != nm_checker.STATUS_DELINQUENT:
        failures.append(
            "nm_open_cycle_not_submitted: expected Delinquent from latest submitted year; "
            f"got {un_women.status!r} / {un_women.raw_status_text!r}"
        )

    sc_result = cc.checker.StateResult(
        "Foot Soldiers Park Inc",
        "861479452",
        "SC",
        "Registered",
        "",
        raw_status_text="Registered. Information from this organization's annual financial report is listed below.",
    )
    sc_result.matched_registry_name = "Foot Soldiers Park Inc"
    interpreted = cc.true_status_from_body(sc_result, sc_result.raw_status_text)
    if interpreted != cc.checker.STATUS_DELINQUENT:
        failures.append(
            "sc_missing_filing_data: expected safe raw Registered without usable filing evidence to classify as "
            f"Delinquent; got {interpreted!r}"
        )


def assert_no_fixture_hardwiring(rows: list[dict[str, str]], failures: list[str]) -> None:
    source = SERVER_SOURCE.read_text(encoding="utf-8", errors="ignore")
    compact_source = source.lower()
    for row in rows:
        ein = "".join(ch for ch in (row.get("ein") or "") if ch.isdigit())
        if len(ein) == 9 and ein in compact_source:
            failures.append(
                f"anti_hardwiring: fixture EIN {ein} appears in runtime server source"
            )
        org_name = (row.get("organization_name") or "").strip()
        if len(org_name) >= 12 and org_name.lower() in compact_source:
            failures.append(
                f"anti_hardwiring: fixture organization {org_name!r} appears in runtime server source"
            )


def main() -> int:
    with FIXTURE.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    latest_rows = []
    if LATEST_FIXTURE.exists():
        with LATEST_FIXTURE.open(newline="", encoding="utf-8") as handle:
            latest_rows = list(csv.DictReader(handle))
    failures: list[str] = []
    assert_name_variants(rows, failures)
    assert_shared_query_builder(latest_rows, failures)
    assert_false_positive_guards(rows, failures)
    assert_latest_false_positive_categories(latest_rows, failures)
    assert_alias_segment_guards(failures)
    assert_state_specific_variant_order(failures)
    assert_deadline_helpers(failures)
    assert_no_fixture_hardwiring(latest_rows, failures)
    if failures:
        print("FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"PASS core matching guardrails ({len(rows)} fixture rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
