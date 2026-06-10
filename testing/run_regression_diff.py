#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


KEY_FIELDS = ("organization_name", "ein", "state")


def norm(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def status_match(row: dict[str, str]) -> bool:
    comparison = norm(row.get("comparison", ""))
    if comparison:
        return comparison in {"match", "matched", "ok", "pass"}
    return norm(row.get("expected") or row.get("expected_status")) == norm(row.get("actual") or row.get("actual_status"))


def row_key(row: dict[str, str]) -> tuple[str, str, str]:
    return (
        norm(row.get("organization") or row.get("organization_name")),
        "".join(ch for ch in (row.get("ein") or "") if ch.isdigit()),
        (row.get("state") or "").strip().upper(),
    )


def read_failures(path: Path) -> dict[tuple[str, str, str], dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    return {row_key(row): row for row in rows if not status_match(row)}


def category_for(row: dict[str, str]) -> str:
    for field in ("likely_category", "category", "failure_category"):
        value = (row.get(field) or "").strip()
        if value:
            return value
    actual = norm(row.get("actual") or row.get("actual_status"))
    expected = norm(row.get("expected") or row.get("expected_status"))
    if actual in {"unable to verify", "unable to confirm", "needs review"}:
        return "UNABLE_TO_VERIFY_FLOOD"
    if actual == "runner timeout":
        return "RUNNER_TIMEOUT"
    if actual == "not registered" and expected != "not registered":
        return "FALSE_NEGATIVE_SEARCH_MISS"
    if actual != "not registered" and expected == "not registered":
        return "FALSE_POSITIVE_GENERIC_TOKEN"
    return "NEEDS_MANUAL_REVIEW"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--current", required=True)
    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    current_path = Path(args.current)
    baseline = read_failures(baseline_path)
    current = read_failures(current_path)
    new_keys = sorted(set(current) - set(baseline))
    fixed_keys = sorted(set(baseline) - set(current))

    states = sorted({key[2] for key in set(baseline) | set(current)})
    print("State | Baseline Failures | Current Failures | New Failures | Fixed Failures | Net")
    print("--- | ---: | ---: | ---: | ---: | ---:")
    for state in states:
        baseline_state = {key for key in baseline if key[2] == state}
        current_state = {key for key in current if key[2] == state}
        new_state = {key for key in new_keys if key[2] == state}
        fixed_state = {key for key in fixed_keys if key[2] == state}
        print(
            f"{state} | {len(baseline_state)} | {len(current_state)} | "
            f"{len(new_state)} | {len(fixed_state)} | {len(current_state) - len(baseline_state)}"
        )

    baseline_categories = Counter(category_for(row) for row in baseline.values())
    current_categories = Counter(category_for(row) for row in current.values())
    new_categories = Counter(category_for(current[key]) for key in new_keys)
    fixed_categories = Counter(category_for(baseline[key]) for key in fixed_keys)
    categories = sorted(set(baseline_categories) | set(current_categories) | set(new_categories) | set(fixed_categories))
    print()
    print("Category | Baseline Count | Current Count | New | Fixed | Net")
    print("--- | ---: | ---: | ---: | ---: | ---:")
    for category in categories:
        print(
            f"{category} | {baseline_categories[category]} | {current_categories[category]} | "
            f"{new_categories[category]} | {fixed_categories[category]} | "
            f"{current_categories[category] - baseline_categories[category]}"
        )

    if new_keys:
        print()
        print("New failures:")
        for key in new_keys[:200]:
            row = current[key]
            print(
                f"- {key[2]} {row.get('ein')}: {row.get('organization') or row.get('organization_name')} "
                f"expected {row.get('expected') or row.get('expected_status')} got {row.get('actual') or row.get('actual_status')}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
