#!/usr/bin/env python3
from __future__ import annotations

import csv
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

import CharityClarity_WA_NM_checker as nm_checker
import registry_snapshot_server as cc


FIXTURE = Path(__file__).with_name("core_matching_regression_cases.csv")


def norm(value: str) -> str:
    return cc.normalized_match_name(value or "")


def assert_name_variants(rows: list[dict[str, str]], failures: list[str]) -> None:
    for row in rows:
        expected = (row.get("expected_variant") or "").strip()
        if not expected:
            continue
        variants = cc.organization_name_variants(row["organization_name"], row.get("ein", ""))
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


def assert_deadline_helpers(failures: list[str]) -> None:
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
    interpreted = cc.true_status_from_body(sc_result, sc_result.raw_status_text)
    if interpreted == "Current":
        failures.append("sc_missing_filing_data: raw Registered without a filing date was classified as Current")


def main() -> int:
    with FIXTURE.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    failures: list[str] = []
    assert_name_variants(rows, failures)
    assert_false_positive_guards(rows, failures)
    assert_deadline_helpers(failures)
    if failures:
        print("FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"PASS core matching guardrails ({len(rows)} fixture rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
