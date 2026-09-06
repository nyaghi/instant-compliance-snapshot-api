"""Regression tests for the September 5 manual-check reconciliation."""
import sys
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc


class AsOfDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 5)


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.clock = patch.object(cc, "date", AsOfDate)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def test_six_calendar_month_boundary(self):
        self.assertEqual(cc.status_from_calendar_date(date(2027, 3, 5)), "Upcoming Filing")
        self.assertEqual(cc.status_from_calendar_date(date(2027, 3, 6)), "Current")
        self.assertEqual(cc.status_from_calendar_date(date(2026, 9, 4)), "Delinquent")

    def test_connecticut_detail_keeps_search_session(self):
        response = Mock()
        response.text = '<script>Expiration 1/1/2000</script><div>Expiration Date: 11/30/2026</div>'
        session = Mock()
        session.get.return_value = response
        with patch.object(cc.urllib.request, "urlopen", side_effect=AssertionError("Search session lost")):
            text = cc.ct_direct_detail_text("DisplayLicenceDetail('record-id')", session=session)
        self.assertIn("11/30/2026", text)
        self.assertNotIn("1/1/2000", text)
        session.get.assert_called_once()

    def test_maryland_current_registration_receives_automatic_extension(self):
        r = cc.checker.StateResult("Victims of Communism", "521920858", "MD", cc.checker.STATUS_CURRENT, "")
        r.raw_status_text = "Current"
        body = "Year Represented: 2024\nFiscal Year End: 12/31/2024\nCurrent"
        context = cc.filing_context(r, body)
        self.assertEqual(context["base_due_date"], date(2026, 6, 30))
        self.assertEqual(context["due_date"], date(2026, 11, 15))
        self.assertEqual(cc.true_status_from_body(r, body), "Upcoming Filing")
        self.assertIn("11/15/2026", cc.comments_for_result(r, body, "Upcoming Filing"))

    def test_oklahoma_certificate_requires_correct_entity_and_one_expiration(self):
        text = "CERTIFICATE OF REGISTRATION Registration of READING IS FUNDAMENTAL INC has been filed. This registration will expire on March 12, 2027."
        page = Mock()
        page.images = []
        page.extract_text.return_value = text
        reader = Mock()
        reader.pages = [page]
        with patch("pypdf.PdfReader", return_value=reader):
            self.assertEqual(cc.ok_certificate_expiration(b"fixture", "Reading Is Fundamental Inc")[0], date(2027, 3, 12))
            self.assertIsNone(cc.ok_certificate_expiration(b"fixture", "Junior Achievement USA")[0])
            page.extract_text.return_value = text + " Another registration will expire on March 13, 2027."
            self.assertIsNone(cc.ok_certificate_expiration(b"fixture", "Reading Is Fundamental Inc")[0])

    def test_certificate_ocr_month_and_spacing_are_bounded(self):
        page = Mock()
        page.images = []
        reader = Mock()
        reader.pages = [page]
        with patch("pypdf.PdfReader", return_value=reader):
            for month, expected in [("Jamuary", date(2027, 1, 28)), ("Juny", None)]:
                page.extract_text.return_value = f"CERTIFICATE OF REGISTRATION Registrationof RONALD MCDONALD HOUSE CHARITIES INC has been filed. This registration will expire on {month} 28,2027."
                self.assertEqual(cc.ok_certificate_expiration(b"fixture", "Ronald McDonald House Charities Inc")[0], expected)

    def test_failed_detail_is_not_negative_from_prior_query(self):
        r = cc.checker.StateResult("Reading Is Fundamental", "520976257", "NY", cc.checker.STATUS_UNKNOWN, "")
        r.raw_status_text = "Detail page not reached"
        r.source_note = "EIN query returned no results; name query found a record."
        self.assertEqual(cc.public_status(r), "Unable to Confirm")
        self.assertEqual(cc.true_status_from_body(r, r.raw_status_text), "Unable to Confirm")

    def test_maine_status_glossary_cannot_override_failed_renewal(self):
        r = cc.checker.StateResult("Make-A-Wish", "860481941", "ME", "Failed to Renew", "")
        r.raw_status_text = "Failed to Renew"
        self.assertEqual(cc.true_status_from_body(r, "Status definitions: Pending, Active, Failed to Renew"), "Failed to Renew")

    def test_virginia_lapsed_record_is_not_absent(self):
        reg = {"expirationDate": "2025-05-15", "extensionDate": "2025-11-15", "status": {"name": "Expired"}}
        status, _, _, due = cc.va_evoke_status_from_entity_and_registrations({"status": "Unregistered"}, [reg])
        self.assertEqual(status, "Delinquent")
        self.assertEqual(due, date(2025, 11, 15))
        self.assertEqual(cc.va_evoke_status_from_entity_and_registrations({"status": "Unregistered"}, [])[0], cc.checker.STATUS_NOT_REGISTERED)

    def test_wisconsin_aliases_do_not_select_regional_license(self):
        name = "Ronald McDonald House Global / RMHC"
        targets = cc.organization_match_target_variants(name, "362934689")
        rows = [
            ("25435-800", "RONALD MCDONALD HOUSE CHARITIES", "Salt Lake City, UT", "7/31/2027"),
            ("25435-800", "RONALD MCDONALD HOUSE CHARITIES OF THE INTERMOUNTAIN AREA INC", "Salt Lake City, UT", "7/31/2027"),
            ("2812-800", "RONALD MCDONALD HOUSE CHARITIES INC", "Chicago, IL", "7/31/2026"),
            ("9999-800", "RMHC", "Other city", "7/31/2028"),
        ]
        html_rows, markdown_rows = [], []
        for license_id, registry_name, location, due in rows:
            cells = [license_id, "Charitable Organization", registry_name, location, "10/30/1990", due]
            html_rows.append("<tr>" + "".join(f"<td>{v}</td>" for v in cells) + "</tr>")
            markdown_rows.append("| " + " | ".join(cells) + " |")
        html = '<table id="ctl00_cphMainContent_OrgCredentialSearch_gvCredentialSearchResults">' + "".join(html_rows) + "</table>"
        with patch.object(cc, "wi_http_detail_status", return_value=""), patch.object(cc, "wi_reader_detail_status", return_value=""):
            for parser, source in [(cc.wi_best_match_from_html, html), (cc.wi_best_match_from_markdown, "\n".join(markdown_rows))]:
                candidate = parser(source, targets, original_name=name, ein="362934689")
                self.assertEqual(candidate["license_number"], "2812-800")
                self.assertEqual(candidate["expiration_date"], date(2026, 7, 31))
        self.assertFalse(cc.explicit_acronym_alias_matches_registry(name, "Ronald McDonald House Cleveland"))
        self.assertFalse(cc.explicit_acronym_alias_matches_registry(name, rows[1][1]))

    def test_shared_explicit_acronym_requires_full_identity(self):
        name = "Ronald McDonald House Global / RMHC"
        registry_name = "Ronald McDonald House Charities Inc."
        self.assertTrue(cc.registry_name_is_safe_for_org(registry_name, name, "362934689"))
        self.assertEqual(cc.target_name_score(registry_name, [name]), 850)
        self.assertEqual(cc.score_candidate(name, "362934689", {"name": registry_name})["decision"], "accepted")
        self.assertEqual(cc.score_candidate(name, "362934689", {"name": registry_name, "ein": "123456789"})["decision"], "rejected")
        for other in ["Ronald McDonald House Cleveland", "Ronald McDonald House Charities of Greater Houston", "RMHC"]:
            self.assertFalse(cc.explicit_acronym_alias_matches_registry(name, other))
        self.assertFalse(cc.explicit_acronym_alias_matches_registry("Good Health National Foundation / GHNF", "Good Health Nevada Foundation"))

    def test_wisconsin_final_response_preserves_confirmed_alias(self):
        name = "Ronald McDonald House Global / RMHC"
        org = cc.checker.Organization(name, "362934689")
        r = cc.checker.StateResult(name, org.ein, "WI", "Delinquent", cc.WI_SEARCH_URL)
        r.matched_registry_name = "RONALD MCDONALD HOUSE CHARITIES INC"
        r.matched_registry_identifier = "2812-800"
        r.raw_status_text = "License expired 7/31/2026"
        r.success = True
        result = cc.response_data_for_lookup(r, r.raw_status_text, org, name, org.ein, "WI", time.perf_counter())
        self.assertEqual(result["status"], "Delinquent")
        self.assertEqual(result["matched_registry_identifier"], "2812-800")

    def test_new_mexico_completed_filing_advances_cycle(self):
        module = cc.load_wa_nm_module()
        cases = [
            ([(2025, "Tax Year Registration Open", "9/1/2026"), (2024, "Registration Submitted 20244122623260437", "8/20/2026"), (2024, "Extension Granted", "10/28/2025")], "8/31/2025", "Upcoming Filing", "02/28/2027"),
            ([(2025, "Registration Submitted 20255022622447622", "8/12/2026"), (2025, "Extension Granted", "8/12/2026"), (2025, "Registration Submission Delinquent", "7/1/2026")], "12/31/2025", "Current", "06/30/2027"),
        ]
        with patch.object(module, "date", AsOfDate):
            for rows, fye, expected, due in cases:
                r = module.SearchResult("Test", "123456789", "NM", module.STATUS_UNKNOWN, "", module.NM_SEARCH_URL, "")
                result = cc.nm_apply_status_history_master(module, r, rows, fye)
                self.assertEqual(result.status, expected)
                self.assertIn("Due: " + due, result.raw_status_text)

    def test_new_mexico_later_delinquency_is_preserved(self):
        module = cc.load_wa_nm_module()
        rows = [(2025, "Registration Submitted 123456789012", "1/1/2026"), (2025, "Registration Submission Delinquent", "8/1/2026")]
        r = module.SearchResult("Test", "123456789", "NM", module.STATUS_UNKNOWN, "", module.NM_SEARCH_URL, "")
        with patch.object(module, "date", AsOfDate):
            self.assertEqual(cc.nm_apply_status_history_master(module, r, rows, "12/31/2025").status, "Delinquent")


if __name__ == "__main__":
    unittest.main(verbosity=2)
