"""Private lab forkserver template. Loads code and verified public source tables once; never executes a lookup.

No organization inputs, completed results, database connections, browser sessions
or task threads enter this process. Each job receives a separate copy-on-write
child; that child and its browser descendants are killed before releasing slots.
"""
import os
import json
from pathlib import Path
import sys
import threading
import time

from deployment.performance_lab import validate_environment, install_http_egress_guard


def preload_ky_public_names(master):
    """Warm only pure name normalization from a currently verified public file.

    Never invoke the live fallback or an organization lookup. Each child still
    loads and validates the current source and performs every identity/date rule.
    The existing cache is keyed by the actual name, not a record ID or status.
    """
    path = master.weekly_asset("KY", "downloadable-data/KY-records.json")
    if path is not None:
        for _, registry_name, _, _ in json.loads(path.read_text(encoding="utf-8")):
            for name in master.ky_registry_name_variants(registry_name):
                master.normalized_match_name(name)

validate_environment(os.environ)
if not sys.platform.startswith('linux'):
    raise RuntimeError('The warm engine template requires Linux forkserver isolation')
for key in ('CE_LAB_DATABASE_URL','CE_TEST_DATABASE_URL','RENDER_API_KEY'):
    os.environ.pop(key,None)
os.environ['CE_LAB_DURABLE_QUEUE']='0'
install_http_egress_guard()
started, cpu_started = time.monotonic(), time.process_time()
import registry_snapshot_server as master
# Pure source parsing only: no EIN, organization, live network or match results.
# Child lookups repeat freshness/asset validation before reusing these tables.
for source in ("KS", "NH", "OR", "KY"):
    try:
        if source == "KS" and master.downloadable_data_info(source).get("usable"):
            ks = master.load_ks_weekly_checker()
            records, _, _ = ks.load_live_records()
            for row in records:
                ks.normalize_name(row.name)
                ks.normalize_legal_name(row.name)
            del records, row
        elif source == "OR":
            master.validated_or_snapshot_index()
        elif source == "KY":
            preload_ky_public_names(master)
        elif (source == "NH" and master.weekly_asset(source, "downloadable-data/NH-records.json") is not None
                and master.weekly_asset(source, "registered-charities.pdf") is not None):
            records, _ = master.nh_download_live_pdf_records()
            for row in records:
                master.distinctive_match_tokens(master.normalized_match_name(row["registry_name"]))
            del records, row
    except Exception as exc:
        # A broken source must remain an ordinary state failure, not prevent
        # unrelated states from starting. The lookup revalidates it in its child.
        master.log_event(f"Static source preload skipped: {source}; {type(exc).__name__}")
IMPORT_SECONDS=time.monotonic()-started
IMPORT_CPU_SECONDS=time.process_time()-cpu_started
PRELOAD_PID=os.getpid()
if threading.active_count()!=1 or len(list(Path('/proc/self/task').iterdir()))!=1:
    raise RuntimeError('Refusing to fork a template with active library threads')
