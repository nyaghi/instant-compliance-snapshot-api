import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

from pypdf import PdfReader
import registry_snapshot_server as c
from deployment import search_history as history, state_snapshots as snapshots
from deployment import validated_search_history as receipt


PARENT = "Geological Society of America Inc."
FOUNDATION = "THE GEOLOGICAL SOCIETY OF AMERICA FOUNDATION"
EIN = "13-1659623"
FOUNDATION_EIN = "74-2156871"
AAAS = "American Association for the Advancement of Science"


class Gate38EntityScope(unittest.TestCase):
    def test_ar_uses_record_ein_before_name_similarity(self):
        candidate = "Geological Society of America Foundation (The)"
        targets = [PARENT, candidate]  # A checked alias cannot establish identity.
        for ein, expected in [("", "unconfirmed_scope"), (EIN, "accept"), (FOUNDATION_EIN, "reject")]:
            with self.subTest(ein=ein):
                self.assertEqual(c.ar_candidate_identity(dict(name=candidate, ein=ein), PARENT, targets, EIN), expected)
        self.assertEqual(c.ar_candidate_identity(dict(name=candidate), candidate, [candidate], FOUNDATION_EIN), "accept")

    def test_ar_alias_query_preserves_original_scope(self):
        page = MagicMock()
        query = [""]
        page.locator.return_value.fill.side_effect = lambda value: query.__setitem__(0, value)
        page.get_by_role.return_value.click.side_effect = lambda **kw: setattr(page, "url", receipt.AR_RESULTS_URL + "?" + urlencode({"name": query[0]}))
        row = dict(name=FOUNDATION, status="Current", type="Charity Registration", registration_date="2023-05-01")
        org = c.org_with_name(c.checker.Organization(PARENT, EIN), FOUNDATION)
        with patch.object(c, "ar_wait_for_search_form", return_value=True), patch.object(c, "safe_wait_for_network_idle"), patch.object(c, "registry_page_body", return_value="Back to Search Form Registration Date"), patch.object(c, "ar_result_rows", return_value=[row]):
            result = c.search_ar_precise(page, org)
        self.assertFalse(result.success)
        self.assertEqual(result._cc_identity_review["records"][0]["name"], FOUNDATION)

    @staticmethod
    def ct_row(name):
        return (f'<tr><b class="headline6">{name}</b><b>Credential</b><p>CHR.0070372</p>'
                '<b>Credential Description</b><p>PUBLIC CHARITY</p><b>Status</b><p>ACTIVE</p>'
                '<b>Expiration Date</b><p>5/31/2027</p></tr>')

    def test_ct_candidate_and_verified_ein_paths(self):
        org = c.checker.Organization(PARENT, EIN)
        url = "https://www.elicense.ct.gov/lookup/licenselookup.aspx"
        targets = [PARENT, FOUNDATION]
        for detail, expected in [
            ("", "review"),
            (f"Credential CHR.0070372 Address {EIN}", "review"),
            (f"Credential CHR.0070372 EIN: {EIN}", "accept"),
            (f"Credential CHR.0070372 EIN: {FOUNDATION_EIN}", "exclude"),
            (f"Credential CHR.0000000 EIN: {EIN}", "unbound"),
        ]:
            with self.subTest(expected=expected, detail=detail), patch.object(c, "ct_direct_detail_text", return_value=detail):
                result, _ = c.ct_direct_result_from_row(org, self.ct_row(FOUNDATION), targets, url)
            if expected == "exclude":
                self.assertIsNone(result)
            elif expected == "accept":
                self.assertTrue(result.success)
            elif expected == "unbound":
                self.assertFalse(result.success)
                self.assertFalse(getattr(result, "_cc_identity_review", None))
            else:
                self.assertFalse(result.success)
                self.assertFalse(result.matched_registry_identifier)
                self.assertEqual(result._cc_identity_review["records"][0]["identifier"], "CHR.0070372")
        with patch.object(c, "ct_direct_detail_text", return_value=""):
            result, _ = c.ct_direct_result_from_row(c.checker.Organization(FOUNDATION, FOUNDATION_EIN),
                self.ct_row(FOUNDATION), [FOUNDATION], url)
        self.assertTrue(result.success)

    def test_ky_candidate_is_exclusive_and_confirmed_parent_still_wins(self):
        candidate = ("18796", FOUNDATION, "", "")
        parent = ("18801", "Geological Society of America, Inc.", "", "")
        org = c.checker.Organization(PARENT, EIN)
        with patch.object(c, "load_ky_snapshot_records", return_value=[candidate]):
            result = c.search_ky_strict_snapshot(org)
            self.assertFalse(result.success)
            self.assertFalse(result._cc_identity_review["search_complete"])
            self.assertEqual(result._cc_identity_review["records"][0]["identifier"], "18796")
            confirmed = c.search_ky_strict_snapshot(c.checker.Organization(FOUNDATION, FOUNDATION_EIN))
            self.assertEqual(confirmed.matched_registry_identifier, "18796")
        with patch.object(c, "load_ky_snapshot_records", return_value=[candidate, parent]):
            self.assertEqual(c.search_ky_strict_snapshot(org).matched_registry_identifier, "18801")


class ArkansasEvidence(unittest.TestCase):
    def test_same_run_report_distinguishes_no_match_from_incomplete(self):
        ein = "530196568"
        exact = AAAS
        completed = "AAAS"
        with snapshots.CaptureRun(AAAS, ein, "AR") as run:
            for name, destination in [(exact, "Other submitted name"), (completed, completed)]:
                query = receipt.begin_query("AR", name, c.AR_SEARCH_URL)
                url = receipt.AR_RESULTS_URL + "?" + urlencode({"name": destination, "type": "Charity Registration"})
                receipt.ar_rows_start()
                receipt.finish_ar(query, "Back to Search Form No Results Found", url, True)
            raw = dict(state="AR", ein=ein, status="Unable to Confirm", success=False,
                       status_reason="AR_REQUIRED_SEARCH_INCOMPLETE")
            worker = history.finish_worker_history(run, raw)
        job = {"state": "AR", "payload": {"ein": ein}}
        with tempfile.TemporaryDirectory() as folder:
            store = snapshots.SQLiteStore(Path(folder) / "history.db")
            result = history.persist_worker_history(raw, job, worker["_worker_search_history"], [], store=store)
            self.assertEqual(result["status"], raw["status"])
            self.assertFalse(result["success"])
            self.assertNotIn("evidence_url", result)
            ident = result["search_history_url"].split("/")[2]
            _, payload, _ = store.load(ident)
            doc = json.loads(payload)
            self.assertEqual([(q["query"]["name"], q["returned_rows"]) for q in doc["queries"]], [(exact, None), (completed, 0)])
            text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(history.render_pdf(doc))).pages)
            self.assertIn("CharityClarity Search Attempts", text)
            self.assertIn("Completion not confirmed", text)

    def test_stale_result_urls_never_bind(self):
        url = receipt.AR_RESULTS_URL
        for suffix in ("?name=Other", "?name=AAAS&name=AAAS", "?name=AAAS&type=Paid", "?name=AAAS&other=1", "?name=AAAS#wrong"):
            self.assertFalse(receipt.ar_results_bound(url + suffix, "AAAS"))
        self.assertFalse(receipt.ar_results_bound(c.AR_SEARCH_URL + "?name=AAAS", "AAAS"))
        self.assertTrue(receipt.ar_results_bound(url + "?name=AAAS", "AAAS"))

    def test_readiness_uses_existing_allowance_and_exact_name(self):
        page = MagicMock()
        c.ar_wait_for_bound_result(page, AAAS, 498)
        self.assertEqual(page.wait_for_function.call_args.kwargs,
            {"arg": [receipt.AR_RESULTS_URL, AAAS], "timeout": 498})
        page.reset_mock()
        c.ar_wait_for_bound_result(page, AAAS, 0)
        page.wait_for_function.assert_not_called()
