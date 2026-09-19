"""Completed ND result consensus: full identity, explicit status, no extra requests."""
import itertools
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc


def row(identifier, name="Example Relief", status="Inactive - Involuntary"):
    return {"ID": identifier, "RECORD_NUM": str(identifier), "TITLE": [name], "STATUS": status}


class InactiveConsensusTests(unittest.TestCase):
    def lookup(self, rows, *, name="Example Relief", detail_status="Active", detail_extra=(), http=200, incomplete=False):
        page = Mock()
        data = {"template": [], "rows": {str(i): r for i, r in enumerate(rows)}}
        if incomplete:
            data.pop("template")
        detail = {"DRAWER_DETAIL_LIST": [{"LABEL": "Status", "VALUE": detail_status}, *detail_extra]}
        def response(value):
            pending = SimpleNamespace(value=SimpleNamespace(status=http, json=lambda: value))
            context = Mock()
            context.__enter__ = Mock(return_value=pending)
            context.__exit__ = Mock(return_value=False)
            return context
        page.expect_response.side_effect = [response(data), response(detail)]
        org = cc.checker.Organization(name, "123456789")
        with patch.object(cc, "nd_search_queries", return_value=[name]):
            result = cc.search_nd_completed(page, org)
        return result, page, org

    def test_reported_rows_both_orders_return_consensus_without_detail_request(self):
        records = [row("0005917531", "The American Tinnitus Association"),
                   row("0004011262", "THE AMERICAN TINNITUS ASSOCIATION")]
        for ordered in itertools.permutations(records):
            result, page, org = self.lookup(ordered, name="American Tinnitus Association")
            self.assertTrue(result.success)
            self.assertEqual(result.status, "Closed / Withdrawn / Canceled")
            self.assertEqual(result.matched_registry_identifier, "0004011262, 0005917531")
            self.assertEqual(page.expect_response.call_count, 1)
            page.get_by_role.assert_not_called()
            with patch.object(cc, "filing_context", return_value={"due_date": None, "represented_year": None, "fiscal_end": None}):
                output = cc.response_data_for_lookup(result, result._cc_detail_body, org, org.organization_name, org.ein, "ND", time.perf_counter())
            self.assertEqual(output["status"], "Closed / Withdrawn / Canceled")
            self.assertIn("all explicitly inactive", output["comments"])
            self.assertIn("0005917531", output["comments"])
            self.assertIn("0004011262", output["comments"])
            self.assertFalse(output.get("computed_due_date"))

    def test_generic_names_not_organization_specific(self):
        for name in ["Beacon Science Network", "River Education Alliance", "Evergreen Assistance"]:
            result, _, _ = self.lookup([row(1, name), row(2, name.upper())], name=name)
            self.assertEqual(result.status, "Closed / Withdrawn / Canceled")

    def test_all_tied_rows_must_agree(self):
        for status in ["", "Unknown", "Pending", "Suspended", "Revoked", "Not Registered", "Delinquent", "Inactive pending review", "Not inactive"]:
            with self.subTest(status=status):
                result, page, _ = self.lookup([row(1), row(2), row(3, status=status)], detail_status=status)
                self.assertNotEqual(getattr(result, "status_reason", ""), "ND_MATCHING_RECORDS_INACTIVE")
                self.assertNotEqual(cc.public_status(result), "Closed / Withdrawn / Canceled")
                # Existing ranking may select a non-terminal record for detail.
                # Only the new consensus path must reject conflicting evidence.
                if result.status == "Unable to Confirm":
                    self.assertFalse(result.success)

    def test_inactive_status_vocabulary_and_spacing(self):
        for status in ["Inactive", "INACTIVE - INVOLUNTARY", "Inactive - Voluntary", " Inactive – Involuntary "]:
            result, _, _ = self.lookup([row(1), row(2, status=status)])
            self.assertEqual(result.status, "Closed / Withdrawn / Canceled")

    def test_active_preference_still_selects_the_active_detail(self):
        for ordered in itertools.permutations([row(1), row(2, status="Active")]):
            result, page, _ = self.lookup(ordered)
            self.assertEqual(result.status, "Active")
            self.assertEqual(result.matched_registry_identifier, "2")
            self.assertEqual(page.expect_response.call_count, 2)
            page.get_by_role.assert_any_call("cell", name="2", exact=True)

    def test_two_active_records_are_not_assumed_current(self):
        result, page, _ = self.lookup([row(1, status="Active"), row(2, status="Active")])
        self.assertEqual(result.status, "Unable to Confirm")
        self.assertEqual(page.expect_response.call_count, 1)

    def test_single_inactive_record_keeps_detail_path(self):
        result, page, _ = self.lookup([row(1)], detail_status="Inactive - Involuntary")
        self.assertEqual(result.raw_status_text, "Inactive - Involuntary")
        self.assertEqual(page.expect_response.call_count, 2)
        self.assertEqual(cc.public_status(result), "Closed / Withdrawn / Canceled")

    def test_unrelated_and_local_chapter_rows_never_join_consensus(self):
        for name in ["Different Relief", "Example Relief Wisconsin Chapter", "Example Relief - Madison", "Example Relief Academy"]:
            result, page, _ = self.lookup([row(1), row(2, name)], detail_status="Inactive - Involuntary")
            self.assertEqual(result.matched_registry_identifier, "1")
            self.assertEqual(page.expect_response.call_count, 2)

    def test_fuzzy_equal_scores_do_not_establish_consensus(self):
        with patch.object(cc, "registry_name_is_safe_against_targets", return_value=True), \
                patch.object(cc.checker, "candidate_selection_score_for_targets", return_value=(700, 0)):
            result, _, _ = self.lookup([row(1, "Example Relief Foundation"), row(2, "Example Relief Society")])
        self.assertEqual(result.status, "Unable to Confirm")

    def test_reviewed_full_alias_remains_eligible(self):
        token = cc.REVIEWED_NAME_CONTEXT.set({"123456789": ["Former Relief Network"]})
        try:
            result, _, _ = self.lookup([row(1, "Former Relief Network"), row(2, "Former Relief Network, Inc.")])
            self.assertEqual(result.status, "Closed / Withdrawn / Canceled")
        finally:
            cc.REVIEWED_NAME_CONTEXT.reset(token)

    def test_nonmatching_completed_search_is_still_not_registered(self):
        for rows in [[], [row(1, "Different Relief"), row(2, "Other Alliance")]]:
            result, _, _ = self.lookup(rows)
            self.assertEqual(result.status, cc.checker.STATUS_NOT_REGISTERED)
            self.assertTrue(result.success)

    def test_http_failure_cannot_be_classified_from_cached_rows(self):
        result, _, _ = self.lookup([row(1), row(2)], http=503)
        self.assertEqual(result.status, "Site Not Reachable")
        self.assertFalse(result.success)

    def test_missing_response_structure_is_not_consensus(self):
        result, _, _ = self.lookup([row(1), row(2)], incomplete=True)
        self.assertEqual(result.status, "Unable to Confirm")
        self.assertFalse(result.success)

    def test_malformed_row_is_not_skipped_to_create_consensus(self):
        result, _, _ = self.lookup([row(1), row(2), {"ID": 3}])
        self.assertEqual(result.status, "Unable to Confirm")
        self.assertFalse(result.success)

    def test_missing_selected_detail_status_remains_incomplete(self):
        result, _, _ = self.lookup([row(1)], detail_status="")
        self.assertEqual(result.status, "Unable to Confirm")

    def test_status_branch_does_not_apply_to_another_state(self):
        result, _, _ = self.lookup([row(1), row(2)])
        result.state = "ME"
        self.assertNotEqual(cc.comments_for_result_base(result, "", result.status), result.source_note)

    def test_only_top_ranked_matching_records_are_combined(self):
        records = [row(1), row(2), row(3, "Different Relief", "Active")]
        for ordered in itertools.permutations(records):
            result, _, _ = self.lookup(ordered)
            self.assertEqual(result.matched_registry_identifier, "1, 2")
            self.assertEqual(result.status, "Closed / Withdrawn / Canceled")


if __name__ == "__main__":
    unittest.main(verbosity=2)
