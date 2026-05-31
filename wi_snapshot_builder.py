#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode, urljoin


WI_SEARCH_URL = "https://apps.dfi.wi.gov/ice/berg/Registration/OrganizationCredentialSearch.aspx"
WI_RESULTS_URL = "https://apps.dfi.wi.gov/ice/berg/Registration/OrgCredentialSearchResults.aspx"
WI_READER_BASE_URL = "https://r.jina.ai/http://"
DEFAULT_OUTPUT = Path(__file__).with_name("wi_charities_snapshot.json")


def clean_text(value: str) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def requires_verification(source: str) -> bool:
    return bool(re.search(r"Verification\s+Type\s+the\s+characters\s+you\s+see|letters\s+are\s+not\s+case\s+sensitive|captcha", clean_text(source), re.I))


def request_headers(referer: str = WI_SEARCH_URL) -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
            "CharityClarity-WI-Snapshot/1.0"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": referer,
    }


def reader_url(url: str) -> str:
    return f"{WI_READER_BASE_URL}{url}"


def fetch_direct_text(url: str, timeout: float, referer: str = WI_SEARCH_URL, retries: int = 2) -> str:
    last_error: BaseException | None = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, headers=request_headers(referer))
            with urllib.request.urlopen(request, timeout=timeout) as response:
                text = response.read().decode("utf-8", errors="replace")
            if requires_verification(text):
                raise RuntimeError("Wisconsin verification page returned")
            return text
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(0.4 * (attempt + 1))
                continue
            break
    raise RuntimeError(str(last_error or "request failed"))


def fetch_reader_text(url: str, timeout: float, retries: int = 2) -> str:
    last_error: BaseException | None = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(reader_url(url), headers={"User-Agent": "Mozilla/5.0 CharityClarity-WI-Snapshot/1.0"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                text = response.read().decode("utf-8", errors="replace")
            if requires_verification(text):
                raise RuntimeError("Wisconsin verification page returned")
            return text
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(0.6 * (attempt + 1))
                continue
            break
    raise RuntimeError(str(last_error or "reader request failed"))


def fetch_text(url: str, timeout: float, referer: str = WI_SEARCH_URL, retries: int = 2, use_reader: bool = True) -> str:
    if use_reader:
        return fetch_reader_text(url, timeout=timeout, retries=retries)
    return fetch_direct_text(url, timeout=timeout, referer=referer, retries=retries)


def table_rows(source: str) -> Iterable[str]:
    match = re.search(
        r"<table[^>]+id=[\"']ctl00_cphMainContent_OrgCredentialSearch_gvCredentialSearchResults[\"'][^>]*>([\s\S]*?)</table>",
        source,
        flags=re.I,
    )
    if not match:
        return []
    return re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", match.group(1), flags=re.I)


def row_cells(row_html: str) -> list[str]:
    return [
        clean_text(cell)
        for cell in re.findall(r"<t[dh][^>]*>([\s\S]*?)</t[dh]>", row_html or "", flags=re.I)
    ]


def parse_result_rows(source: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for row_html in table_rows(source):
        cells = row_cells(row_html)
        if len(cells) < 6:
            continue
        license_number, profession, registry_name, location, granted_date, expiration_date = cells[:6]
        if not re.search(r"Charitable\s+Organization", profession or "", re.I):
            continue
        if re.search(r"^License#?$", license_number or "", re.I):
            continue
        href_match = re.search(r"<a[^>]+href=[\"']([^\"']+)[\"']", row_html or "", flags=re.I)
        detail_url = urljoin(WI_SEARCH_URL, html.unescape(href_match.group(1))) if href_match else ""
        records.append({
            "license_number": license_number.strip(),
            "license_digits": re.sub(r"\D", "", license_number.split("-", 1)[0] if license_number else ""),
            "registry_name": registry_name.strip(),
            "location": location.strip(),
            "granted_date": granted_date.strip(),
            "expiration_date": expiration_date.strip(),
            "detail_url": detail_url,
        })
    return records


def markdown_link_parts(value: str) -> tuple[str, str]:
    match = re.search(r"\[([^\]]+)\]\(([^)]+)\)", value or "")
    if match:
        return html.unescape(match.group(1)).strip(), html.unescape(match.group(2)).strip()
    return html.unescape(value or "").strip(), ""


def parse_markdown_result_rows(source: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for line in (source or "").splitlines():
        text = line.strip()
        if not text.startswith("|"):
            continue
        cells = [cell.strip() for cell in text.strip("|").split("|")]
        if len(cells) < 6:
            continue
        license_number, profession, registry_cell, location, granted_date, expiration_date = cells[:6]
        if re.match(r"^-+$", license_number or "") or re.search(r"^License#?$", license_number or "", re.I):
            continue
        if not re.search(r"Charitable\s+Organization", profession or "", re.I):
            continue
        registry_name, detail_url = markdown_link_parts(registry_cell)
        records.append({
            "license_number": license_number.strip(),
            "license_digits": re.sub(r"\D", "", license_number.split("-", 1)[0] if license_number else ""),
            "registry_name": registry_name.strip(),
            "location": location.strip(),
            "granted_date": granted_date.strip(),
            "expiration_date": expiration_date.strip(),
            "detail_url": detail_url,
        })
    return records


def parse_search_results(source: str) -> list[dict[str, str]]:
    return parse_result_rows(source) or parse_markdown_result_rows(source)


def search_license_number(license_number: int, timeout: float, use_reader: bool) -> list[dict[str, str]]:
    url = f"{WI_RESULTS_URL}?{urlencode({'CredentialType': '800', 'FirmName': '', 'LicenseNumber': str(license_number)})}"
    return parse_search_results(fetch_text(url, timeout=timeout, use_reader=use_reader))


def text_by_id(source: str, element_id: str) -> str:
    match = re.search(
        rf"<[^>]+id=[\"'][^\"']*{re.escape(element_id)}[\"'][^>]*>([\s\S]*?)</[^>]+>",
        source or "",
        flags=re.I,
    )
    return clean_text(match.group(1)) if match else ""


def parse_other_names(source: str) -> list[str]:
    names: list[str] = []
    table_match = re.search(r"<table[^>]+id=[\"'][^\"']*rpOtherNames[^\"']*[\"'][^>]*>([\s\S]*?)</table>", source or "", flags=re.I)
    if table_match:
        for cell in re.findall(r"<t[dh][^>]*>([\s\S]*?)</t[dh]>", table_match.group(1), flags=re.I):
            value = clean_text(cell)
            if value and not re.search(r"^Other\s+Names?$", value, re.I) and value not in names:
                names.append(value)
    return names


def parse_reader_detail_names(body: str) -> tuple[str, list[str]]:
    full_name = ""
    other_names: list[str] = []
    full_match = re.search(r"\bName:\s*(.+?)\s+Credential\s+Type:", body or "", flags=re.I)
    if full_match:
        full_name = re.sub(r"\s+", " ", full_match.group(1)).strip()
    other_match = re.search(r"\bOther\s+Names:\s*(.+?)(?:\s+(?:[A-Z][A-Za-z]+\s*){1,4}:|$)", body or "", flags=re.I)
    if other_match:
        raw = re.sub(r"\s+", " ", other_match.group(1)).strip()
        if raw and not re.fullmatch(r"NONE|N/A", raw, flags=re.I):
            other_names = [part.strip() for part in re.split(r"\s*;\s*|\s*\|\s*", raw) if part.strip()]
    return full_name, other_names


def parse_detail(source: str) -> dict[str, object]:
    body = clean_text(source)
    status = text_by_id(source, "lblLicenseStatus")
    if not status:
        match = re.search(r"\bStatus\s+(License\s+is\s+(?:not\s+)?current\s*\([^)]+\))", body, flags=re.I)
        status = re.sub(r"\s+", " ", match.group(1)).strip() if match else ""
    full_name = text_by_id(source, "lblFullName")
    reader_full_name, reader_other_names = parse_reader_detail_names(body)
    if not full_name:
        full_name = reader_full_name
    other_names = parse_other_names(source)
    for name in reader_other_names:
        if name and name not in other_names:
            other_names.append(name)
    return {
        "full_name": full_name,
        "detail_status": status,
        "other_names": other_names,
    }


def fetch_detail(detail_url: str, timeout: float, use_reader: bool) -> dict[str, object]:
    if not detail_url:
        return {}
    return parse_detail(fetch_text(detail_url, timeout=timeout, referer=WI_RESULTS_URL, use_reader=use_reader))


def merge_record(target: dict[str, object], row: dict[str, str]) -> None:
    for key in ["license_number", "license_digits", "detail_url"]:
        target.setdefault(key, row.get(key, ""))
    target.setdefault("registry_names", [])
    target.setdefault("locations", [])
    target.setdefault("granted_dates", [])
    target.setdefault("expiration_date", "")
    for key, list_key in [("registry_name", "registry_names"), ("location", "locations"), ("granted_date", "granted_dates")]:
        value = row.get(key, "").strip()
        values = target[list_key]
        if value and isinstance(values, list) and value not in values:
            values.append(value)
    if row.get("expiration_date") and not target.get("expiration_date"):
        target["expiration_date"] = row["expiration_date"]


def build_snapshot(args: argparse.Namespace) -> dict[str, object]:
    license_numbers = args.license_numbers or list(range(args.start_license, args.max_license + 1))
    merged: dict[str, dict[str, object]] = {}
    errors: list[str] = []
    started = time.perf_counter()

    def scan_one(number: int) -> tuple[int, list[dict[str, str]], str]:
        try:
            return number, search_license_number(number, args.timeout, args.reader), ""
        except Exception as exc:
            return number, [], str(exc)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(scan_one, number) for number in license_numbers]
        for index, future in enumerate(as_completed(futures), start=1):
            number, rows, error = future.result()
            if error:
                errors.append(f"{number}: {error}")
            for row in rows:
                key = row.get("detail_url") or row.get("license_number") or f"license:{number}"
                record = merged.setdefault(key, {})
                merge_record(record, row)
            if args.progress and (index % args.progress == 0 or index == len(futures)):
                elapsed = time.perf_counter() - started
                print(f"scanned {index}/{len(futures)} licenses, records={len(merged)}, errors={len(errors)}, elapsed={elapsed:.1f}s", file=sys.stderr)

    if errors and not args.allow_errors:
        raise RuntimeError(f"Wisconsin snapshot scan had {len(errors)} errors; keeping prior snapshot. First error: {errors[0]}")

    records = list(merged.values())
    if not args.skip_details:
        detail_errors: list[str] = []

        def enrich(record: dict[str, object]) -> tuple[dict[str, object], str]:
            try:
                detail = fetch_detail(str(record.get("detail_url") or ""), args.timeout, args.reader)
                record.update(detail)
                names = record.setdefault("registry_names", [])
                if isinstance(names, list):
                    for value in [detail.get("full_name"), *(detail.get("other_names") or [])]:
                        if isinstance(value, str) and value and value not in names:
                            names.append(value)
                return record, ""
            except Exception as exc:
                return record, str(exc)

        with ThreadPoolExecutor(max_workers=args.detail_workers) as executor:
            futures = [executor.submit(enrich, record) for record in records if record.get("detail_url")]
            for index, future in enumerate(as_completed(futures), start=1):
                record, error = future.result()
                if error:
                    detail_errors.append(f"{record.get('license_number')}: {error}")
                if args.progress and (index % args.progress == 0 or index == len(futures)):
                    elapsed = time.perf_counter() - started
                    print(f"details {index}/{len(futures)}, detail_errors={len(detail_errors)}, elapsed={elapsed:.1f}s", file=sys.stderr)
        if detail_errors and not args.allow_errors:
            raise RuntimeError(f"Wisconsin detail scan had {len(detail_errors)} errors; keeping prior snapshot. First error: {detail_errors[0]}")
        errors.extend(detail_errors)

    records.sort(key=lambda item: (int(str(item.get("license_digits") or "0") or 0), str(item.get("license_number") or "")))
    return {
        "state": "WI",
        "complete": not errors,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "search_url": WI_SEARCH_URL,
            "results_url": WI_RESULTS_URL,
            "method": (
                "Official Wisconsin DFI charitable organization credential-number result and detail pages"
                + (" fetched through a text-reader fallback when direct pages require verification." if args.reader else ".")
            ),
        },
        "scan": {
            "start_license": args.start_license,
            "max_license": args.max_license,
            "license_count": len(license_numbers),
            "record_count": len(records),
            "errors": errors[:50],
            "error_count": len(errors),
            "details_included": not args.skip_details,
        },
        "records": records,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Wisconsin CharityClarity local registry snapshot.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--start-license", type=int, default=1)
    parser.add_argument("--max-license", type=int, default=int(os.environ.get("CE_WI_SNAPSHOT_MAX_LICENSE", "30000")))
    parser.add_argument("--workers", type=int, default=int(os.environ.get("CE_WI_SNAPSHOT_WORKERS", "8")))
    parser.add_argument("--detail-workers", type=int, default=int(os.environ.get("CE_WI_SNAPSHOT_DETAIL_WORKERS", "8")))
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("CE_WI_SNAPSHOT_TIMEOUT_SECONDS", "20")))
    parser.add_argument("--progress", type=int, default=500)
    parser.add_argument("--skip-details", action="store_true")
    parser.add_argument("--allow-errors", action="store_true")
    parser.add_argument("--direct", dest="reader", action="store_false", help="Fetch Wisconsin DFI pages directly instead of through the text-reader fallback.")
    parser.set_defaults(reader=True)
    parser.add_argument("--license", dest="license_numbers", type=int, action="append", help="Scan only this license number; can be repeated.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    snapshot = build_snapshot(args)
    if not snapshot["records"]:
        raise RuntimeError("Wisconsin snapshot produced zero records; keeping prior snapshot.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp_path = args.output.with_suffix(args.output.suffix + ".tmp")
    temp_path.write_text(json.dumps(snapshot, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(args.output)
    print(f"Wisconsin snapshot written: {args.output} ({snapshot['scan']['record_count']} records, complete={snapshot['complete']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
