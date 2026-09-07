"""MA submitted fiscal-period regression tests; offline tooling only."""
import sys
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc


class Today(date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 7)


class MassachusettsTests(unittest.TestCase):
    def setUp(self):
        for p in (patch.object(cc, "date", Today),
                  patch.object(cc.urllib.request, "urlopen", side_effect=AssertionError("Unexpected network"))):
            p.start()
            self.addCleanup(p.stop)

    def result(self, state="MA", status="Delinquent"):
        r = cc.checker.StateResult("Example Foundation", "123456789", state, status, "https://example.org")
        r.raw_status_text = "2024"
        r.source_note = "Latest visible Form PC year from Annual Filings"
        r.matched_registry_name = "Example Foundation"
        r.success = True
        return r

    def text(self, year=2024, end="12/31/2024", status="Submitted", account="051172"):
        return (f"AG Charity Number {account}\nFiling Year {year}\nFiling Status {status}\n"
                f"Current Fiscal Period Start Date 1/1/2024\nCurrent Fiscal Period End Date {end}")

    def evidence(self, end="12/31/2024", year=2024):
        return cc.ma_submitted_form_pc_evidence(self.text(year, end), year, "051172")

    def test_fiscal_period_is_read_from_submitted_detail(self):
        self.assertEqual(self.evidence()["period_end"], "12/31/2024")

    def test_wrong_account_or_year_is_not_accepted(self):
        self.assertFalse(cc.ma_submitted_form_pc_evidence(self.text(), 2025, "051172"))
        self.assertFalse(cc.ma_submitted_form_pc_evidence(self.text(), 2024, "999999"))
        self.assertFalse(cc.ma_submitted_form_pc_evidence(self.text(), 2024, ""))

    def test_open_requested_pending_and_rejected_are_not_submitted(self):
        for status in ("Open", "Extension Requested", "Draft", "Pending", "Rejected", "Not Submitted"):
            self.assertFalse(cc.ma_submitted_form_pc_evidence(self.text(status=status), 2024, "051172"))

    def test_missing_invalid_and_future_periods_are_not_assumed(self):
        for end in ("", "2/31/2024", "12/31/2027"):
            self.assertFalse(cc.ma_submitted_form_pc_evidence(self.text(end=end), 2024, "051172"))

    def test_december_period_survives_master_and_comment(self):
        r = cc.annotate_ma_visible_form_pc_due(self.result(), self.evidence())
        self.assertEqual(r.fiscal_year_end, "12/31")
        self.assertEqual(r.next_required_period, "12/31/2025")
        self.assertEqual(r.computed_due_date, "11/15/2026")
        self.assertEqual(cc.true_status_from_body(r, "Annual Filings 2024 Form-PC Data"), "Upcoming Filing")
        context = cc.filing_context(r, "")
        self.assertEqual(context["base_due_date"], date(2026, 5, 15))
        self.assertEqual(context["due_date"], date(2026, 11, 15))
        self.assertTrue(context["uses_extension_assumption"])
        text = cc.comments_for_result(r, "", "Upcoming Filing")
        for expected in ("12/31/2024", "12/31/2025", "5/15/2026", "11/15/2026", "inferred"):
            self.assertIn(expected, text)
        self.assertNotIn("6/30", text)

    def test_noncalendar_period_uses_its_own_month_day(self):
        for end, year, due, status in (("6/30/2025", 2025, "5/15/2027", "Current"),
                                       ("8/31/2024", 2024, "7/15/2026", "Delinquent"),
                                       ("9/30/2024", 2024, "8/15/2026", "Delinquent")):
            r = cc.annotate_ma_visible_form_pc_due(self.result(), self.evidence(end, year))
            self.assertEqual(r.computed_due_date, due)
            self.assertEqual(cc.true_status_from_body(r, ""), status)

    def test_leap_year_period_rolls_without_invalid_date(self):
        r = cc.annotate_ma_visible_form_pc_due(self.result(), self.evidence("2/29/2024"))
        self.assertEqual(r.next_required_period, "2/28/2025")
        self.assertEqual(r.computed_due_date, "1/15/2026")

    def test_unavailable_detail_never_reintroduces_june_or_profile_date(self):
        r = self.result()
        r.fiscal_year_end = "6/30"
        r.computed_due_date = "11/15/2025"
        cc.annotate_ma_visible_form_pc_due(r, {})
        self.assertEqual(cc.true_status_from_body(r, "2024 Form-PC Data"), "Unable to Confirm")
        self.assertEqual(r.computed_due_date, "")
        self.assertEqual(r.fiscal_year_end, "")
        self.assertIsNone(cc.filing_context(r, "2024 Form-PC Data")["due_date"])

    def test_explicit_adverse_registration_is_not_overridden_by_extension(self):
        for adverse, status in (("Delinquent", "Delinquent"), ("Suspended", "Suspended"),
                                ("Revoked", "Revoked"), ("Expired", "Delinquent")):
            evidence = {**self.evidence(), "adverse_status": adverse}
            r = cc.annotate_ma_visible_form_pc_due(self.result(), evidence)
            self.assertEqual(cc.true_status_from_body(r, ""), status)
            self.assertNotIn("Automatic Extension", r.raw_status_text)

    def test_clean_negative_and_other_states_are_untouched(self):
        for state, status in (("MA", "Not Registered"), ("MA", "Site Not Reachable"),
                              ("MA", "Exempt"), ("CO", "Current")):
            r = self.result(state, status)
            cc.annotate_ma_visible_form_pc_due(r, self.evidence())
            self.assertEqual(r.status, status)
            self.assertFalse(hasattr(r, "ma_filing_evidence"))

    def test_latest_row_selection_is_by_year_not_first_row(self):
        page = Mock()
        rows = page.get_by_role.return_value
        rows.all_inner_texts.return_value = ["2023 Form-PC Data", "2024 Financial Statement.pdf", "2024 Form-PC Data"]
        popup = page.expect_popup.return_value.__enter__ = Mock()
        page.expect_popup.return_value.__exit__ = Mock(return_value=False)
        detail = popup.return_value.value
        detail.locator.return_value.inner_text.return_value = self.text()
        detail.url = "https://masscharities.my.site.com/FilingSearch/s/detail/fixture"
        evidence = cc.ma_read_latest_form_pc(page, self.result(), "AG Account Number 051172 Tax ID 12-3456789")
        self.assertEqual(evidence["period_end"], "12/31/2024")
        rows.nth.assert_called_once_with(2)
        detail.close.assert_called_once()

    def test_duplicate_latest_forms_are_not_selected_arbitrarily(self):
        page = Mock()
        page.get_by_role.return_value.all_inner_texts.return_value = ["2024 Form-PC Data", "2024 Form-PC Data"]
        self.assertFalse(cc.ma_read_latest_form_pc(page, self.result(), "AG Account Number 051172"))
        page.expect_popup.assert_not_called()

    def test_newer_scanned_form_is_not_ignored_for_older_electronic_form(self):
        page = Mock()
        page.get_by_role.return_value.all_inner_texts.return_value = [
            "2023 Form-PC Data", "2024 FY2024 PC - Form PC/Annual RPT.tiff"]
        self.assertFalse(cc.ma_read_latest_form_pc(page, self.result(), "AG Account Number 051172"))
        page.expect_popup.assert_not_called()

    def test_explicit_adverse_is_preserved_without_opening_filing(self):
        page = Mock()
        evidence = cc.ma_read_latest_form_pc(page, self.result(), "AG Account Number 051172 Registration Status: Suspended")
        self.assertEqual(evidence["adverse_status"], "Suspended")
        page.expect_popup.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
