"""New Mexico filing-event regressions; test tooling, not runtime routing."""
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc


class AsOfDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 7)


ARBOR_HISTORY = [
    (2025, "Tax Year Registration Open", "7/1/2026"),
    (2024, "Registration Submitted 20244122601247590", "1/12/2026"),
    (2024, "Extension Granted", "11/15/2025"),
    (2024, "Extension Requested", "11/15/2025"),
    (2024, "Tax Year Registration Open", "7/1/2025"),
    (2023, "Registration Submitted 20234112431758948", "11/12/2024"),
]


class NewMexicoHistoryTests(unittest.TestCase):
    def setUp(self):
        self.module = cc.load_wa_nm_module()
        for owner in (cc, self.module):
            clock = patch.object(owner, "date", AsOfDate)
            clock.start()
            self.addCleanup(clock.stop)

    def classify(self, rows, fye):
        r = self.module.SearchResult("History fixture", "012345678", "NM", self.module.STATUS_UNKNOWN, "", self.module.NM_SEARCH_URL, "")
        r.matched_registry_name = "History fixture"
        with patch.object(self.module, "nm_extract_fye", side_effect=AssertionError("No new document fetch needed")):
            return cc.nm_apply_status_history_master(self.module, r, rows, fye)

    def test_open_date_cannot_replace_submitted_fiscal_period(self):
        # FYE is an explicit test input, not asserted as Arbor Day's verified FYE.
        r = self.classify(ARBOR_HISTORY, "06/30/2024")
        self.assertEqual(r.status, "Delinquent")
        self.assertIn("Due: 12/30/2025", r.raw_status_text)
        self.assertIn("Filed FYE: 06/30/2024", r.raw_status_text)

    def test_same_history_can_remain_upcoming_if_filed_period_supports_it(self):
        r = self.classify(ARBOR_HISTORY, "06/30/2025")
        self.assertEqual(r.status, "Upcoming Filing")
        self.assertIn("Due: 12/30/2026", r.raw_status_text)
        self.assertIn("Filed FYE: 06/30/2025", r.raw_status_text)

    def test_requested_extension_does_not_change_unextended_deadline(self):
        submitted = [(2024, "Registration Submitted 123456789012", "2/1/2025")]
        for detail in ("Extension Requested", "Tax Year Registration Open"):
            r = self.classify([(2025, detail, "7/1/2026")] + submitted, "12/31/2024")
            self.assertEqual(r.status, "Delinquent")
            self.assertIn("Due: 06/30/2026", r.raw_status_text)

    def test_granted_extension_for_new_cycle_is_preserved(self):
        rows = [(2025, "Extension Granted", "6/1/2026"), (2025, "Extension Requested", "6/1/2026"), (2024, "Registration Submitted 123456789012", "2/1/2025")]
        r = self.classify(rows, "12/31/2024")
        self.assertEqual(r.status, "Upcoming Filing")
        self.assertIn("Extension Granted", r.raw_status_text)
        self.assertIn("Due: 11/15/2026", r.raw_status_text)

    def test_newer_requested_year_cannot_hide_intermediate_grant(self):
        rows = [(2026, "Extension Requested", "9/1/2026"), (2025, "Extension Granted", "6/1/2026"), (2024, "Registration Submitted 123456789012", "2/1/2025")]
        r = self.classify(rows, "12/31/2024")
        self.assertIn("Tax Year 2025", r.raw_status_text)
        self.assertIn("Extension Granted", r.raw_status_text)

    def test_later_open_row_cannot_hide_submission_same_cycle(self):
        rows = [(2025, "Tax Year Registration Open", "9/1/2026"), (2025, "Registration Submitted 123456789012", "8/1/2026")]
        r = self.classify(rows, "12/31/2025")
        self.assertEqual(r.status, "Current")
        self.assertIn("Due: 06/30/2027", r.raw_status_text)

    def test_only_open_or_requested_is_not_completed_filing_evidence(self):
        for detail in ("Tax Year Registration Open", "Extension Requested"):
            r = self.classify([(2025, detail, "7/1/2026")], "06/30/2025")
            self.assertNotIn(r.status, {"Current", "Upcoming Filing", "Delinquent", "Not Registered"})
            org = cc.checker.Organization("History fixture", "012345678")
            copied = cc.copy_external_result(org, "NM", r)
            self.assertNotIn(cc.public_status(copied), {"Current", "Upcoming Filing", "Delinquent", "Not Registered"})

    def test_open_event_cannot_supply_missing_submitted_fiscal_period(self):
        r = self.classify(ARBOR_HISTORY, "")
        self.assertEqual(r.status, self.module.STATUS_UNKNOWN)
        self.assertIn("fiscal period could not be confirmed", r.source_note)

    def test_final_comment_uses_submitted_fiscal_period(self):
        r = self.classify(ARBOR_HISTORY, "06/30/2025")
        org = cc.checker.Organization("History fixture", "012345678")
        copied = cc.copy_external_result(org, "NM", r)
        text = cc.comments_for_result(copied, "", copied.status)
        self.assertIn("6/30/2025", text)
        self.assertIn("12/30/2026", text)

    def test_later_explicit_delinquency_still_controls(self):
        rows = [(2025, "Registration Submission Delinquent", "8/1/2026"), (2025, "Registration Submitted 123456789012", "1/1/2026")]
        self.assertEqual(self.classify(rows, "12/31/2025").status, "Delinquent")

    def test_row_order_does_not_change_result(self):
        a = self.classify(ARBOR_HISTORY, "06/30/2024")
        b = self.classify(list(reversed(ARBOR_HISTORY)), "06/30/2024")
        self.assertEqual((a.status, a.raw_status_text), (b.status, b.raw_status_text))


if __name__ == "__main__":
    unittest.main(verbosity=2)
