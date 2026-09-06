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
args = parser.parse_args()
rows = json.loads(Path(__file__).with_name("weekly-data-regression-baseline.json").read_text(encoding="utf-8"))
if not args.full:
    rows = [r for r in rows if r["state"] in {"KS", "KY", "LA", "NH", "OR"} or (r["state"] == "CO" and r["ein"] == "860481941")]
rows.append({"organization": "ZZZ CharityClarity Nonexistent Test 987654321", "ein": "000000000", "state": "KS", "manual_expected": "Not Registered", "prior_staging": "Not Registered"})
if not args.staging:
    import registry_snapshot_server as cc

def run(row):
    started = time.perf_counter()
    try:
        if args.staging:
            request = urllib.request.Request(API, data=json.dumps({"organization_name": row["organization"], "ein": row["ein"], "state": row["state"]}).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=120) as response:
                result = json.load(response)
        else:
            result = cc.run_state_lookup(row["organization"], row["ein"], row["state"])
        return {**row, "result": result, "seconds": round(time.perf_counter() - started, 2)}
    except Exception as exc:
        return {**row, "error": str(exc), "seconds": round(time.perf_counter() - started, 2)}

output = Path(args.output)
output.parent.mkdir(parents=True, exist_ok=True)
results = []
with output.open("w", encoding="utf-8") as handle, concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    for future in concurrent.futures.as_completed([pool.submit(run, row) for row in rows]):
        result = future.result()
        results.append(result)
        handle.write(json.dumps(result) + "\n")
        handle.flush()
        print(result["organization"], result["state"], result.get("result", {}).get("status", "ERROR"), result["seconds"], flush=True)
print("Completed", len(results), "checks; evidence", output)
