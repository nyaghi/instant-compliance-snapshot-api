"""Alaska search completion, bounded step retry, and negative-result controls."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc

class AlaskaCompletionTests(unittest.TestCase):
    def lookup(self, submit):
        browser = Mock()
        org = cc.checker.Organization("Junior Achievement USA", "84-1267604")
        with patch.object(cc, "ak_latest_registration_cycle", return_value=2027), \
             patch.object(cc, "AK_RECENT_FILING_CUTOFF_YEAR", 2023), \
             patch.object(cc, "AK_HISTORICAL_IDENTITY_FLOOR_YEAR", 2019), \
             patch.object(cc, "AK_NAME_FALLBACK_AFTER_EIN_NO_ROWS", False), \
             patch.object(cc, "configure_browser_context"), \
             patch.object(cc.checker, "open_ak_public_search", return_value=True), \
             patch.object(cc, "fill_ak_search_form_ein_fast", side_effect=submit), \
             patch.object(cc, "registry_page_body", return_value="There are no charitable organizations."), \
             patch.object(cc, "find_ak_print_link_relaxed", return_value=None), \
             patch.object(cc, "find_ak_result_row_relaxed", return_value=None):
            return cc.search_ak_with_registration_evidence(browser, org, "fixture")[0]

    def test_completed_search_visits_each_required_year_once(self):
        years = []
        result = self.lookup(lambda page, org, year: years.append(year))
        self.assertEqual(years, list(range(2027, 2018, -1)))
        self.assertEqual(result.status, cc.checker.STATUS_NOT_REGISTERED)
        self.assertEqual(result.reason_code, "AK_COMPLETED_EIN_SEARCH")

    def test_transient_failure_retries_only_failed_year(self):
        years = []
        def submit(page, org, year):
            years.append(year)
            if year == 2026 and years.count(year) == 1:
                raise TimeoutError("one slow query")
        result = self.lookup(submit)
        self.assertEqual(years, [2027, 2026, 2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019])
        self.assertEqual(result.status, cc.checker.STATUS_NOT_REGISTERED)

    def test_persistent_failed_year_cannot_become_negative(self):
        years = []
        def submit(page, org, year):
            years.append(year)
            if year == 2026:
                raise TimeoutError("unavailable")
        result = self.lookup(submit)
        self.assertEqual(years.count(2026), 2)
        self.assertEqual(result.status, "Unable to Verify")
        self.assertFalse(result.success)
        self.assertEqual(result.reason_code, "AK_INCOMPLETE_SEARCH")
        self.assertNotIn("2026", result.source_attempts[0])

    def test_confirmed_negative_does_not_repeat_complete_lookup(self):
        result = {"state": "AK", "status": "Not Registered", "reason_code": "AK_COMPLETED_EIN_SEARCH"}
        with patch.object(cc, "run_state_lookup", return_value=result) as lookup:
            actual = cc.run_single_state_lookup_reliably("Control", "123456789", "AK")
        lookup.assert_called_once()
        self.assertEqual(actual["semantic_attempts"], 1)

    def test_legacy_unconfirmed_negative_keeps_confirmation_safeguard(self):
        result = {"state": "AK", "status": "Not Registered", "reason_code": "NO_CANDIDATES"}
        with patch.object(cc, "run_state_lookup", return_value=result) as lookup, \
             patch.object(cc, "SINGLE_STATE_SEMANTIC_RETRY_DELAY_SECONDS", 0):
            cc.run_single_state_lookup_reliably("Control", "123456789", "AK")
        self.assertEqual(lookup.call_count, 3)

    def test_empty_result_shell_raises_instead_of_confirming_negative(self):
        page = Mock()
        page._ak_search_deadline = 0
        with self.assertRaises(TimeoutError):
            cc.wait_ak_search_results(page, completed_no_rows=False)

if __name__ == "__main__": unittest.main()
