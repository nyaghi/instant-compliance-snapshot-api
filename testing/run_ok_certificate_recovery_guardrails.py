"""Oklahoma certificate transport failures must not become registration conclusions."""
import base64
import sys
import time
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc

class OklahomaCertificateRecoveryTests(unittest.TestCase):
    def calculate(self, filing="12345670002 Renewal Registration June 15, 2026 5", note="Oklahoma certificate service unavailable. HTTP 520.", detail="Status: Active", candidates=None):
        import re
        def parse(text):
            match = re.search(r"[A-Za-z]+ \d{1,2}, \d{4}", text)
            try:
                return datetime.strptime(match.group(), "%B %d, %Y").date() if match else None
            except ValueError:
                return None
        module = Mock(parse_ok_filing_date=parse)
        return cc.ok_calculated_registration_expiration(filing, note, detail, candidates if candidates is not None else [filing], module)

    def test_transport_failure_can_use_completed_renewal_anniversary(self):
        self.assertEqual(self.calculate(), date(2027, 6, 15))

    def test_initial_registration_anniversary(self):
        self.assertEqual(self.calculate(filing="123 Application for Registration June 15, 2026 3"), date(2027, 6, 15))

    def test_ez_renewal_history_is_a_qualifying_registration(self):
        self.assertEqual(self.calculate(candidates=["456 Renewal Registration - EZ June 15, 2025 3"]), date(2027, 6, 15))
        self.assertEqual(self.calculate(filing="123 Renewal Registration - EZ June 15, 2026 3"), date(2027, 6, 15))

    def test_early_and_late_renewals_use_actual_filing_date(self):
        for day in (1, 28):
            self.assertEqual(self.calculate(filing=f"123 Renewal Registration January {day}, 2026 3"), date(2027, 1, day))

    def test_invalid_certificate_is_not_overridden(self):
        for note in ("Certificate identity not confirmed", "Certificate could not be read", "Missing document action"):
            self.assertIsNone(self.calculate(note=note))

    def test_adverse_or_uncompleted_record_cannot_use_calculation(self):
        for status in ("Pending", "Rejected", "Denied", "Suspended", "Revoked", "Canceled", "Void", "Unapproved"):
            self.assertIsNone(self.calculate(detail="Status: " + status))

    def test_other_filings_do_not_reset_registration(self):
        for filing in ("123 Amendment June 15, 2026 2", "123 Annual Report June 15, 2026 2", "123 Renewal Registration June 15, 2026 2 Pending"):
            self.assertIsNone(self.calculate(filing=filing))

    def test_future_invalid_and_leap_day_dates_not_guessed(self):
        for filed in ("June 15, 2099", "February 30, 2026", "February 29, 2024"):
            self.assertIsNone(self.calculate(filing=f"123 Renewal Registration {filed} 2"))

    def test_ambiguous_or_newer_history_blocks_fallback(self):
        for candidate in ("456 Renewal Registration date unavailable 2", "456 Renewal Registration June 15, 2026 2", "456 Renewal Registration July 15, 2026 2"):
            self.assertIsNone(self.calculate(candidates=[candidate]))

    def test_calculated_expiration_survives_public_response(self):
        org = cc.checker.Organization("Example National Foundation", "123456789")
        result = cc.checker.StateResult(org.organization_name, org.ein, "OK", "Current", "https://www.sos.ok.gov/")
        result.raw_status_text = "123 Renewal Registration June 15, 2026 2 | Calculated Registration Expiration: 6/15/2027"
        result.source_note = "Calculated registration expiration: 6/15/2027 (certificate unavailable; not certificate-confirmed)."
        result.success = True
        response = cc.response_data_for_lookup(result, result.raw_status_text + " " + result.source_note, org, org.organization_name, org.ein, "OK", time.perf_counter())
        self.assertEqual(response["status"], "Current")
        self.assertIn("not certificate-confirmed", response["comments"])

    def setUp(self):
        cc._ok_certificate_cache.clear()
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

    def seed(self, age=0, name=None, document="12345670002", url=None):
        self.key = (url or self.page.url, document, name or self.name)
        cc._ok_certificate_cache[self.key] = (time.time() - age, date(2027, 1, 28))

    def test_verified_cache_reused_on_520_with_original_timestamp(self):
        self.seed(age=3600)
        original = cc._ok_certificate_cache[self.key]
        due, note = self.fetch()
        self.assertEqual(due, original[1])
        self.assertEqual(cc._ok_certificate_cache[self.key], original)
        self.assertIn("Certificate freshness note", note)
        self.assertIn("12345670002", note)
        self.assertIn("UTC", note)
        self.page.goto.assert_not_called()

    def test_cache_timestamp_survives_public_comments(self):
        result = cc.checker.StateResult(self.name, "123456789", "OK", "Current", self.page.url)
        result.source_note = "Certificate freshness note: reused the verified certificate retrieved 2026-09-06 12:00:00 UTC (less than 24 hours old)."
        comments = cc.comments_for_result(result, "Certificate Expiration Date: March 12, 2027", "Current")
        self.assertIn(result.source_note, comments)

    def test_low_confidence_exact_name_does_not_relax_dates_or_identity(self):
        pdf_page = Mock()
        pdf_page.extract_text.return_value = ""
        pdf_page.images = [Mock(image=Mock(width=100, height=100))]
        for printed_name, date_confidence, expected in (
            (self.name, .98, date(2027, 1, 28)),
            ("Other National Foundation", .98, None),
            (self.name, .80, None),
        ):
            with self.subTest(name=printed_name, date_confidence=date_confidence):
                lines = [[[], "CERTIFICATE OF REGISTRATION", .99],
                         [[], "WHEREAS,theRenewalRegistrationof", .99],
                         [[], printed_name, .78], [[], "has been filed", .99],
                         [[], "will expire on January 28, 2027", date_confidence]]
                engine = Mock(return_value=(lines, None))
                with patch("pypdf.PdfReader", return_value=Mock(pages=[pdf_page])), \
                     patch.object(cc, "_OK_CERTIFICATE_OCR", engine), \
                     patch.object(cc, "_OK_CERTIFICATE_OCR_DETAIL", engine):
                    due, _ = cc.ok_certificate_expiration(b"%PDF-fixture", self.name)
                self.assertEqual(due, expected)

    def test_expired_and_future_cache_not_reused(self):
        for age in (86400, 86401, -100):
            with self.subTest(age=age):
                self.seed(age=age)
                self.page.evaluate.return_value = {"ok": False, "status": 520}
                due, note = self.fetch()
                self.assertIsNone(due)
                self.assertIn("service unavailable", note)

    def test_different_identity_document_or_record_not_reused(self):
        for options in ({"name": "Other Foundation"}, {"document": "99999990002"}, {"url": self.page.url + "9"}):
            with self.subTest(options=options):
                cc._ok_certificate_cache.clear()
                self.seed(**options)
                self.page.evaluate.return_value = {"ok": False, "status": 520}
                due, note = self.fetch()
                self.assertIsNone(due)

    def test_cache_requires_live_document_action(self):
        self.seed()
        self.page.get_by_role.return_value.get_attribute.return_value = "invalid"
        due, note = self.fetch()
        self.assertIsNone(due)
        self.assertNotIn("reused", note)

    def test_fresh_pdf_is_preferred_and_verified_before_caching(self):
        self.seed(age=3600)
        self.page.request.post.return_value.ok = True
        self.page.request.post.return_value.body.return_value = b"%PDF-new"
        with patch.object(cc, "ok_certificate_expiration", return_value=(date(2027, 2, 28), "verified")):
            due, note = self.fetch()
        self.assertEqual(due, date(2027, 2, 28))
        self.assertEqual(cc._ok_certificate_cache[self.key][1], due)
        self.assertNotIn("reused", note)

    def test_invalid_fresh_pdf_invalidates_existing_cache(self):
        self.seed()
        self.page.request.post.return_value.ok = True
        self.page.request.post.return_value.body.return_value = b"%PDF-invalid"
        with patch.object(cc, "ok_certificate_expiration", return_value=(None, "identity not confirmed")):
            due, note = self.fetch()
        self.assertIsNone(due)
        self.assertNotIn(self.key, cc._ok_certificate_cache)

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

    def test_unreadable_pdf_is_not_mislabeled_as_server_outage(self):
        self.page.request.post.return_value.ok = True
        self.page.request.post.return_value.body.return_value = b"%PDF-broken"
        with patch.object(cc, "ok_certificate_expiration", side_effect=ValueError("broken document")):
            due, note = self.fetch()
        self.assertIsNone(due)
        self.assertIn("could not be read", note)
        self.assertNotIn("service unavailable", note)
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
