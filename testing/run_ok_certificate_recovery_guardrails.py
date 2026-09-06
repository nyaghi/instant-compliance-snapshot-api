"""Oklahoma certificate transport failures must not become registration conclusions."""
import base64
import sys
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc

class OklahomaCertificateRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.page = Mock()
        self.page.url = "https://www.sos.ok.gov/corp/charityDetail.aspx?id=1234567890"
        self.page.get_by_role.return_value.get_attribute.return_value = "javascript:__doPostBack('ctl00$DefaultContent$grdFilingList$ctl26$lnkAction','')"
        self.page.locator.return_value.first.evaluate.return_value = {"__VIEWSTATE": "fixture"}
        response = self.page.request.post.return_value
        response.ok = False
        response.status = 520
        response.headers = {"content-type": "text/html"}
        response.body.return_value = b"<html>520: Web server is returning an unknown error</html>"
        self.page.evaluate.return_value = {"ok": True, "status": 200, "content_type": "application/pdf",
                                           "pdf_base64": base64.b64encode(b"%PDF-recovered").decode()}
        self.filing = "12345670002 Renewal Registration January 28, 2026 5"
        self.name = "Example National Foundation"

    def fetch(self):
        return cc.ok_fetch_registration_certificate(self.page, self.filing, self.name)

    def test_520_recovers_via_refreshed_browser_request(self):
        with patch.object(cc, "ok_certificate_expiration", return_value=(date(2027, 1, 28), "certificate")) as parse:
            due, note = self.fetch()
        self.assertEqual(due, date(2027, 1, 28))
        self.assertIn("HTTP 520", note)
        self.assertIn("one refreshed browser request", note)
        self.page.goto.assert_called_once_with(self.page.url, wait_until="domcontentloaded", timeout=12000)
        self.assertEqual(self.page.evaluate.call_args.args[1], "12345670002")
        parse.assert_called_once_with(b"%PDF-recovered", self.name)
        self.page.request.post.assert_called_once()
        self.page.expect_download.assert_not_called()

    def test_primary_pdf_needs_no_recovery(self):
        self.page.request.post.return_value.ok = True
        self.page.request.post.return_value.body.return_value = b"%PDF-primary"
        with patch.object(cc, "ok_certificate_expiration", return_value=(date(2027, 1, 28), "certificate")):
            due, note = self.fetch()
        self.assertEqual(due, date(2027, 1, 28))
        self.page.goto.assert_not_called()
        self.page.evaluate.assert_not_called()
        self.assertIn("primary request", note)

    def test_timeout_has_one_bounded_recovery(self):
        self.page.request.post.side_effect = TimeoutError("upstream timeout")
        with patch.object(cc, "ok_certificate_expiration", return_value=(date(2027, 1, 28), "certificate")):
            due, note = self.fetch()
        self.assertIsNotNone(due)
        self.assertIn("TimeoutError", note)
        self.page.evaluate.assert_called_once()

    def test_persistent_520_is_registry_unavailability(self):
        self.page.evaluate.return_value = {"ok": False, "status": 520, "content_type": "text/html", "pdf_base64": ""}
        with patch.object(cc, "ok_certificate_expiration") as parse:
            due, note = self.fetch()
        self.assertIsNone(due)
        self.assertTrue(note.startswith("Oklahoma certificate service unavailable."))
        parse.assert_not_called()
        self.page.expect_download.assert_not_called()

    def test_recovery_timeout_does_not_trigger_more_attempts(self):
        self.page.evaluate.side_effect = TimeoutError("browser timeout")
        due, note = self.fetch()
        self.assertIsNone(due)
        self.assertTrue(note.startswith("Oklahoma certificate service unavailable."))
        self.page.evaluate.assert_called_once()
        self.page.request.post.assert_called_once()

    def test_refresh_failure_stops_before_posting_stale_form(self):
        self.page.goto.side_effect = TimeoutError("refresh failed")
        due, note = self.fetch()
        self.assertIsNone(due)
        self.page.evaluate.assert_not_called()
        self.assertIn("unavailable", note)

    def test_html_200_recovery_is_not_a_pdf(self):
        self.page.evaluate.return_value = {"ok": True, "status": 200, "content_type": "text/html", "pdf_base64": ""}
        with patch.object(cc, "ok_certificate_expiration") as parse:
            due, note = self.fetch()
        self.assertIsNone(due)
        parse.assert_not_called()
        self.assertIn("no PDF received", note)

    def test_recovered_pdf_must_confirm_identity_and_date(self):
        with patch.object(cc, "ok_certificate_expiration", return_value=(None, "Certificate identity not confirmed")):
            due, note = self.fetch()
        self.assertIsNone(due)
        self.assertIn("identity not confirmed", note)

    def test_bad_primary_certificate_is_not_replaced_with_another_document(self):
        self.page.request.post.return_value.ok = True
        self.page.request.post.return_value.body.return_value = b"%PDF-primary"
        with patch.object(cc, "ok_certificate_expiration", return_value=(None, "Certificate identity not confirmed")):
            due, note = self.fetch()
        self.assertIsNone(due)
        self.page.goto.assert_not_called()

    def test_missing_document_action_is_not_guessed(self):
        self.page.get_by_role.return_value.get_attribute.return_value = "javascript:unrelatedAction()"
        due, note = self.fetch()
        self.assertIsNone(due)
        self.page.request.post.assert_not_called()
        self.page.evaluate.assert_not_called()

    def test_registry_unavailable_survives_response_normalization(self):
        org = cc.checker.Organization(self.name, "123456789")
        result = cc.checker.StateResult(self.name, org.ein, "OK", "Site Not Reachable", self.page.url)
        result.raw_status_text = self.filing
        result.source_note = "Oklahoma certificate service unavailable. HTTP 520. No deadline was inferred."
        result.success = False
        response = cc.response_data_for_lookup(result, result.raw_status_text + " " + result.source_note,
                                               org, self.name, org.ein, "OK", time.perf_counter())
        self.assertEqual(response["status"], "Site Not Reachable")

if __name__ == "__main__":
    unittest.main(verbosity=2)
