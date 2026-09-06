"""Bounded repeatability experiment against unchanged live staging, not runtime code."""
import argparse
import concurrent.futures
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--version", required=True)
args = parser.parse_args()
ROOT = args.output
if (ROOT / "metadata.json").exists():
    raise RuntimeError("Refusing to overwrite an existing experiment")
ROOT.mkdir(parents=True, exist_ok=True)
API = "https://instant-compliance-snapshot-api-staging-8dnk.onrender.com"
LANES = {
    "NY": [
        ("Make-A-Wish Foundation of America", "860481941", "NY", "Delinquent"),
        ("Junior Achievement USA", "841267604", "NY", "Delinquent"),
        ("Ronald McDonald House Global / RMHC", "362934689", "NY", "Delinquent"),
        ("Prevent Child Abuse America", "237235671", "NY", "Delinquent"),
    ],
    "MI-control": [
        ("Make-A-Wish Foundation of America", "860481941", "MI", "Current"),
        ("Make-A-Wish Foundation of America", "860481941", "CO", "Current"),
    ],
    "OK": [
        ("Make-A-Wish Foundation of America", "860481941", "OK", "Upcoming Filing"),
        ("Ronald McDonald House Global / RMHC", "362934689", "OK", "Upcoming Filing"),
    ],
}

def health():
    with urllib.request.urlopen(API + "/health", timeout=30) as response:
        result = json.load(response)
    if result["app_version"] != args.version:
        raise RuntimeError("Staging version changed; stop the repeatability experiment")
    return result

def lane(round_number, cases):
    results = []
    for name, ein, state, expected in cases:
        row = {"round": round_number, "organization": name, "ein": ein, "state": state,
               "reference_status": expected, "started_utc": datetime.now(timezone.utc).isoformat()}
        started = time.perf_counter()
        payload = {"organization_name": name, "ein": ein, "state": state,
                   "email": "staging-smoke@" + cc.EXEMPT_EMAIL_DOMAIN,
                   "admin_passcode": cc.ADMIN_PASSCODE}
        request = urllib.request.Request(API + "/api/check", data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=130) as response:
                row["http_status"] = response.status
                row["result"] = json.load(response)
        except urllib.error.HTTPError as exc:
            row["http_status"] = exc.code
            row["error"] = exc.read().decode("utf-8", errors="replace")[:2000]
        except Exception as exc:
            row["error"] = str(exc)
        row["seconds"] = round(time.perf_counter() - started, 2)
        row["finished_utc"] = datetime.now(timezone.utc).isoformat()
        results.append(row)
        # Separate files avoid interleaving writes between lanes; every initial attempt is retained.
        path = ROOT / f"round-{round_number}-{state}-{ein}.json"
        path.write_text(json.dumps(row, indent=2), encoding="utf-8")
        print(round_number, state, name, row.get("result", {}).get("status", "ERROR"), row["seconds"], flush=True)
    return results

metadata = {"started_utc": datetime.now(timezone.utc).isoformat(), "rounds": 5,
            "method": "Three concurrent lanes; at most one active request per target state. No harness retries. Identical inputs each round. Existing backend internal retries remain unchanged.",
            "initial_health": health(), "rounds_completed": 0}
metadata_path = ROOT / "metadata.json"
metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
with (ROOT / "attempts.jsonl").open("w", encoding="utf-8") as handle:
    for round_number in range(1, 6):
        health()
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(lane, round_number, cases) for cases in LANES.values()]
            for future in concurrent.futures.as_completed(futures):
                for row in future.result():
                    handle.write(json.dumps(row) + "\n")
                handle.flush()
        metadata["rounds_completed"] = round_number
        metadata["last_round_health"] = health()
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
metadata["finished_utc"] = datetime.now(timezone.utc).isoformat()
metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
print("Experiment complete: 40 attempts, no harness retries.", flush=True)
