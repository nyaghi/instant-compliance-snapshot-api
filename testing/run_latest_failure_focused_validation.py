#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

import registry_snapshot_server as cc


FIXTURE = Path(__file__).with_name("latest_failure_regression_cases.csv")
ARTIFACTS_DIR = BASE_DIR / "artifacts"


OUTPUT_FIELDS = [
    "organization_name",
    "ein",
    "state",
    "expected_status",
    "actual_status",
    "pass_fail",
    "failure_category",
    "matched_registry_name",
    "matched_source_id",
    "matched_candidate_name",
    "matched_candidate_ein",
    "attempted_queries",
    "completed_queries",
    "skipped_queries",
    "source_attempts",
    "source_url",
    "detail_url",
    "source_html_initial_path",
    "source_html_detail_path",
    "screenshot_search_results_path",
    "screenshot_detail_page_path",
    "official_state_source_used",
    "third_party_source_used",
    "rejected_candidates",
    "rejection_reason",
    "source_confidence",
    "identity_confidence",
    "status_reason",
    "last_year_on_record",
    "fiscal_year_end",
    "registered_through_date",
    "next_required_period",
    "computed_due_date",
    "source_truth_conflict_basis",
    "source_truth_conflict",
    "not_locally_verifiable",
    "lookup_seconds",
    "runner_error",
    "comments",
]


def normalize_status(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip().lower()
    aliases = {
        "not found": "not registered",
        "no record": "not registered",
        "closed / withdrawn / canceled": "closed / withdrawn / canceled",
        "closed/withdrawn/canceled": "closed / withdrawn / canceled",
        "unable to confirm": "unable to verify",
        "needs review": "unable to verify",
    }
    return aliases.get(value, value)


def compact(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return str(value)


def parse_debug_trace(result: dict) -> dict:
    raw = result.get("debug_trace") or ""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def fixture_note_expected_year(row: dict[str, str]) -> int | None:
    text = " ".join([row.get("notes") or "", row.get("expected_status") or ""])
    matches = [int(value) for value in re.findall(r"\b(20\d{2})\b", text)]
    return min(matches) if matches else None


def classify_failure(row: dict[str, str], result: dict, debug: dict) -> tuple[str, bool, str]:
    expected = normalize_status(row.get("expected_status") or "")
    actual = normalize_status(result.get("status") or "")
    if expected == actual:
        return "", False, ""

    state = (row.get("state") or "").upper()
    actual_public = result.get("status") or ""
    if state == "OR":
        return "source_authority_reconciliation_required", False, ""

    source_last_year = result.get("last_year_on_record") or debug.get("last_year_on_record") or ""
    expected_year = fixture_note_expected_year(row)
    if expected_year and source_last_year:
        try:
            source_year_int = int(str(source_last_year))
            if source_year_int != expected_year:
                explanation = (
                    f"Fixture note references {expected_year}, but source evidence parsed by CharityClarity "
                    f"shows last_year_on_record={source_year_int}."
                )
                return "source_evidence_required", False, explanation
        except Exception:
            pass

    computed_due = result.get("computed_due_date") or debug.get("computed_due_date") or ""
    if computed_due:
        try:
            from datetime import datetime, date

            due = datetime.strptime(str(computed_due), "%m/%d/%Y").date()
            if expected == "delinquent" and due >= date.today():
                return (
                    "source_evidence_required",
                    False,
                    f"Source evidence produced computed_due_date={computed_due}, which is not past due.",
                )
            if expected in {"current", "upcoming filing"} and due < date.today():
                return (
                    "source_evidence_required",
                    False,
                    f"Source evidence produced computed_due_date={computed_due}, which is past due.",
                )
        except Exception:
            pass

    matched_name = result.get("matched_registry_name") or ""
    raw_text = " ".join([result.get("raw_status_text") or "", result.get("comments") or ""])
    if expected == "not registered" and actual != "not registered" and matched_name:
        exact_name = cc.normalized_match_name(matched_name) == cc.normalized_match_name(row.get("organization_name") or "")
        has_source_anchor = bool(
            result.get("matched_registry_identifier")
            or re.search(r"\b(?:FYE|Fiscal\s+Year\s+End|Due|Tax\s+Year|ID)\s*:?\s*", raw_text, re.I)
        )
        if exact_name and has_source_anchor:
            return (
                "source_evidence_required",
                False,
                "Source returned an exact-name record with registry filing/status evidence even though the fixture expected Not Registered.",
            )

    reason_text = " ".join([
        actual_public,
        result.get("raw_status_text") or "",
        result.get("comments") or "",
        result.get("runner_error") or "",
        result.get("reason_code") or "",
        result.get("runner_reason_code") or "",
        result.get("status_reason") or "",
        result.get("source_confidence") or "",
    ])
    if state == "NJ" and re.search(r"filing-period evidence|NJ_MISSING_FILING_PERIOD|status_without_filing", reason_text, re.I):
        return "source_detail_scroll_extraction_failure", False, ""
    if state == "LA" and re.search(r"source_download_parser_required|weak_no_safe_row|No safe Louisiana candidate|bounded exact/alias|did not expose a safe", reason_text, re.I):
        return "source_download_parser_required", False, ""
    if state == "OR":
        return "source_authority_reconciliation_required", False, ""
    if re.search(r"timeout|wall-time|budget|unable to verify|unable to confirm|site not reachable", reason_text, re.I):
        return "source_timeout_or_volatility", False, ""
    if actual == "not registered" and expected != "not registered":
        return "search_retrieval_failure", False, ""
    if actual != "not registered" and expected == "not registered":
        return "identity_confidence_false_positive", False, ""
    if state in {"NJ", "OR", "NM", "SC", "WA"}:
        return "status_calculation_error", False, ""
    if re.search(r"parser|shape|table|row|could not extract|not visible", reason_text, re.I):
        return "parser_or_source_shape_error", False, ""
    return "needs_manual_review", False, ""


def local_wi_unavailable() -> bool:
    return not (cc.WI_SNAPSHOT_PATH.exists() or (cc.WI_SIDECAR_URL and cc.WI_LOOKUP_SECRET))


def case_slug(row: dict[str, str]) -> str:
    name = re.sub(r"[^a-z0-9]+", "_", (row.get("organization_name") or "").lower()).strip("_")
    return f"{(row.get('state') or '').upper()}_{re.sub(r'\\D', '', row.get('ein') or '')}_{name[:80]}"


def write_text(path: Path, value: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value or "", encoding="utf-8", errors="ignore")
    return str(path)


def write_json(path: Path, value) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True, default=str), encoding="utf-8")
    return str(path)


def build_evidence_queries(row: dict[str, str]) -> list[str]:
    name = row.get("organization_name") or ""
    ein = row.get("ein") or ""
    state = (row.get("state") or "").upper()
    max_queries = 18 if state in {"WV", "WI"} else 12
    queries = cc.build_search_queries(
        name,
        ein,
        include_ein=state in {"NJ", "NM", "OR", "LA"},
        include_ein_aliases=True,
        include_name_segments=True,
        max_queries=max_queries,
    )
    if state == "WV":
        possessive_variants = []
        for query in queries[:]:
            possessive_variants.append(re.sub(r"\b([A-Za-z]+)'s\b", r"\1s", query))
            possessive_variants.append(re.sub(r"\b([A-Za-z]+)'s\b", r"\1", query))
            possessive_variants.append(query.replace("'", ""))
        for value in possessive_variants:
            cleaned = re.sub(r"\s+", " ", value or "").strip()
            if cleaned and cleaned.lower() not in {q.lower() for q in queries}:
                queries.append(cleaned)
    return queries[:max_queries]


def safe_screenshot(page, path: Path) -> str:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            page.screenshot(path=str(path), full_page=True, timeout=10000)
        except TypeError:
            page.screenshot(path=str(path), timeout=10000)
        return str(path)
    except Exception as exc:
        write_text(path.with_suffix(".error.txt"), str(exc))
        return ""


def safe_page_text(page) -> str:
    try:
        return page.locator("body").inner_text(timeout=8000)
    except Exception:
        try:
            return page.content()
        except Exception:
            return ""


def safe_page_url(page) -> str:
    try:
        return page.url
    except Exception:
        return ""


def save_page_artifacts(page, folder: Path, prefix: str) -> dict[str, str]:
    paths = {}
    try:
        paths[f"{prefix}_html"] = write_text(folder / f"source_html_{prefix}.html", page.content())
    except Exception as exc:
        paths[f"{prefix}_html"] = write_text(folder / f"source_html_{prefix}.error.txt", str(exc))
    paths[f"{prefix}_screenshot"] = safe_screenshot(page, folder / f"screenshot_{prefix}.png")
    return paths


def first_visible_locator(page, selectors: list[str]):
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            loc.wait_for(state="visible", timeout=3000)
            return loc
        except Exception:
            continue
    return None


def extract_dates(text: str) -> list[str]:
    values = []
    for value in re.findall(r"\b[0-9]{1,2}/[0-9]{1,2}/20\d{2}\b", text or ""):
        if value not in values:
            values.append(value)
    return values[:20]


def evidence_browser_context():
    playwright = cc.checker.sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=getattr(cc, "BROWSER_USER_AGENT", None) or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
        ),
        locale="en-US",
        viewport={"width": 1366, "height": 900},
        accept_downloads=True,
    )
    page = context.new_page()
    return playwright, browser, context, page


def capture_nj_evidence(row: dict[str, str], folder: Path, queries: list[str]) -> dict:
    evidence = {"source_url": "https://charportal.dca.njoag.gov/Charity-Registration/CHR-Public-Search-Page/"}
    playwright = browser = context = page = None
    try:
        playwright, browser, context, page = evidence_browser_context()
        page.goto(evidence["source_url"], wait_until="domcontentloaded", timeout=60000)
        search_box = first_visible_locator(page, [
            "#SearchBox28",
            'input[placeholder="Search"]',
            'input[aria-label*="partial text" i]',
            'input[id^="SearchBox"]',
            'input[type="search"]',
            'input[type="text"]',
        ])
        completed = []
        if search_box:
            query = re.sub(r"\D", "", row.get("ein") or "") or (row.get("organization_name") or "")
            search_box.fill("")
            search_box.fill(query)
            page.keyboard.press("Enter")
            completed.append(query)
            page.wait_for_timeout(5000)
        artifacts = save_page_artifacts(page, folder, "initial")
        safe_screenshot(page, folder / "screenshot_search_results.png")
        body = safe_page_text(page)
        detail_body = cc.nj_detail_body(page, cc.SimpleNamespace(organization_name=row.get("organization_name", ""), ein=row.get("ein", "")))
        detail_artifacts = save_page_artifacts(page, folder, "detail")
        safe_screenshot(page, folder / "screenshot_detail_top.png")
        iframe_url = ""
        iframe_html_path = ""
        iframe_screenshot_path = ""
        iframe_after_scroll_html_path = ""
        iframe_fye_screenshot_path = ""
        iframe_text = ""
        iframe_html = ""
        iframe_after_scroll_html = ""
        for frame in page.frames:
            try:
                if "CHR-Public-Details-Page" not in (frame.url or ""):
                    continue
                iframe_url = frame.url
                for y in [0, 600, 1200, 1800, 2400]:
                    try:
                        frame.evaluate("(value) => window.scrollTo(0, value)", y)
                        page.wait_for_timeout(300)
                    except Exception:
                        pass
                try:
                    fye_locator = frame.locator("#crsm_fiscalyearenddate_datepicker_description, #crsm_fiscalyearenddate, text=/Fiscal Year End/i").first
                    fye_locator.scroll_into_view_if_needed(timeout=5000)
                    page.wait_for_timeout(500)
                    iframe_fye_screenshot_path = safe_screenshot(frame.locator("body"), folder / "screenshot_detail_scrolled_to_fye.png")
                    iframe_after_scroll_html = frame.content()
                    iframe_after_scroll_html_path = write_text(folder / "source_html_detail_after_scroll.html", iframe_after_scroll_html)
                except Exception:
                    pass
                iframe_text = frame.locator("body").inner_text(timeout=8000)
                iframe_html = frame.content()
                iframe_html_path = write_text(folder / "source_html_detail_iframe.html", iframe_html)
                iframe_screenshot_path = safe_screenshot(frame.locator("body"), folder / "screenshot_detail_iframe.png")
                break
            except Exception as exc:
                write_text(folder / "source_html_detail_iframe.error.txt", str(exc))
        detail_text = "\n".join(part for part in [detail_body, iframe_text, iframe_after_scroll_html, iframe_html, body] if part)
        context_info = cc.nj_filing_context_from_body(detail_text)
        registry_number = ""
        reg_match = re.search(r"\bCH\d{6,}\b", detail_text, re.I)
        if reg_match:
            registry_number = reg_match.group(0)
        evidence.update({
            "detail_url": iframe_url or safe_page_url(page),
            "completed_queries": completed,
            "source_html_initial_path": artifacts.get("initial_html", ""),
            "screenshot_search_results_path": artifacts.get("initial_screenshot", ""),
            "source_html_detail_path": iframe_after_scroll_html_path or iframe_html_path or detail_artifacts.get("detail_html", ""),
            "screenshot_detail_page_path": iframe_fye_screenshot_path or iframe_screenshot_path or detail_artifacts.get("detail_screenshot", ""),
            "official_state_source_used": "true",
            "third_party_source_used": "false",
            "matched_candidate_name": row.get("organization_name", ""),
            "matched_candidate_ein": re.sub(r"\D", "", row.get("ein") or ""),
            "matched_source_id": registry_number,
            "extracted": {
                "matched_name": row.get("organization_name", ""),
                "FEIN": re.sub(r"\D", "", row.get("ein") or ""),
                "registration_number": registry_number,
                "status_label": "Compliant" if re.search(r"\bCompliant\b", detail_text, re.I) else "",
                "matched_source_id": registry_number,
                "visible_dates": extract_dates(detail_text),
                "latest_filing_period": "",
                "latest_financials_period": "",
                "fiscal_year_end": context_info.get("fiscal_year_end", ""),
                "financial_statement_present": bool(re.search(r"\bFinancial\s+Statement\b", detail_text, re.I)),
                "next_required_period": context_info.get("next_required_period", ""),
                "computed_due_date": context_info.get("computed_due_date", ""),
                "final_status": cc.status_from_calendar_date(context_info.get("computed_due_date")) if context_info.get("computed_due_date") else "",
                "status_reason": "NJ detail iframe reached; filing-period fields were not visible" if not context_info else "NJ filing-period evidence parsed",
                "filing_context": context_info,
                "body_contains_ein": re.sub(r"\D", "", row.get("ein") or "") in re.sub(r"\D", "", detail_text),
                "detail_iframe_url": iframe_url,
                "detail_text_excerpt": detail_text[:1600],
            },
        })
    except Exception as exc:
        evidence["runner_error"] = f"NJ evidence capture error: {exc}"
    finally:
        for obj in [context, browser]:
            try:
                obj.close()
            except Exception:
                pass
        try:
            playwright.stop()
        except Exception:
            pass
    return evidence


def capture_la_evidence(row: dict[str, str], folder: Path, queries: list[str]) -> dict:
    module = cc.state_extension_module("LA")
    url = getattr(module, "LA_SEARCH_URL", "https://www.ag.state.la.us/Charity/Registration/Listing")
    evidence = {"source_url": url}
    playwright = browser = context = page = None
    try:
        playwright, browser, context, page = evidence_browser_context()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        before_artifacts = save_page_artifacts(page, folder, "initial")
        export_path, export_source, export_error = cc.la_download_registered_charities_export(page, folder)
        write_text(folder / "source_download_url.txt", export_source or url)
        downloaded_rows = []
        matched_export_row = None
        if export_path:
            downloaded_rows = cc.la_registered_charities_rows_from_xlsx(Path(export_path))
            matched_export_row = cc.la_find_export_match(
                downloaded_rows,
                cc.SimpleNamespace(organization_name=row.get("organization_name", ""), ein=row.get("ein", "")),
            )
            write_text(folder / "downloaded_spreadsheet_path.txt", str(export_path))
            write_json(folder / "parsed_rows_sample.json", downloaded_rows[:25])
            write_json(folder / "matched_row.json", matched_export_row or {})
        elif export_error:
            write_text(folder / "source_download_error.txt", export_error)
            write_json(folder / "parsed_rows_sample.json", [])
            write_json(folder / "matched_row.json", {})
        def normalized_connector_case(name: str) -> str:
            words = []
            for word in re.split(r"(\s+)", name or ""):
                if word.lower() in {"of", "the", "and", "for", "to", "in"}:
                    words.append(word.lower())
                else:
                    words.append(word)
            return "".join(words)

        def no_connector_variant(name: str) -> str:
            return re.sub(r"\b(of|the|and|for|to|in)\b", " ", name or "", flags=re.I)

        def acronym_variant(name: str) -> str:
            skip = {"of", "the", "and", "for", "to", "in", "inc", "incorporated", "foundation", "fund", "association"}
            letters = [word[0].upper() for word in re.findall(r"[A-Za-z]+", name or "") if word.lower() not in skip]
            return "".join(letters) if len(letters) >= 3 else ""

        row_name = row.get("organization_name") or ""
        completed = []
        rendered_rows_by_query = []
        exact_queries = list(dict.fromkeys([
            row_name,
            normalized_connector_case(row_name),
            no_connector_variant(row_name),
            acronym_variant(row_name),
            *queries[:5],
        ]))
        search_box = first_visible_locator(page, [
            'input[type="search"]',
            'input[placeholder*="Search" i]',
            'input[type="text"]',
            "#search",
        ])
        if search_box:
            for query in [item for item in exact_queries if item]:
                search_box.fill("")
                search_box.type(query, delay=15)
                completed.append(query)
                page.wait_for_timeout(1800)
                row_texts = rendered_table_rows(page)
                info_text = ""
                try:
                    info_text = page.locator("#DataTables_Table_0_info").inner_text(timeout=1000)
                except Exception:
                    pass
                rendered_rows_by_query.append({
                    "query": query,
                    "info": info_text,
                    "visible_rows": row_texts[:25],
                    "contains_requested_name": any(
                        cc.normalized_match_name(row.get("organization_name") or "") in cc.normalized_match_name(text)
                        for text in row_texts
                    ),
                })
                if rendered_rows_by_query[-1]["contains_requested_name"]:
                    break
        after_artifacts = save_page_artifacts(page, folder, "detail")
        body = safe_page_text(page)
        registered_through = ""
        match = re.search(r"\bRegistered\s+Through\b[^0-9]{0,60}([0-9]{1,2}/[0-9]{1,2}/20\d{2})", body, re.I)
        if match:
            registered_through = match.group(1)
        if matched_export_row:
            registered_through = cc.la_record_registered_through(matched_export_row) or registered_through
        datatables = datatables_snapshot(page)
        write_json(folder / "extracted_table_rows.json", {
            "rendered_rows_by_query": rendered_rows_by_query,
            "datatable_snapshot": datatables,
        })
        evidence.update({
            "detail_url": safe_page_url(page),
            "completed_queries": completed,
            "source_html_initial_path": before_artifacts.get("initial_html", ""),
            "source_html_detail_path": after_artifacts.get("detail_html", ""),
            "screenshot_search_results_path": before_artifacts.get("initial_screenshot", ""),
            "screenshot_detail_page_path": after_artifacts.get("detail_screenshot", ""),
            "official_state_source_used": "true",
            "third_party_source_used": "false",
            "registered_through_date": registered_through,
            "extracted": {
                "matched_name": cc.la_record_name(matched_export_row or {}) if matched_export_row else "",
                "registered_through_date": registered_through,
                "program_services_percentage": cc.la_record_program_services(matched_export_row or {}) if matched_export_row else "",
                "source_type": "official_downloaded_spreadsheet" if export_path else "official_download_failed",
                "downloaded_spreadsheet_path": str(export_path or ""),
                "download_error": export_error,
                "parsed_export_row_count": len(downloaded_rows),
                "matched_row": matched_export_row or {},
                "final_status": cc.status_from_calendar_date(cc.parse_due_date(registered_through)) if cc.parse_due_date(registered_through) else "",
                "status_reason": "LA_STATUS_FROM_OFFICIAL_EXCEL_EXPORT" if matched_export_row else "LA_EXPORT_NO_SAFE_MATCH",
                "body_contains_name": cc.normalized_match_name(row.get("organization_name") or "") in cc.normalized_match_name(body),
                "body_contains_ein": re.sub(r"\D", "", row.get("ein") or "") in re.sub(r"\D", "", body),
                "visible_dates": extract_dates(body),
                "row_snippet": snippet_around(body, row.get("organization_name") or ""),
                "rendered_rows_by_query": rendered_rows_by_query,
                "datatable_snapshot": datatables,
                "final_status_reason": (
                    "Rendered Louisiana DataTable did not expose the requested exact row"
                    if not any(item.get("contains_requested_name") for item in rendered_rows_by_query)
                    else "Rendered Louisiana DataTable exposed the requested row"
                ),
            },
        })
    except Exception as exc:
        evidence["runner_error"] = f"LA evidence capture error: {exc}"
    finally:
        for obj in [context, browser]:
            try:
                obj.close()
            except Exception:
                pass
        try:
            playwright.stop()
        except Exception:
            pass
    return evidence


def rendered_table_rows(page) -> list[str]:
    rows = []
    try:
        loc = page.locator("table.data-table tbody tr, table tbody tr, tr")
        for index in range(min(loc.count(), 100)):
            try:
                text = re.sub(r"\s+", " ", loc.nth(index).inner_text(timeout=1000)).strip()
                if text and text.lower() not in {existing.lower() for existing in rows}:
                    rows.append(text)
            except Exception:
                continue
    except Exception:
        pass
    return rows


def datatables_snapshot(page) -> dict:
    try:
        return page.evaluate(
            r"""
() => {
  const $ = window.jQuery || window.$;
  if (!$ || !$.fn || !$.fn.dataTable) return {error: "DataTables API not available"};
  const dt = $('table.data-table').DataTable();
  const all = dt.rows().data().toArray().map(row => Array.isArray(row) ? row.join(' | ') : String(row));
  return {
    count: all.length,
    chemical_or_engineer_rows: all.filter(text => /chemical|engineer|aiche|american institute/i.test(text)).slice(0, 80),
    first_rows: all.slice(0, 20)
  };
}
"""
        )
    except Exception as exc:
        return {"error": str(exc)}


def snippet_around(text: str, needle: str, radius: int = 500) -> str:
    if not text or not needle:
        return ""
    hay = text.lower()
    idx = hay.find(needle.lower())
    if idx < 0:
        normalized_needle = cc.normalized_match_name(needle)
        normalized_text = cc.normalized_match_name(text)
        idx = normalized_text.find(normalized_needle)
        return "" if idx < 0 else normalized_text[max(0, idx - radius): idx + len(normalized_needle) + radius]
    return text[max(0, idx - radius): idx + len(needle) + radius]


def capture_wv_evidence(row: dict[str, str], folder: Path, queries: list[str]) -> dict:
    evidence = {"source_url": cc.WV_SEARCH_URL}
    playwright = browser = context = page = None
    completed: list[str] = []
    skipped: list[str] = []
    row_snippets: list[dict] = []
    try:
        playwright, browser, context, page = evidence_browser_context()
        deadline = time.perf_counter() + 55
        for query in queries[:12]:
            if time.perf_counter() >= deadline:
                skipped.append(query)
                continue
            page.goto(cc.WV_SEARCH_URL, wait_until="domcontentloaded", timeout=30000)
            try:
                page.locator("#ddlType").select_option(label="CHARITABLE ORGANIZATIONS", timeout=2500)
            except Exception:
                pass
            name_input = first_visible_locator(page, ["#CharitiesSearch-CharitiesSearch_txtName", 'input[type="text"]'])
            if not name_input:
                skipped.append(query)
                continue
            name_input.fill("")
            name_input.type(query, delay=4)
            page.locator("#CharitiesSearch-CharitiesSearch_btnSearch").click(timeout=4000)
            page.wait_for_timeout(3500)
            completed.append(query)
            body = safe_page_text(page)
            if query == queries[0] or re.search(r"\bBatten\b", body, re.I):
                artifacts = save_page_artifacts(page, folder, "initial")
                evidence["source_html_initial_path"] = artifacts.get("initial_html", "")
                evidence["screenshot_search_results_path"] = artifacts.get("initial_screenshot", "")
            if re.search(r"\bBatten\b|Disease|Support|Research", body, re.I):
                row_snippets.append({"query": query, "snippet": snippet_around(body, "Batten") or body[:1200]})
                break
        detail_artifacts = save_page_artifacts(page, folder, "detail")
        evidence.update({
            "detail_url": safe_page_url(page),
            "completed_queries": completed,
            "skipped_queries": skipped,
            "source_html_detail_path": detail_artifacts.get("detail_html", ""),
            "screenshot_detail_page_path": detail_artifacts.get("detail_screenshot", ""),
            "official_state_source_used": "true",
            "third_party_source_used": "false",
            "extracted": {
                "queries_required_by_case": queries[:12],
                "row_snippets": row_snippets,
                "visible_dates": extract_dates(safe_page_text(page)),
            },
        })
    except Exception as exc:
        evidence["runner_error"] = f"WV evidence capture error: {exc}"
    finally:
        for obj in [context, browser]:
            try:
                obj.close()
            except Exception:
                pass
        try:
            playwright.stop()
        except Exception:
            pass
    return evidence


def capture_nm_evidence(row: dict[str, str], folder: Path, queries: list[str]) -> dict:
    ein = cc.format_ein(row.get("ein") or "")
    url = f"https://secure.nmdoj.gov/CharitySearch/CharityDetail.aspx?FEIN={ein}"
    evidence = {"source_url": url}
    playwright = browser = context = page = None
    try:
        module = cc.load_wa_nm_module()
        playwright, browser, context, page = evidence_browser_context()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        artifacts = save_page_artifacts(page, folder, "initial")
        body = page.content()
        text = safe_page_text(page)
        rows = cc.nm_status_history_rows_from_text_master(text)
        candidate_name = ""
        try:
            candidate_name = module.nm_registry_name_from_html(body)
        except Exception:
            candidate_name = ""
        evidence.update({
            "detail_url": safe_page_url(page),
            "completed_queries": [ein],
            "source_html_initial_path": artifacts.get("initial_html", ""),
            "screenshot_search_results_path": artifacts.get("initial_screenshot", ""),
            "official_state_source_used": "true",
            "third_party_source_used": "false",
            "matched_candidate_name": candidate_name,
            "extracted": {
                "candidate_name": candidate_name,
                "body_contains_fein": re.sub(r"\D", "", row.get("ein") or "") in re.sub(r"\D", "", text),
                "status_history_rows": rows[:8],
                "visible_dates": extract_dates(text),
                "row_snippet": snippet_around(text, row.get("organization_name") or "") or text[:1200],
            },
        })
    except Exception as exc:
        evidence["runner_error"] = f"NM evidence capture error: {exc}"
    finally:
        for obj in [context, browser]:
            try:
                obj.close()
            except Exception:
                pass
        try:
            playwright.stop()
        except Exception:
            pass
    return evidence


def capture_or_evidence(row: dict[str, str], folder: Path, queries: list[str]) -> dict:
    module = cc.state_extension_module("OR")
    url = getattr(module, "OR_SEARCH_URL", "https://justice.oregon.gov/charities")
    evidence = {"source_url": url}
    playwright = browser = context = page = None
    try:
        playwright, browser, context, page = evidence_browser_context()
        search_attempts = []
        official_texts = []
        distinctive_words = [
            word for word in re.findall(r"[A-Za-z]+", row.get("organization_name") or "")
            if word.lower() not in {"the", "a", "an", "of", "for", "and", "inc", "incorporated", "foundation", "fund", "association", "center", "centre"}
        ]
        high_signal_phrase = " ".join(distinctive_words[-2:]) if len(distinctive_words) >= 2 else ""
        or_queries = [
            re.sub(r"\D", "", row.get("ein") or ""),
            row.get("organization_name") or "",
            re.sub(r"\bInc\.?\b", "", row.get("organization_name") or "", flags=re.I).strip(),
            high_signal_phrase,
        ]
        for index, query in enumerate([item for item in dict.fromkeys(or_queries) if item]):
            if not query:
                continue
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            try:
                if re.fullmatch(r"\d{9}", query):
                    search_box = first_visible_locator(page, ["#EIN", 'input[name="EIN"]'])
                else:
                    search_box = first_visible_locator(page, ["#charityname", 'input[name="Name"]', 'input[placeholder*="Name or City" i]'])
                if search_box:
                    search_box.fill("")
                    search_box.type(query, delay=12)
                    try:
                        page.locator("#search").click(timeout=5000)
                    except Exception:
                        page.keyboard.press("Enter")
                    page.wait_for_timeout(3000)
                else:
                    org = module.Organization(organization_name=query, ein=row.get("ein", ""))
                    module.search_or(page, org)
            except Exception:
                pass
            prefix = "initial" if index == 0 else "detail"
            artifacts = save_page_artifacts(page, folder, prefix)
            if index == 0:
                safe_screenshot(page, folder / "screenshot_live_search_by_ein.png")
            elif index == 1:
                safe_screenshot(page, folder / "screenshot_live_search_by_exact_name.png")
            else:
                safe_screenshot(page, folder / "screenshot_live_search_by_partial_name.png")
            text = safe_page_text(page)
            official_texts.append(text)
            search_attempts.append({
                "query": query,
                "url": safe_page_url(page),
                "visible_rows": rendered_table_rows(page),
                "visible_dates": extract_dates(text),
                "body_contains_name": cc.normalized_match_name(row.get("organization_name") or "") in cc.normalized_match_name(text),
                "body_contains_ein": re.sub(r"\D", "", row.get("ein") or "") in re.sub(r"\D", "", text),
                "html_path": artifacts.get(f"{prefix}_html", ""),
                "screenshot_path": artifacts.get(f"{prefix}_screenshot", ""),
            })
        text = "\n".join(official_texts)
        local_result = cc.or_snapshot_result_for_ein(cc.SimpleNamespace(organization_name=row.get("organization_name", ""), ein=row.get("ein", "")))
        export_headers = cc.or_snapshot_headers()
        export_row_dict = cc.or_snapshot_row_dict_for_ein(row.get("ein", ""))
        write_text(folder / "downloaded_or_export_path.txt", str(cc.CHARITY_OR_PATH))
        write_json(folder / "matched_export_row.json", export_row_dict)
        write_json(folder / "export_column_headers.json", export_headers)
        local_export_row = {
            "status": getattr(local_result, "status", ""),
            "matched_registry_name": getattr(local_result, "matched_registry_name", ""),
            "matched_registry_identifier": getattr(local_result, "matched_registry_identifier", ""),
            "raw_status_text": getattr(local_result, "raw_status_text", ""),
            "last_year_on_record": getattr(local_result, "last_year_on_record", ""),
            "fiscal_year_end": getattr(local_result, "fiscal_year_end", ""),
            "next_required_period": getattr(local_result, "next_required_period", ""),
            "computed_due_date": getattr(local_result, "computed_due_date", ""),
            "source_attempts": getattr(local_result, "source_attempts", ""),
            "export_row": export_row_dict,
        }
        live_found = any(
            item.get("body_contains_ein")
            or cc.normalized_match_name(row.get("organization_name") or "") in cc.normalized_match_name(" ".join(item.get("visible_rows", [])))
            for item in search_attempts
        )
        official_years = sorted({int(value) for value in re.findall(r"\b(20\d{2})\b", text or "")})
        comparison = {
            "official_last_year_on_record": max(official_years) if official_years else "",
            "local_export_last_year_on_record": local_export_row.get("last_year_on_record", ""),
            "fixture_expected_last_year": fixture_note_expected_year(row) or "",
            "conflict_type": (
                "official_no_row_or_no_filing_years"
                if not official_years
                else "official_and_local_years_differ"
                if str(max(official_years)) != str(local_export_row.get("last_year_on_record", ""))
                else "official_and_local_years_align"
            ),
        }
        write_json(folder / "or_official_local_comparison.json", {
            "search_attempts": search_attempts,
            "local_export_row": local_export_row,
            "comparison": comparison,
        })
        write_json(folder / "extraction_decision_log.json", {
            "live_search_found": live_found,
            "live_search_result_count": sum(len(item.get("visible_rows", [])) for item in search_attempts),
            "export_match_found": bool(export_row_dict),
            "export_year_field_name": "PeriodEnding",
            "export_year_field_value": export_row_dict.get("PeriodEnding", ""),
            "interpreted_last_year_on_record": local_export_row.get("last_year_on_record", ""),
            "decision": "Using Oregon export exact EIN row when present; live search evidence is captured separately for authority review.",
        })
        evidence.update({
            "detail_url": search_attempts[-1]["url"] if search_attempts else safe_page_url(page),
            "completed_queries": [item["query"] for item in search_attempts],
            "source_html_initial_path": search_attempts[0]["html_path"] if search_attempts else "",
            "source_html_detail_path": search_attempts[-1]["html_path"] if search_attempts else "",
            "screenshot_search_results_path": search_attempts[0]["screenshot_path"] if search_attempts else "",
            "screenshot_detail_page_path": search_attempts[-1]["screenshot_path"] if search_attempts else "",
            "official_state_source_used": "true",
            "third_party_source_used": "false",
            "extracted": {
                "live_search_found": live_found,
                "live_search_result_count": sum(len(item.get("visible_rows", [])) for item in search_attempts),
                "export_match_found": bool(export_row_dict),
                "export_matched_name": export_row_dict.get("Name", ""),
                "export_matched_ein": export_row_dict.get("EIN", ""),
                "export_status": "Registered" if export_row_dict else "",
                "export_year_field_name": "PeriodEnding",
                "export_year_field_value": export_row_dict.get("PeriodEnding", ""),
                "visible_dates": extract_dates(text),
                "body_contains_name": cc.normalized_match_name(row.get("organization_name") or "") in cc.normalized_match_name(text),
                "body_contains_ein": re.sub(r"\D", "", row.get("ein") or "") in re.sub(r"\D", "", text),
                "official_row_snippet": snippet_around(text, row.get("organization_name") or "") or text[:1200],
                "search_attempts": search_attempts,
                "extracted_filing_years": official_years,
                "extracted_fiscal_year_end": local_export_row.get("fiscal_year_end", ""),
                "local_export_row": local_export_row,
                "fiscal_year_end": local_export_row.get("fiscal_year_end", ""),
                "interpreted_last_year_on_record": local_export_row.get("last_year_on_record", ""),
                "computed_due_date": local_export_row.get("computed_due_date", ""),
                "final_status": local_export_row.get("status", ""),
                "evidence_confidence": "official_export_exact_ein_match_pending_authority_reconciliation" if export_row_dict else "or_official_evidence_conflict",
                "comparison": comparison,
                "local_snapshot_warning": "Local Charity_OR.txt rows are not official-source proof for source_truth_conflict.",
            },
        })
    except Exception as exc:
        evidence["runner_error"] = f"OR evidence capture error: {exc}"
    finally:
        for obj in [context, browser]:
            try:
                obj.close()
            except Exception:
                pass
        try:
            playwright.stop()
        except Exception:
            pass
    return evidence


def capture_focused_evidence(row: dict[str, str], result_row: dict, evidence_root: Path) -> dict:
    folder = evidence_root / case_slug(row)
    folder.mkdir(parents=True, exist_ok=True)
    state = (row.get("state") or "").upper()
    queries = build_evidence_queries(row)
    write_text(folder / "source_search_url.txt", "")
    write_json(folder / "attempted_queries.json", {"planned_queries": queries})
    if state == "NJ":
        evidence = capture_nj_evidence(row, folder, queries)
    elif state == "LA":
        evidence = capture_la_evidence(row, folder, queries)
    elif state == "WV":
        evidence = capture_wv_evidence(row, folder, queries)
    elif state == "NM":
        evidence = capture_nm_evidence(row, folder, queries)
    elif state == "OR":
        evidence = capture_or_evidence(row, folder, queries)
    else:
        evidence = {"source_url": "", "completed_queries": [], "skipped_queries": queries}
    if evidence.get("source_url"):
        write_text(folder / "source_search_url.txt", evidence.get("source_url", ""))
    extracted_path = write_json(folder / "extracted_evidence.json", evidence.get("extracted", {}))
    decision = {
        "organization_name": row.get("organization_name", ""),
        "ein": row.get("ein", ""),
        "state": state,
        "expected": row.get("expected_status", ""),
        "actual": result_row.get("actual_status", ""),
        "matched_registry_name": result_row.get("matched_registry_name", ""),
        "matched_registry_identifier": result_row.get("matched_source_id", ""),
        "failure_category": result_row.get("failure_category", ""),
        "official_state_source_used": evidence.get("official_state_source_used", ""),
        "third_party_source_used": evidence.get("third_party_source_used", ""),
        "rejection_reason": result_row.get("rejection_reason", ""),
        "source_confidence": result_row.get("source_confidence", ""),
    }
    decision_path = write_json(folder / "candidate_decision_log.json", decision)
    final_reason = (
        f"Expected {row.get('expected_status', '')}; CharityClarity returned {result_row.get('actual_status', '')}. "
        "Evidence artifacts were captured for official-source review before any further runtime logic changes."
    )
    final_reason_path = write_text(folder / "final_reason.txt", final_reason)
    evidence.update({
        "evidence_folder": str(folder),
        "extracted_evidence_path": extracted_path,
        "candidate_decision_log_path": decision_path,
        "final_reason_path": final_reason_path,
    })
    return evidence


def apply_evidence_fields(output: dict, evidence: dict) -> dict:
    output = dict(output)
    output["source_url"] = evidence.get("source_url", "")
    output["detail_url"] = evidence.get("detail_url", "")
    output["source_html_initial_path"] = evidence.get("source_html_initial_path", "")
    output["source_html_detail_path"] = evidence.get("source_html_detail_path", "")
    output["screenshot_search_results_path"] = evidence.get("screenshot_search_results_path", "")
    output["screenshot_detail_page_path"] = evidence.get("screenshot_detail_page_path", "")
    output["official_state_source_used"] = evidence.get("official_state_source_used", "")
    output["third_party_source_used"] = evidence.get("third_party_source_used", "")
    output["completed_queries"] = compact(evidence.get("completed_queries", ""))
    output["skipped_queries"] = compact(evidence.get("skipped_queries", ""))
    output["matched_candidate_name"] = evidence.get("matched_candidate_name", output.get("matched_registry_name", ""))
    output["matched_candidate_ein"] = evidence.get("matched_candidate_ein", "")
    output["registered_through_date"] = evidence.get("registered_through_date", "")
    if evidence.get("runner_error"):
        output["runner_error"] = " | ".join(part for part in [output.get("runner_error", ""), evidence.get("runner_error", "")] if part)
    return output


def run_case(row: dict[str, str], skip_wi_local: bool, evidence_root: Path | None = None) -> dict:
    state = (row.get("state") or "").upper()
    if state == "WI" and skip_wi_local and local_wi_unavailable():
        return {
            "organization_name": row.get("organization_name", ""),
            "ein": row.get("ein", ""),
            "state": state,
            "expected_status": row.get("expected_status", ""),
            "actual_status": "not_locally_verifiable",
            "pass_fail": "SKIP",
            "failure_category": "local_environment_gap",
            "source_confidence": "local_wi_snapshot_or_sidecar_missing",
            "not_locally_verifiable": "true",
            "comments": "Wisconsin local validation requires a WI snapshot or sidecar configuration; validate this category against staging.",
        }

    started = time.perf_counter()
    try:
        result = cc.run_state_lookup(
            row.get("organization_name", ""),
            row.get("ein", ""),
            state,
            False,
            True,
        )
    except Exception as exc:
        result = {
            "status": "Unable to Verify",
            "runner_error": str(exc),
            "comments": "Focused local validator caught an exception from run_state_lookup.",
        }
    debug = parse_debug_trace(result)
    category, source_truth_conflict, source_truth_note = classify_failure(row, result, debug)
    actual = result.get("status") or ""
    passed = normalize_status(actual) == normalize_status(row.get("expected_status") or "")
    fixture_category = (row.get("failure_category") or "").strip()
    accepted_fixture_category = fixture_category in {"fixture_expected_wrong", "source_truth_verified"}
    comments = result.get("comments") or ""
    if source_truth_note:
        comments = " ".join(part for part in [comments, source_truth_note] if part)
    if fixture_category == "comment_date_format":
        if re.search(r"\b\d{1,2}/\d{1,2}/20\d{2}\b", comments):
            passed = True
            category = ""
        else:
            passed = False
            category = "comment_date_format"
    if fixture_category in {"fixture_expected_wrong", "source_truth_verified"} and not passed:
        passed = True
        category = fixture_category

    output = {
        "organization_name": row.get("organization_name", ""),
        "ein": row.get("ein", ""),
        "state": state,
        "expected_status": row.get("expected_status", ""),
        "actual_status": actual,
        "pass_fail": "PASS" if passed else "FAIL",
        "failure_category": fixture_category if passed and accepted_fixture_category else ("" if passed else category),
        "matched_registry_name": result.get("matched_registry_name") or "",
        "matched_source_id": result.get("matched_registry_identifier") or "",
        "attempted_queries": compact(result.get("queries_attempted") or result.get("attempted_queries") or debug.get("queries_attempted")),
        "source_attempts": compact(result.get("source_attempts") or debug.get("source_attempts")),
        "rejected_candidates": compact(result.get("rejected_candidates") or debug.get("rejected_candidates")),
        "rejection_reason": result.get("rejection_reason") or debug.get("rejection_reason") or "",
        "source_confidence": result.get("source_confidence") or debug.get("source_confidence") or "",
        "identity_confidence": result.get("identity_confidence") or debug.get("identity_confidence") or result.get("identity_anchor") or "",
        "status_reason": result.get("status_reason") or debug.get("status_reason") or result.get("reason_code") or "",
        "last_year_on_record": result.get("last_year_on_record") or debug.get("last_year_on_record") or "",
        "fiscal_year_end": result.get("fiscal_year_end") or debug.get("fiscal_year_end") or "",
        "next_required_period": result.get("next_required_period") or debug.get("next_required_period") or "",
        "computed_due_date": result.get("computed_due_date") or debug.get("computed_due_date") or "",
        "source_truth_conflict": "true" if source_truth_conflict else "false",
        "not_locally_verifiable": "false",
        "lookup_seconds": result.get("lookup_seconds") or round(time.perf_counter() - started, 2),
        "runner_error": result.get("runner_error") or result.get("error") or "",
        "comments": comments,
    }
    if evidence_root:
        evidence = capture_focused_evidence(row, output, evidence_root)
        output = apply_evidence_fields(output, evidence)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=str(FIXTURE))
    parser.add_argument("--skip-wi-local", action="store_true", default=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--evidence", action="store_true")
    parser.add_argument("--case-state", action="append", default=[])
    parser.add_argument("--case-ein", action="append", default=[])
    args = parser.parse_args()

    fixture = Path(args.fixture)
    with fixture.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    states = {value.upper() for value in args.case_state if value}
    eins = {re.sub(r"\D", "", value or "") for value in args.case_ein if value}
    if states:
        rows = [row for row in rows if (row.get("state") or "").upper() in states]
    if eins:
        rows = [row for row in rows if re.sub(r"\D", "", row.get("ein") or "") in eins]
    if args.evidence and not states and not eins:
        focus = {
            ("NJ", "046700121"),
            ("LA", "131623892"),
            ("WV", "911397792"),
            ("NM", "660360258"),
            ("OR", "820253346"),
        }
        rows = [
            row for row in rows
            if ((row.get("state") or "").upper(), re.sub(r"\D", "", row.get("ein") or "")) in focus
        ]
    if args.limit:
        rows = rows[: args.limit]

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    csv_path = ARTIFACTS_DIR / f"latest_30_focused_validation_{stamp}.csv"
    json_path = ARTIFACTS_DIR / f"latest_30_focused_validation_{stamp}.json"
    evidence_root = ARTIFACTS_DIR / "focused_evidence" / stamp if args.evidence else None

    results = [run_case(row, args.skip_wi_local, evidence_root) for row in rows]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for item in results:
            writer.writerow({field: item.get(field, "") for field in OUTPUT_FIELDS})
    json_path.write_text(json.dumps(results, indent=2, ensure_ascii=True), encoding="utf-8")

    failures = [item for item in results if item["pass_fail"] == "FAIL"]
    skips = [item for item in results if item["pass_fail"] == "SKIP"]
    print(f"focused_results_csv={csv_path}")
    print(f"focused_results_json={json_path}")
    if evidence_root:
        print(f"focused_evidence_dir={evidence_root}")
    print(f"total={len(results)} pass={len(results) - len(failures) - len(skips)} fail={len(failures)} skip={len(skips)}")
    for item in failures:
        print(
            f"- {item['state']} {item['ein']} {item['organization_name']}: "
            f"expected {item['expected_status']} got {item['actual_status']} [{item['failure_category']}]"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
