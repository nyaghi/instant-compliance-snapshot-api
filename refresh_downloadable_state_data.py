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
    # Parse exactly the bytes just downloaded, before replacing a deployed asset.
    from unittest.mock import patch
    import io
    server_module.NH_LIVE_PDF_RECORDS = None
    with patch.object(server_module, "weekly_asset", return_value=None), patch.object(
        server_module.urllib.request, "urlopen", return_value=io.BytesIO(pdf_bytes)
    ):
        records, parsed_label = server_module.nh_live_pdf_records()
    if len(records) < 1000:
        raise RuntimeError(f"NH parser returned suspiciously few records: {len(records)}")
    if not dry_run and changed:
        NH_PDF_PATH.write_bytes(pdf_bytes)
    return {
        "state": "NH",
        "status": "changed" if changed else "unchanged",
        "record_count": len(records),
        "updated_label": label or parsed_label,
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


def refresh_ky(server_module, dry_run: bool) -> dict:
    from unittest.mock import patch
    import io
    pdf_bytes = download_pdf(server_module.KY_LIVE_PDF_URL, "https://www.ag.ky.gov/")
    server_module.KY_LIVE_PDF_RECORDS = None
    with patch.object(server_module.urllib.request, "urlopen", return_value=io.BytesIO(pdf_bytes)):
        records = server_module.load_ky_live_pdf_records()
    if len(records) < 1000:
        raise RuntimeError(f"KY suspicious parsed record count: {len(records)}")
    if not dry_run:
        (BASE_DIR / "downloadable-data/KY.pdf").write_bytes(pdf_bytes)
        (BASE_DIR / "downloadable-data/KY-records.json").write_text(json.dumps(records), encoding="utf-8")
    return {"state": "KY", "record_count": len(records), "source_url": server_module.KY_LIVE_PDF_URL,
            "source_date": pdf_updated_label(pdf_bytes)}


def refresh_la(server_module, dry_run: bool) -> dict:
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory(prefix="la_weekly_") as folder, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(accept_downloads=True)
            path, source, error = server_module.la_download_registered_charities_export(page, Path(folder))
            if path is None:
                raise RuntimeError(f"LA export download failed: {error}")
            records = server_module.la_registered_charities_rows_from_xlsx(path)
            # Louisiana's solicitation list is much smaller than general charity registries.
            if len(records) < 25 or not all(server_module.la_record_name(r) for r in records):
                raise RuntimeError(f"LA invalid export: {len(records)} rows")
            if not dry_run:
                shutil.copyfile(path, BASE_DIR / "downloadable-data/LA.xlsx")
            return {"state": "LA", "record_count": len(records),
                    "source_url": "https://www.ag.state.la.us/Charity/Registration/Listing", "source_date": ""}
        finally:
            browser.close()


def refresh_or(dry_run: bool) -> dict:
    import csv, io, zipfile
    url = "https://justice.oregon.gov/Charities/Charity/GetZip"
    response = requests.get(url, impersonate="chrome120", timeout=90)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        candidates = [i for i in archive.infolist() if i.filename.lower() == "charity.txt"]
        if len(candidates) != 1 or candidates[0].file_size > 50_000_000:
            raise RuntimeError("OR archive missing expected Charity.txt or exceeds size limit")
        raw = archive.read(candidates[0])
    text = raw.decode("utf-8-sig")
    import re
    # The official export leaves embedded newlines and tildes unquoted. A record
    # starts with CharityID~RegistrationNumber, not every physical line.
    chunks = re.split(r"\r?\n(?=\d+~\d+~)", text)
    header = chunks[0].strip().split("~")
    expected = ["CharityID", "RegistrationNumber", "CategoryCode", "IRSCode", "EIN", "Purpose", "Name"]
    if header[:7] != expected or header[14:16] != ["PeriodBeginning", "PeriodEnding"]:
        raise RuntimeError("OR source schema changed")
    rows = [header]
    for chunk in chunks[1:]:
        fields = [re.sub(r"[\r\n]+", " ", field).strip() for field in chunk.split("~")]
        # Two unused trailing columns occur in the source, but not its header.
        if fields[-2:] != ["", ""]:
            raise RuntimeError("OR trailing-column schema changed")
        fields = fields[:-2]
        if len(fields) > len(header):
            # Name permits literal tildes; the fourteen typed/address fields
            # following it retain their fixed positions from the right.
            fields = fields[:6] + ["~".join(fields[6:-14])] + fields[-14:]
        if len(fields) != len(header) or not fields[0].isdigit() or not fields[1].isdigit():
            raise RuntimeError("OR export incomplete or malformed")
        if any(fields[i] and not re.fullmatch(r"[A-Za-z]{3} \d{2}, \d{4}", fields[i]) for i in (14, 15)):
            raise RuntimeError("OR fiscal-period columns misaligned")
        for index in (14, 15):
            if fields[index]:
                fields[index] = datetime.strptime(fields[index], "%b %d, %Y").strftime("%m/%d/%Y")
        rows.append(fields)
    if len(rows) < 10000 or len({(row[0], row[14], row[15]) for row in rows[1:]}) != len(rows) - 1:
        raise RuntimeError("OR export incomplete or duplicated")
    output = io.StringIO(newline="")
    csv.writer(output, delimiter="\t", lineterminator="\n").writerows(rows)
    if not dry_run:
        OR_EXPORT_PATH.write_text(output.getvalue(), encoding="utf-8", newline="")
    return {"state": "OR", "record_count": sum(bool(row) for row in rows[1:]), "source_url": url, "source_date": ""}


ASSETS = {
    "KS": ["KS_weekly_checker.py"],
    "KY": ["downloadable-data/KY.pdf", "downloadable-data/KY-records.json"],
    "LA": ["downloadable-data/LA.xlsx"],
    "NH": ["registered-charities.pdf"],
    "OR": ["Charity_OR.txt"],
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and validate all five staging state datasets.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--states", default="KS,KY,LA,NH,OR")
    args = parser.parse_args()
    states = [part.strip().upper() for part in args.states.split(",") if part.strip()]
    if set(states) - set(ASSETS):
        parser.error("Supported downloadable states: KS,KY,LA,NH,OR")
    (BASE_DIR / "downloadable-data").mkdir(exist_ok=True)
    manifest_path = BASE_DIR / "downloadable-state-data.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"schema_version": 1, "states": {}}
    server = load_server_module()
    results, errors = [], []
    for state in states:
        print(f"Downloading {state}...", flush=True)
        backups = {name: (BASE_DIR / name).read_bytes() if (BASE_DIR / name).exists() else None for name in ASSETS[state]}
        try:
            if state == "KS":
                if args.dry_run:
                    # Dry-run must really download and parse; never mistake metadata inspection for refresh.
                    module = server.load_ks_weekly_checker()
                    data, url, filename = module.download_workbook_bytes_for_refresh(headless=True)
                    entry = {"state": state, "status": "downloaded-dry-run", "source_url": url, "bytes": len(data)}
                else:
                    refresh_ks(False)
                    ks_path = BASE_DIR / "KS_weekly_checker.py"
                    ks_path.write_bytes(ks_path.read_bytes().replace(b"\r\n", b"\n"))
                    spec = importlib.util.spec_from_file_location("ks_refreshed", BASE_DIR / "KS_weekly_checker.py")
                    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
                    records, url, _ = module.load_live_records()
                    entry = {"state": state, "record_count": len(records), "source_url": url,
                             "source_date": "", "content_last_changed_at": module.SNAPSHOT_LAST_CHANGED_AT}
            elif state == "KY":
                entry = refresh_ky(server, args.dry_run)
            elif state == "LA":
                entry = refresh_la(server, args.dry_run)
            elif state == "NH":
                # Validate the newly downloaded PDF, not any already-deployed cached version.
                from unittest.mock import patch
                with patch.object(server, "weekly_asset", return_value=None), patch.object(server, "NH_PREFER_ENV_PDF", True):
                    entry = refresh_nh(server, args.dry_run)
                entry.update(source_url=server.NH_LIVE_PDF_URL, source_date=entry.get("updated_label", ""))
            else:
                entry = refresh_or(args.dry_run)
            if not args.dry_run:
                old = manifest["states"].get(state, {})
                count = entry["record_count"]
                if old.get("record_count") and count < old["record_count"] * 0.8:
                    raise RuntimeError(f"{state} record count dropped over 20%; review required before deployment")
                entry["downloaded_at"] = datetime.now(timezone.utc).isoformat()
                entry["assets"] = [{"path": name, "sha256": sha256_bytes((BASE_DIR / name).read_bytes())} for name in ASSETS[state]]
                manifest["states"][state] = entry
            results.append(entry)
            print(f"Validated {state}: {entry.get('record_count', 'dry-run')} records", flush=True)
        except Exception as exc:
            if not args.dry_run:
                for name, original in backups.items():
                    if original is None:
                        (BASE_DIR / name).unlink(missing_ok=True)
                    else:
                        (BASE_DIR / name).write_bytes(original)
            errors.append({"state": state, "error": " ".join(str(exc).split())})
            print(f"FAILED {state}: {errors[-1]['error']}", flush=True)
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "dry_run": args.dry_run, "results": results, "errors": errors}
    if not args.dry_run:
        manifest["last_run"] = {"at": report["generated_at"], "errors": errors}
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
