#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

import registry_snapshot_server as cc


def make_result(state: str, status: str, reason: str = "") -> dict:
    return {
        "state": state,
        "status": status,
        "raw_status_text": reason,
        "comments": reason,
        "reason_code": reason,
    }


def main() -> int:
    failures: list[str] = []

    healthy = [make_result("WV", "Not Registered") for _ in range(12)]
    cc.apply_batch_state_health(healthy)
    if {row.get("state_health") for row in healthy} != {"STATE_HEALTH_OK"}:
        failures.append("healthy WV no-match batch should remain STATE_HEALTH_OK")

    flooded = [make_result("WV", "Unable to Verify", "WV_INCOMPLETE_BOUNDED_SEARCH") for _ in range(4)]
    flooded.extend(make_result("WV", "Not Registered") for _ in range(8))
    cc.apply_batch_state_health(flooded)
    if {row.get("state_health") for row in flooded} != {"STATE_HEALTH_UNKNOWN_FAILURE"}:
        failures.append("WV 25% inconclusive flood should be classified as state-level unknown failure")

    timeout_cluster = [make_result("WI", "Runner Timeout", "RUNNER_TIMEOUT_RETRY_FAILED") for _ in range(3)]
    timeout_cluster.extend(make_result("WI", "Not Registered") for _ in range(9))
    cc.apply_batch_state_health(timeout_cluster)
    if {row.get("state_health") for row in timeout_cluster} != {"STATE_HEALTH_TIMEOUT_CLUSTER"}:
        failures.append("WI timeout cluster should be classified as STATE_HEALTH_TIMEOUT_CLUSTER")

    if failures:
        print("FAIL state health checks")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("PASS state health checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
