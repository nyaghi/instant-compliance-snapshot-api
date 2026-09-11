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
        page.expect_popup.assert_called_once()  # First unreadable detail keeps the result inconclusive.

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

    def completed(self, empty=True, status="Registered", account="051172"):
        return {"record": {"ago_account": account, "registry_status": status},
                "filings": {account: {"empty": empty}}}

    def test_completed_empty_history_inference_survives_master_and_comment(self):
        page = Mock()
        evidence = cc.ma_read_latest_form_pc(page, self.result(), "AG Account Number 051172", self.completed())
        r = cc.annotate_ma_visible_form_pc_due(self.result(), evidence)
        self.assertEqual(cc.true_status_from_body(r, "No documents found"), "Delinquent")
        self.assertEqual(r.computed_due_date, "")
        comment = cc.comments_for_result(r, "", "Delinquent")
        self.assertIn("infers Delinquent", comment)
        self.assertIn("not an explicit state determination", comment)
        page.expect_popup.assert_not_called()

    def test_empty_dom_without_completed_response_is_not_inferred(self):
        page = Mock()
        page.get_by_role.return_value.all_inner_texts.return_value = []
        for completed in ({}, {"record": {"ago_account": "051172"}}, self.completed(account="999999")):
            evidence = cc.ma_read_latest_form_pc(page, self.result(), "AG Account Number 051172 No documents found", completed)
            r = cc.annotate_ma_visible_form_pc_due(self.result(), evidence)
            self.assertEqual(cc.true_status_from_body(r, ""), "Unable to Confirm")

    def test_non_form_rows_are_not_an_empty_history(self):
        page = Mock()
        page.get_by_role.return_value.all_inner_texts.return_value = ["2023 Schedule-A2 Data"]
        evidence = cc.ma_read_latest_form_pc(page, self.result(), "AG Account Number 051172", self.completed(empty=False))
        self.assertEqual(cc.annotate_ma_visible_form_pc_due(self.result(), evidence).status, "Unable to Confirm")

    def test_not_doing_business_contradicts_empty_filing_inference(self):
        for empty in (False, True):
            evidence = cc.ma_read_latest_form_pc(Mock(), self.result(), "AG Account Number 051172",
                                                self.completed(empty=empty, status="Not Doing Business in Mass"))
            r = cc.annotate_ma_visible_form_pc_due(self.result(), evidence)
            self.assertEqual(cc.true_status_from_body(r, ""), "Closed / Withdrawn / Canceled")
            self.assertIn("Not Doing Business in Mass", cc.comments_for_result(r, "", "Closed / Withdrawn / Canceled"))

    def test_completed_response_requires_correct_identity_and_success(self):
        import json
        from urllib.parse import urlencode
        org = cc.checker.Organization("Example Foundation", "123456789")
        response = Mock(url="https://masscharities.my.site.com/FilingSearch/s/sfsites/aura")
        response.request.post_data = urlencode({"message": json.dumps({"actions": [{"id": "1", "params": {
            "classname": "AeS_Apex_Controller_Class", "method": "get_CharityInfo", "params": {"recID": "record1"}}}]})})
        for ein, state in (("123456789", "SUCCESS"), ("", "SUCCESS"), ("987654321", "SUCCESS"), ("123456789", "ERROR")):
            response.json.return_value = {"actions": [{"id": "1", "state": state, "returnValue": {"returnValue": [{
                "Id": "record1", "AGO_Charity_Number__c": "051172", "Organization_Name__c": "Example Foundation",
                "Employer_Idendification_Number_EIN__c": ein, "Charity_Status__c": "Registered"}]}}]}
            evidence = {}
            cc.ma_capture_completed_response(response, org, evidence)
            self.assertEqual(bool(evidence), ein == "123456789" and state == "SUCCESS")

    def test_only_all_filings_success_can_confirm_empty(self):
        import json
        from urllib.parse import urlencode
        response = Mock(url="https://masscharities.my.site.com/FilingSearch/s/sfsites/aura")
        for method, state, data in (("get_ALL_FILINGS_ATTACHMENTS_FOR_PUBLICUSERS", "SUCCESS", []),
                                    ("get_CHARITY_ATTACHMENTS_FOR_PUBLICUSERS", "SUCCESS", []),
                                    ("get_ALL_FILINGS_ATTACHMENTS_FOR_PUBLICUSERS", "ERROR", []),
                                    ("get_ALL_FILINGS_ATTACHMENTS_FOR_PUBLICUSERS", "SUCCESS", None)):
            response.request.post_data = urlencode({"message": json.dumps({"actions": [{"id": "1", "params": {
                "classname": "AeS_Apex_Controller_Class", "method": method, "params": {"agoNumber": "051172"}}}]})})
            response.json.return_value = {"actions": [{"id": "1", "state": state, "returnValue": {"returnValue": data}}]}
            evidence = {}
            cc.ma_capture_completed_response(response, cc.checker.Organization("Example Foundation", "123456789"), evidence)
            self.assertEqual(bool(evidence), method == "get_ALL_FILINGS_ATTACHMENTS_FOR_PUBLICUSERS" and state == "SUCCESS" and data == [])


class MassachusettsSelectionTests(unittest.TestCase):
    def setUp(self):
        self.org = cc.checker.Organization("Example Foundation", "123456789")

    def test_selection_requires_unique_safe_name_not_first_option(self):
        good = {"label": "Example Foundation", "value": "right"}
        other = {"label": "Unrelated Wildlife Association", "value": "wrong"}
        self.assertEqual(cc.ma_selection_candidate(self.org, [other, good]), good)
        self.assertEqual(cc.ma_selection_candidate(self.org, [other]), other)
        self.assertIsNone(cc.ma_selection_candidate(cc.checker.Organization("Example Foundation", ""), [other]))
        for options in ([], [good, {**good, "value": "duplicate"}],
                        [{"label": "-- Select --", "value": ""}]):
            self.assertIsNone(cc.ma_selection_candidate(self.org, options))

    def page(self, completed, finish=True, record_id="right"):
        page = Mock()
        combo = Mock()
        combo.locator.return_value.evaluate_all.return_value = [{"label": "Example Foundation", "value": "right"}]
        page.get_by_role.return_value.all.return_value = [combo]
        actions = []
        combo.select_option.side_effect = lambda **kw: actions.append("selected")
        def click(**kw):
            if actions:
                actions.append("filings")
                if finish:
                    completed.update({"record": {"record_id": record_id, "ago_account": "051172", "name": "Example Foundation"},
                                      "filings": {"051172": {"empty": False}}})
        page.get_by_role.return_value.click.side_effect = click
        return page, actions

    def test_select_then_filings_then_identity_bound_detail(self):
        completed = {}
        page, actions = self.page(completed)
        with patch.object(cc, "registry_page_body", return_value="Select a Charity"), \
             patch.object(cc, "ma_detail_body", return_value="AG Account Number 051172"), \
             patch.object(cc, "ma_read_latest_form_pc", return_value={}) as read:
            result, body = cc.search_ma_master(page, self.org, completed)
        self.assertEqual(actions, ["selected", "filings"])
        read.assert_called_once()
        self.assertEqual(result.status_reason, "MA_FORM_PC_DETAIL_UNCONFIRMED")

    def test_incomplete_or_wrong_record_never_becomes_empty_history(self):
        for finish, record_id in ((False, "right"), (True, "wrong")):
            completed = {}
            page, _ = self.page(completed, finish, record_id)
            with patch.object(cc, "registry_page_body", return_value="Select a Charity"), \
                 patch.object(cc.time, "monotonic", side_effect=[0, 0, 21]), \
                 patch.object(cc, "ma_read_latest_form_pc") as read:
                result, body = cc.search_ma_master(page, self.org, completed)
            read.assert_not_called()
            self.assertEqual(cc.true_status_from_body(result, body), "Unable to Confirm")
            self.assertEqual(result.status_reason, "MA_FILING_LIST_UNCONFIRMED")
            self.assertIn("incomplete lookup", cc.comments_for_result(result, body, result.status))
            self.assertEqual(cc.source_note_for_result(result), result.source_note)

    def test_clean_no_record_and_timeout_are_distinct(self):
        for fail in (False, True):
            page = Mock()
            if fail:
                page.goto.side_effect = TimeoutError()
            with patch.object(cc, "registry_page_body", return_value="No Charity Found"):
                result, _ = cc.search_ma_master(page, self.org, {})
            self.assertEqual(cc.public_status(result), "Unable to Confirm" if fail else "Not Registered")


if __name__ == "__main__":
    unittest.main(verbosity=2)
