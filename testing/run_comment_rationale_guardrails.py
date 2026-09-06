"""Evidence-to-status explanations: accuracy, preserved uncertainty, and no lookup work."""
import copy
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc


class AsOf(date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 6)


class CommentTests(unittest.TestCase):
    def setUp(self):
        self.clock = patch.object(cc, "date", AsOf)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.network = patch.object(cc.urllib.request, "urlopen", side_effect=AssertionError("Comments must not make network requests"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def result(self, state="CO", status="Current", raw="Expires on 4/15/2027", **fields):
        r = cc.checker.StateResult("Example National Foundation", "012345678", state, status, "https://example.org")
        r.raw_status_text = raw
        r.success = True
        for key, value in fields.items():
            setattr(r, key, value)
        return r

    def comment(self, r, body=""):
        before = copy.deepcopy(vars(r))
        text = cc.comments_for_result(r, body, r.status)
        self.assertEqual(before, vars(r), "Comment generation mutated the evidence/status")
        return text

    def test_expiration_current_has_date_timing_and_conclusion(self):
        text = self.comment(self.result())
        for fragment in ("4/15/2027", "more than six months", "Current"):
            self.assertIn(fragment, text)

    def test_six_month_boundary_and_today(self):
        for due, status, phrase in [(date(2027, 3, 6), "Upcoming Filing", "within the next six months"), (date(2027, 3, 7), "Current", "more than six months"), (date(2026, 9, 6), "Upcoming Filing", "is today"), (date(2026, 9, 5), "Delinquent", "has passed")]:
            self.assertIn(phrase, cc.comment_date_conclusion(due, status))

    def test_timing_is_not_invented_to_fit_a_status(self):
        text = cc.comment_date_conclusion(date(2027, 5, 1), "Delinquent")
        self.assertIn("more than six months", text)
        self.assertNotIn("has passed", text)

    def test_due_date_uses_labeled_field_not_registration_date(self):
        text = self.comment(self.result(raw="Registration Date: 1/1/2000 | Expiration Date: 4/15/2027"))
        self.assertIn("4/15/2027", text)
        self.assertNotIn("1/1/2000", text)

    def test_iso_expiration_not_future_evaluation_date(self):
        text = self.comment(self.result("CA", "Delinquent", "Current Expiration Date: 2026-01-15 | Renewal Evaluation Date: 2027-01-15"))
        self.assertIn("1/15/2026", text)
        self.assertNotIn("1/15/2027", text)

    def test_calculated_year_and_period(self):
        text = self.comment(self.result("MN", "Delinquent", "Fiscal Year Ending 8/31/2024 | Next Required Period: 8/31/2025 | Next Filing Due: 3/15/2026"))
        for fragment in ("8/31/2024", "8/31/2025", "3/15/2026", "has passed", "Delinquent"):
            self.assertIn(fragment, text)

    def test_suspended_is_not_revoked_or_a_date_result(self):
        text = self.comment(self.result("FL", "Suspended", "Status: Suspended | Expiration Date: 12/31/2027"))
        self.assertIn('"Suspended"', text)
        self.assertNotIn("revoked", text.lower())
        self.assertNotIn("Current", text)

    def test_revoked_remains_distinct(self):
        text = self.comment(self.result("NJ", "Revoked", "Revoked"))
        self.assertIn('"Revoked"', text)
        self.assertNotIn("suspended", text.lower())

    def test_pending_and_failed_to_renew_are_specific(self):
        for status, raw in [("Pending", "Registration Pending"), ("Failed to Renew", "Failed to Renew")]:
            self.assertIn('"'+raw+'"', self.comment(self.result("ME", status, raw)))

    def test_closed_preserves_actual_reason(self):
        text = self.comment(self.result("ND", "Closed / Withdrawn / Canceled", "Inactive - Involuntary"))
        self.assertIn('"Inactive - Involuntary"', text)

    def test_exemption_is_not_guessed_from_missing_dates(self):
        text = self.comment(self.result("VA", "Exempt", "Registration Type: Exempt Charity"))
        self.assertIn('"Exempt Charity"', text)
        self.assertNotIn("all filing requirements", text)

    def test_no_record_requires_completed_search_language(self):
        text = self.comment(self.result("OK", "Not Registered", "No safely matching filing number link"))
        self.assertIn("completed", text)
        self.assertIn("organization", text)
        self.assertNotIn("normalized", text)

    def test_incomplete_negative_is_disclosed_not_asserted(self):
        r = self.result("OK", "Not Registered", "search incomplete")
        r.success = False
        self.assertIn("Non-registration could not be confirmed", self.comment(r))

    def test_unavailable_has_reason_without_debug_jargon(self):
        text = self.comment(self.result("NY", "Site Not Reachable", "HTTP 520 timeout"))
        self.assertIn("did not respond in time", text)
        self.assertNotIn("HTTP", text)
        self.assertIn("does not mean", text)

    def test_matched_but_incomplete_is_not_called_delinquent(self):
        text = self.comment(self.result("NM", "Unable to Verify", "Incomplete detail", matched_registry_name="Example"))
        self.assertIn("organization was found", text)
        self.assertIn("insufficient", text)
        self.assertNotIn("status as Delinquent", text)

    def test_missing_filing_rule_discloses_inference_limit(self):
        text = self.comment(self.result("HI", "Delinquent", "Active", matched_registry_name="Example"))
        self.assertIn("annual filing year", text)
        self.assertIn("does not independently confirm", text)

    def test_certificate_and_calculation_are_distinguished(self):
        cert = self.comment(self.result("OK", "Current", "123 Renewal Registration June 15, 2026 2 | Certificate Expiration Date: 6/15/2027"))
        calc = self.comment(self.result("OK", "Current", "123 Renewal Registration June 15, 2026 2 | Calculated Registration Expiration: 6/15/2027"))
        self.assertIn("certificate shows", cert)
        self.assertIn("not certificate-confirmed", calc)
        self.assertIn("6/15/2026", calc)
        self.assertIn("more than six months", calc)

    def test_cached_certificate_disclosure_is_preserved(self):
        r = self.result("OK", "Current", "Certificate Expiration Date: 6/15/2027", source_note="Certificate freshness note: reused the verified certificate retrieved 2026-09-06 10:00:00 UTC (less than 24 hours old).")
        self.assertIn("2026-09-06 10:00:00 UTC", self.comment(r))

    def test_all_five_downloadable_states_keep_freshness(self):
        for state in ("KS", "KY", "LA", "NH", "OR"):
            text = self.comment(self.result(state, "Not Registered", "No matching record"))
            self.assertIn("Data freshness note:", text)
            self.assertIn("downloadable charity list", text)

    def test_oh_partial_access_uses_confirmed_positive_evidence(self):
        text = self.comment(self.result("OH", "Current", "In Compliance: Yes | Detail page unavailable"))
        self.assertIn('"In Compliance: Yes"', text)
        self.assertIn("could not be confirmed", text)

    def test_va_extension_is_explained(self):
        text = self.comment(self.result("VA", "Upcoming Filing", "Expiration Date: 5/15/2026 | Extension Date: 11/15/2026 | Status: Registered"))
        self.assertIn("5/15/2026", text)
        self.assertIn("11/15/2026", text)
        self.assertIn("effective deadline", text)

    def test_ms_calculated_renewal_not_described_as_state_expiration(self):
        text = self.comment(self.result("MS", "Upcoming Filing", "Current - Registered | Expiration Date not visible; MS annual renewal date used: 11/15/2026"))
        self.assertIn("calculated", text)
        self.assertIn("11/15/2026", text)

    def test_nd_uses_report_deadline_not_unrelated_profile_period(self):
        text = self.comment(self.result("ND", "Current", "Active"), "Status Active\nAR Due Date\t9/1/2027\nRegistration Date 2/18/2014")
        self.assertIn("annual report due date", text)
        self.assertIn("9/1/2027", text)
        self.assertNotIn("2014", text)

    def test_la_positive_record_has_expiration_and_freshness(self):
        text = self.comment(self.result("LA", "Current", "Registered Through: 4/15/2027", computed_due_date="4/15/2027"))
        self.assertIn("registration expiration", text)
        self.assertIn("more than six months", text)
        self.assertIn("Data freshness note", text)

    def test_ca_annual_filing_status_explains_pending(self):
        with patch.object(cc, "ca_annual_renewal_years_from_text", return_value={"latest_pending_year":2025,"latest_pending_status":"In Process","latest_submitted_year":2024}):
            text = self.comment(self.result("CA", "Pending", "Registered"))
        self.assertIn('2025 filing as "In Process"', text)
        self.assertIn("still being processed", text)

    def test_not_visible_does_not_mean_no_filings_exist(self):
        text = self.comment(self.result("MA", "Delinquent", "Annual Filings not visible"))
        self.assertIn("does not establish that the state has no filings", text)

    def test_incomplete_retry_replaces_obsolete_negative_comment(self):
        r = {"state":"CT","status":"Not Registered","comments":"No record found; Not Registered.","raw_status_text":"Search incomplete"}
        updated = cc.conservative_incomplete_lookup_result(r, "CT")
        self.assertEqual(updated["status"], "Unable to Confirm")
        self.assertNotIn("No record found", updated["comments"])
        self.assertIn("search remained incomplete", updated["comments"])
        self.assertEqual(r["status"], "Not Registered")

    def test_nm_open_year_replaces_obsolete_negative_comment(self):
        r = {"state":"NM","ein":"012345678","status":"Not Registered","comments":"No matching charity; Not Registered.","raw_status_text":"Tax Year Registration Open"}
        updated = cc.nm_tax_year_open_detail_result(r)
        self.assertEqual(updated["status"], "Delinquent")
        self.assertNotIn("Not Registered", updated["comments"])
        self.assertIn("specific overdue deadline was not confirmed", updated["comments"])

    def test_batch_followup_explains_status_change(self):
        original = {"organization_name":"Example","ein":"012345678","state":"CO","status":"Site Not Reachable","comments":"Check failed"}
        confirmed = {**original,"status":"Current","comments":"The certificate expires 6/15/2027, more than six months away, so the status is Current."}
        with patch.object(cc,"run_state_lookup_for_batch",return_value=confirmed), patch.object(cc,"BATCH_NO_MATCH_CONFIRMATION_DELAY_SECONDS",0), patch.object(cc,"CONFIRM_FRAGILE_BATCH_RESULTS",True), patch.object(cc,"fragile_batch_result_needs_confirmation",return_value=True):
            rows = cc.confirm_fragile_batch_results([original])
        self.assertEqual(rows[0]["status"], "Current")
        self.assertIn("first check returned Site Not Reachable", rows[0]["comments"])
        self.assertNotIn("isolated", rows[0]["comments"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
