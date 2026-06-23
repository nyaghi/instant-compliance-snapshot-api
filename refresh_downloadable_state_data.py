"""Refresh CharityClarity downloadable-state data used by staging.

This is a maintenance script, not a runtime state checker. It updates packaged
downloadable sources where CharityClarity relies on local list data and verifies
downloadable states that are normally fetched live at runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from curl_cffi import requests
from pypdf import PdfReader


BASE_DIR = Path(__file__).resolve().parent
SERVER_PATH = BASE_DIR / "registry_snapshot_server.py"
NH_PDF_PATH = BASE_DIR / "registered-charities.pdf"
OR_EXPORT_PATH = BASE_DIR / "Charity_OR.txt"


def load_server_module():
    spec = importlib.util.spec_from_file_location("registry_snapshot_server_refresh", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SERVER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download_pdf(url: str, referer: str, timeout: int = 90) -> bytes:
    response = requests.get(
        url,
        impersonate="chrome120",
        timeout=timeout,
        headers={
            "Accept": "application/pdf,*/*",
            "Referer": referer,
        },
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if not response.content.startswith(b"%PDF"):
        raise RuntimeError(f"Downloaded source is not a PDF; content-type={content_type!r}")
    return response.content


def pdf_updated_label(pdf_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
        handle.write(pdf_bytes)
        temp_path = Path(handle.name)
    try:
        reader = PdfReader(str(temp_path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages[:3])
    finally:
        temp_path.unlink(missing_ok=True)
    import re

    match = re.search(r"\bUpdated:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})", text, re.I)
    return match.group(1) if match else ""


def refresh_nh(server_module, dry_run: bool) -> dict[str, object]:
    pdf_bytes = download_pdf(
        server_module.NH_LIVE_PDF_URL,
        "https://www.doj.nh.gov/bureaus/charitable-trusts/registered-charities",
    )
    checksum = sha256_bytes(pdf_bytes)
    old_checksum = sha256_bytes(NH_PDF_PATH.read_bytes()) if NH_PDF_PATH.exists() else ""
    changed = checksum != old_checksum
    label = pdf_updated_label(pdf_bytes)
    if not dry_run and changed:
        tmp_path = NH_PDF_PATH.with_suffix(".pdf.tmp")
        tmp_path.write_bytes(pdf_bytes)
        shutil.move(str(tmp_path), str(NH_PDF_PATH))

    # Validate with the production parser, using the refreshed bytes even in dry-run.
    with tempfile.TemporaryDirectory(prefix="nh_refresh_parse_") as temp_dir:
        temp_pdf = Path(temp_dir) / "registered-charities.pdf"
        temp_pdf.write_bytes(pdf_bytes)
        server_module.NH_LIVE_PDF_RECORDS = None
        server_module.NH_BUNDLED_PDF_PATH = temp_pdf
        server_module.NH_BUNDLED_XLSX_PATH = Path(temp_dir) / "missing.xlsx"
        records, parsed_label = server_module.nh_live_pdf_records()
    if len(records) < 1000:
        raise RuntimeError(f"NH parser returned suspiciously few records: {len(records)}")
    return {
        "state": "NH",
        "status": "changed" if changed else "unchanged",
        "record_count": len(records),
        "updated_label": parsed_label or label,
        "checksum": checksum,
    }


def refresh_ks(dry_run: bool) -> dict[str, object]:
    if dry_run:
        spec = importlib.util.spec_from_file_location("ks_weekly_checker_refresh", BASE_DIR / "KS_weekly_checker.py")
        if spec is None or spec.loader is None:
            raise RuntimeError("Could not load KS_weekly_checker.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return {
            "state": "KS",
            "status": "dry-run",
            "last_checked_at": module.SNAPSHOT_LAST_CHECKED_AT,
            "last_changed_at": module.SNAPSHOT_LAST_CHANGED_AT,
            "last_refresh_status": module.SNAPSHOT_LAST_REFRESH_STATUS,
            "source_filename": module.SNAPSHOT_SOURCE_FILENAME,
        }
    command = [sys.executable, "KS_weekly_checker.py", "--refresh"]
    completed = subprocess.run(
        command,
        cwd=BASE_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"KS refresh failed: {completed.stderr.strip() or completed.stdout.strip()}")
    return {
        "state": "KS",
        "status": "checked",
        "stdout": completed.stdout.strip(),
    }


def verify_ky(server_module) -> dict[str, object]:
    records = server_module.load_ky_live_pdf_records()
    if not records:
        # Runtime can fall back to embedded KY data, but the weekly job should
        # still flag this because the live downloadable list was not available.
        raise RuntimeError("KY live downloadable PDF returned zero parseable records")
    return {
        "state": "KY",
        "status": "live-verified",
        "record_count": len(records),
    }


def verify_or() -> dict[str, object]:
    if not OR_EXPORT_PATH.exists():
        raise RuntimeError(f"OR export missing: {OR_EXPORT_PATH}")
    size = OR_EXPORT_PATH.stat().st_size
    if size < 1_000_000:
        raise RuntimeError(f"OR export is suspiciously small: {size} bytes")
    return {
        "state": "OR",
        "status": "packaged-export-present",
        "bytes": size,
        "last_write_time_utc": datetime.fromtimestamp(OR_EXPORT_PATH.stat().st_mtime, timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh/verify CharityClarity downloadable state data.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--states",
        default="NH,KS,KY,OR",
        help="Comma-separated downloadable states to refresh or verify. WI is intentionally excluded.",
    )
    args = parser.parse_args()
    states = {part.strip().upper() for part in args.states.split(",") if part.strip()}
    server_module = load_server_module()
    results: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []

    for state in ["NH", "KS", "KY", "OR"]:
        if state not in states:
            continue
        try:
            if state == "NH":
                results.append(refresh_nh(server_module, args.dry_run))
            elif state == "KS":
                results.append(refresh_ks(args.dry_run))
            elif state == "KY":
                results.append(verify_ky(server_module))
            elif state == "OR":
                results.append(verify_or())
        except Exception as exc:
            errors.append({"state": state, "error": " ".join(str(exc).split())})

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
        "results": results,
        "errors": errors,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
