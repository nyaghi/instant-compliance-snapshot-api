import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import registry_snapshot_server as cc
from deployment.source_visual_adapters import capture_owned_fl_page
from testing.test_fl_initial_recovery import run_case


class FloridaDelayedRecovery(unittest.TestCase):
    def test_replays_recorded_organizations_under_one_bound(self):
        path = os.environ.get("CC_FL_MIGRATION_ROSTER")
        if not path:
            self.skipTest("Provide at least 100 distinct archived audit organizations.")
        with Path(path).open(encoding="utf-8") as roster:
            cases = json.load(roster)
        self.assertGreaterEqual(len({case["ein"] for case in cases}), 100)
        for case in cases:
            with self.subTest(ein=case["ein"]):
                old, original_visits, original_wire, original_seconds, *_ = run_case(case)
                healthy, visits, wire, seconds, *_ = run_case(case, migration=True)
                self.assertEqual((healthy.status, healthy.success, healthy.matched_registry_identifier),
                                 (old.status, old.success, old.matched_registry_identifier))
                self.assertEqual((visits, wire, seconds), (original_visits, original_wire, original_seconds))

                old_failure, _, old_wire, _, *_ = run_case(
                    case, first_error=TimeoutError(), verified_entry_failures=1)
                self.assertEqual(old_failure.reason_code, "FL_SOURCE_NOT_RESPONDING")
                self.assertEqual(len(old_wire), 1)
                recovered, _, recovery_wire, elapsed, page, _ = run_case(
                    case, first_error=TimeoutError(), verified_entry_failures=1,
                    migration=True, business_delay=8.4)
                self.assertTrue(recovered.success)
                self.assertEqual((recovered.status, recovered.matched_registry_identifier),
                                 (healthy.status, healthy.matched_registry_identifier))
                self.assertEqual([request["method"] for request in recovery_wire], ["GET", "GET"])
                self.assertAlmostEqual(recovery_wire[1]["start"] - recovery_wire[0]["start"], 11.1)
                self.assertLess(elapsed, 44)
                # Recovery binds the final selected legacy row to the existing
                # screenshot admission. A changed record cannot reuse it.
                run = SimpleNamespace(state="FL", ein=cc.canonical_ein_digits(case["ein"]),
                                      allow_selected_screenshot=MagicMock())
                capture_owned_fl_page(cc, run, dict(
                    source_url=recovered.source_url, state="FL", ein=case["ein"], success=True,
                    status=recovered.status, matched_registry_identifier=recovered.matched_registry_identifier,
                    selected_legacy_row=recovered._cc_fl_selected_row_text), page, MagicMock(), 44)
                _, capture_stop, guard = run.allow_selected_screenshot.call_args.args
                self.assertEqual(capture_stop, 44)
                self.assertTrue(guard(recovered._cc_fl_selected_row_text))
                self.assertFalse(guard(recovered._cc_fl_selected_row_text.replace("CH12345", "CH99999")))

                failed, _, attempts, end, *_ = run_case(
                    case, first_error=TimeoutError(), unavailable=True, migration=True, business_delay=8.4)
                self.assertEqual(failed.reason_code, "FL_SOURCE_NOT_RESPONDING")
                self.assertFalse(failed.success)
                self.assertEqual(len(attempts), 2)
                self.assertLessEqual(end, 44)
                for negative, wrong_ein in ((True, False), (False, True)):
                    answer, _, searches, end, *_ = run_case(
                        case, first_error=TimeoutError(), verified_entry_failures=1, migration=True,
                        business_delay=8.4, negative=negative, wrong_ein=wrong_ein)
                    self.assertTrue(answer.success)
                    self.assertEqual(answer.status, cc.checker.STATUS_NOT_REGISTERED)
                    self.assertFalse(answer.matched_registry_identifier)
                    self.assertEqual(len(searches), 2)
                    self.assertLessEqual(end, 44)

    def test_no_delayed_open_when_budget_is_insufficient(self):
        case = {"name": "Sample Charity", "ein": "12-3456789"}
        result, _, wire, elapsed, *_ = run_case(
            case, first_error=TimeoutError(), unavailable=True, migration=True,
            business_delay=8.4, absolute_stop=37)
        self.assertFalse(result.success)
        self.assertEqual(result.reason_code, "FL_SOURCE_NOT_RESPONDING")
        self.assertEqual(len(wire), 1)
        self.assertLess(elapsed, 37)

    def test_no_delayed_open_on_rejected_response(self):
        case = {"name": "Sample Charity", "ein": "12-3456789"}
        result, _, wire, elapsed, *_ = run_case(
            case, first_error=ValueError("HTTP 403"), migration=True, business_delay=8.4)
        self.assertFalse(result.success)
        self.assertEqual(wire, [])
        self.assertLess(elapsed, 44)
