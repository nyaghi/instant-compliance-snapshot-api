"""Local or live staging checks for weekly data releases; not runtime routing."""
import argparse
import concurrent.futures
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
API = "https://instant-compliance-snapshot-api-staging-8dnk.onrender.com/api/check"
parser = argparse.ArgumentParser()
parser.add_argument("--staging", action="store_true")
parser.add_argument("--full", action="store_true")
parser.add_argument("--output", required=True)
parser.add_argument("--cases", help="Explicit research/test cases; approved expectations are preserved.")
args = parser.parse_args()
rows = json.loads((Path(args.cases) if args.cases else Path(__file__).with_name("weekly-data-regression-baseline.json")).read_text(encoding="utf-8"))
if not args.full and not args.cases:
    rows = [r for r in rows if r["state"] in {"KS", "KY", "LA", "NH", "OR"} or (r["state"] == "CO" and r["ein"] == "860481941")]
if not args.cases:
    rows.append({"organization": "ZZZ CharityClarity Nonexistent Test 987654321", "ein": "000000000", "state": "KS", "manual_expected": "Not Registered", "prior_staging": "Not Registered"})
import registry_snapshot_server as cc

def run(row):
    started = time.perf_counter()
    try:
        if args.staging:
            request = urllib.request.Request(API, data=json.dumps({"organization_name": row["organization"], "ein": row["ein"], "state": row["state"], "email": "staging-smoke@" + cc.EXEMPT_EMAIL_DOMAIN, "admin_passcode": cc.ADMIN_PASSCODE}).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=240) as response:
                result = json.load(response)
        else:
            result = cc.run_state_lookup(row["organization"], row["ein"], row["state"])
        return {**row, "result": result, "seconds": round(time.perf_counter() - started, 2)}
    except Exception as exc:
        return {**row, "error": str(exc), "seconds": round(time.perf_counter() - started, 2)}

output = Path(args.output)
output.parent.mkdir(parents=True, exist_ok=True)
first = run(rows[0])
if first.get("error"):
    output.write_text(json.dumps(first) + "\n", encoding="utf-8")
    print("First request failed; stopped before submitting the remaining checks:", first["error"])
    sys.exit(1)
results = [first]
with output.open("w", encoding="utf-8") as handle, concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    handle.write(json.dumps(first) + "\n")
    handle.flush()
    for future in concurrent.futures.as_completed([pool.submit(run, row) for row in rows[1:]]):
        result = future.result()
        results.append(result)
        handle.write(json.dumps(result) + "\n")
        handle.flush()
        print(result["organization"], result["state"], result.get("result", {}).get("status", "ERROR"), result["seconds"], flush=True)
print("Completed", len(results), "checks; evidence", output)

if any(r.get("error") or r.get("result", {}).get("status") in {"Needs Review", "Unable to Confirm", "Site Not Reachable", "Unable to Verify", "Unknown"} for r in results):
    sys.exit(1)
