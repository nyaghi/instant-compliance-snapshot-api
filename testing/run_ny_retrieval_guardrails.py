"""NY official-response contract and timing regression tests; no runtime sidecar."""
import json
import sys
import threading
import time
import unittest
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc

ROW = {"orgName": "Example National Foundation", "ein": "123456789", "orgID": "10-20-30"}
DETAIL = {**ROW, "regType": "NFP", "regStatute": "7A", "documents": {
    "Annual Filing for Charitable Organizations": [{"fiscalYearEnd": "12/31/2025", "received": "08/20/2026"}]}}

class AsOfDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 6)

def response(data, success=True):
    r = Mock()
    r.json.return_value = {"success": success, "statusCode": 200, "data": data}
    return r

class NewYorkRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.org = cc.checker.Organization("Example National Foundation", "123456789")
        self.clock = patch.object(cc, "date", AsOfDate)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def lookup(self, responses):
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        session.get.side_effect = responses
        with patch.object(cc.curl_requests, "Session", return_value=session):
            result = cc.search_ny_direct(self.org)
        return result, session

    def test_complete_identity_and_fye_not_received_date(self):
        r, s = self.lookup([response([ROW]), response(DETAIL)])
        self.assertEqual(r.status, "Current")
        self.assertEqual(r.fiscal_year_end, "12/31/2025")
        self.assertEqual(r.computed_due_date, "5/15/2027")
        self.assertEqual(s.get.call_count, 2)
        self.assertEqual(s.get.call_args_list[0].kwargs["params"], {"ein": "123456789"})
        cc.apply_ny_latest_fye_next_cycle_status(self.org, r)
        self.assertEqual(r.source_note.count("New York shows the latest"), 1)

    def test_exact_ein_wins_without_selecting_first_row(self):
        wrong = {**ROW, "ein": "987654321", "orgID": "99-99-99"}
        r, s = self.lookup([response([wrong, ROW]), response(DETAIL)])
        self.assertEqual(r.status, "Current")
        self.assertEqual(s.get.call_args_list[1].kwargs["params"], {"orgID": ROW["orgID"]})

    def test_changed_legal_name_still_matches_exact_ein(self):
        r, _ = self.lookup([response([{**ROW, "orgName": "Renamed Foundation"}]),
                            response({**DETAIL, "orgName": "Renamed Foundation"})])
        self.assertEqual(r.status, "Current")

    def test_duplicate_ein_different_registrations_is_ambiguous(self):
        r, s = self.lookup([response([ROW, {**ROW, "orgID": "11-22-33"}])])
        self.assertEqual(r.status, "Unable to Confirm")
        self.assertEqual(s.get.call_count, 1)

    def test_wrong_detail_identity_is_not_negative(self):
        for field, value in [("ein", "987654321"), ("orgID", "99-99-99")]:
            with self.subTest(field=field):
                r, _ = self.lookup([response([ROW]), response({**DETAIL, field: value})])
                self.assertEqual(r.status, "Unable to Confirm")

    def test_http_error_timeout_invalid_json_and_unsuccessful_empty_are_not_negative(self):
        bad_json = Mock(); bad_json.json.side_effect = ValueError("Invalid JSON")
        bad_http = Mock(); bad_http.raise_for_status.side_effect = RuntimeError("HTTP 503")
        for bad in [TimeoutError("Timeout"), bad_json, bad_http, response([], False), response(None)]:
            with self.subTest(bad=str(bad)):
                r, s = self.lookup([bad])
                self.assertEqual(r.status, "Unable to Confirm")
                self.assertFalse(r.success)
                self.assertEqual(s.get.call_count, 1)

    def test_incomplete_search_row_is_not_negative(self):
        r, _ = self.lookup([response([{"orgName": ROW["orgName"]}])])
        self.assertEqual(r.status, "Unable to Confirm")

    def test_completed_empty_searches_are_negative(self):
        r, s = self.lookup([response([]) for _ in range(5)])
        self.assertEqual(cc.public_status(r), "Not Registered")
        self.assertTrue(r.success)
        self.assertGreater(s.get.call_count, 1)
        self.assertLessEqual(s.get.call_count, 5)

    def test_name_fallback_after_completed_empty_ein(self):
        r, s = self.lookup([response([]), response([ROW]), response(DETAIL)])
        self.assertEqual(r.status, "Current")
        self.assertIn("orgName", s.get.call_args_list[1].kwargs["params"])

    def test_missing_documents_and_missing_fye_are_incomplete(self):
        for documents in [None, [], {"Annual Filing for Charitable Organizations": [{"received": "08/20/2026"}]}]:
            with self.subTest(documents=documents):
                r, _ = self.lookup([response([ROW]), response({**DETAIL, "documents": documents})])
                self.assertEqual(r.status, "Unable to Confirm")

    def test_explicit_empty_annual_collection_preserves_existing_rule(self):
        r, _ = self.lookup([response([ROW]), response({**DETAIL, "documents": {}})])
        self.assertEqual(cc.public_status(r), "Delinquent")
        self.assertEqual(r.status_reason, "NY_SAFE_MATCH_NO_FILINGS_DELINQUENT")

    def test_explicit_exemption(self):
        r, _ = self.lookup([response([ROW]), response({**DETAIL, "regStatute": "EXEMPT"})])
        self.assertEqual(r.status, "Exempt")

    def test_placeholder_ein_does_not_match_real_placeholder_record(self):
        self.org.ein = "000000000"
        r, s = self.lookup([])
        self.assertEqual(r.status, "Unable to Confirm")
        s.get.assert_not_called()

    def test_real_http_delayed_response_waits_for_complete_data(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                search = "RegistrySearch?" in self.path
                if search:
                    time.sleep(4)
                body = json.dumps({"success": True, "statusCode": 200,
                                   "data": [ROW] if search else DETAIL}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            started = time.perf_counter()
            with patch.object(cc, "NY_REGISTRY_API", f"http://127.0.0.1:{server.server_port}"):
                r = cc.search_ny_direct(self.org)
            self.assertGreaterEqual(time.perf_counter() - started, 4)
            self.assertEqual(r.status, "Current")
            self.assertEqual(len(r.source_attempts), 2)
        finally:
            server.shutdown()
            server.server_close()

if __name__ == "__main__":
    unittest.main(verbosity=2)
