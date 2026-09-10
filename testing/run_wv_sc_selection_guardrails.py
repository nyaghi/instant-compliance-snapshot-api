"""Offline regression for WV duplicate records and SC explicit name aliases."""
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc


class Today(date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 10)


class SelectionTests(unittest.TestCase):
    def setUp(self):
        for p in (patch.object(cc, "date", Today), patch.object(cc, "known_names_for_ein", return_value=[])):
            p.start()
            self.addCleanup(p.stop)

    def wv(self, records, name="Comic Relief, Inc.", detail_name=None):
        page = Mock()
        selected = []
        rows = []
        for identifier, registry_name, status in records:
            row = Mock()
            cells = [Mock() for _ in range(5)]
            for cell, value in zip(cells, [identifier, registry_name, "Address", "Charity", status]):
                cell.inner_text.return_value = value
            cell_list = Mock()
            cell_list.count.return_value = 5
            cell_list.nth.side_effect = cells.__getitem__
            link = Mock()
            link.first.click.side_effect = lambda *a, r=(identifier, registry_name, status), **k: selected.append(r)
            row.locator.side_effect = lambda selector, cl=cell_list, li=link: cl if selector == "td" else li
            rows.append(row)
        row_list = Mock()
        row_list.count.return_value = len(rows)
        row_list.nth.side_effect = rows.__getitem__
        page.locator.side_effect = lambda selector: row_list if selector == "tr" else Mock()
        def body(_):
            if not selected:
                return "Search results" if records else "No records found"
            identifier, registry_name, status = selected[-1]
            return (f"Organization Name\n{detail_name or registry_name}\nExpiration Date\n03/14/2027\n"
                    f"Contact Name\nControl\nStatus\n{status}\nStreet Address\nAddress")
        with patch.object(cc, "registry_page_body", side_effect=body), \
             patch.object(cc, "safe_wait_for_network_idle"), \
             patch.object(cc, "wv_preferred_query_variants", return_value=[name]):
            result = cc.search_wv_precise(page, cc.checker.Organization(name, "010885377"))
        return result, selected

    def test_wv_active_wins_both_result_orders(self):
        closed = ("664", "Comic Relief, Inc.", "Closed")
        active = ("5533", "Comic Relief, Inc.", "Active")
        for records in ([closed, active], [active, closed]):
            with self.subTest(records=records):
                result, selected = self.wv(records)
                self.assertEqual(selected[0][0], "5533")
                self.assertEqual(result.status, "Current")
                self.assertEqual(result.matched_registry_identifier, "5533")

    def test_wv_active_alias_beats_closed_legal_name(self):
        result, selected = self.wv([
            ("1", "Example Relief Inc", "Closed"),
            ("2", "Example Aid", "Active"),
        ], "Example Relief Inc / Example Aid")
        self.assertEqual(selected[0][0], "2")
        self.assertEqual(result.status, "Current")

    def test_wv_unrelated_active_cannot_replace_matching_closed(self):
        result, selected = self.wv([
            ("664", "Comic Relief, Inc.", "Closed"),
            ("9", "Unrelated Relief Charity", "Active"),
        ])
        self.assertEqual(selected[0][0], "664")
        self.assertEqual(result.status, "Closed / Withdrawn / Canceled")

    def test_wv_closed_only_is_preserved(self):
        result, _ = self.wv([("664", "Comic Relief, Inc.", "Closed")])
        self.assertEqual(result.status, "Closed / Withdrawn / Canceled")

    def test_wv_inactive_is_not_active_substring(self):
        result, selected = self.wv([
            ("1", "Comic Relief, Inc.", "Inactive"),
            ("2", "Comic Relief, Inc.", "Active"),
        ])
        self.assertEqual(selected[0][0], "2")

    def test_wv_mismatched_detail_is_rejected(self):
        result, _ = self.wv([("5533", "Comic Relief, Inc.", "Active")], detail_name="Unrelated Relief Charity")
        self.assertNotEqual(result.status, "Current")
        self.assertFalse(result.matched_registry_identifier)

    def test_wv_no_rows_preserves_completed_negative(self):
        with patch.object(cc, "wv_core_search_completed", return_value=True):
            result, selected = self.wv([])
        self.assertEqual(result.status, cc.checker.STATUS_NOT_REGISTERED)
        self.assertFalse(selected)

    def test_wv_transport_failure_is_inconclusive(self):
        page = Mock()
        page.goto.side_effect = TimeoutError("Navigation timeout")
        result = cc.search_wv_precise(page, cc.checker.Organization("Comic Relief", "010885377"))
        self.assertFalse(result.success)
        self.assertNotEqual(result.status, "Not Registered")

    def sc_official(self, name, registry_name, status="Registered", due="11/15/2026"):
        session = Mock()
        session.get.return_value.text = "<form></form>"
        def post(_url, data, **kwargs):
            response = Mock()
            response.text = (f"Public Id P35089 Status {status} Due Date {due}" if "ctl00$MainContent$Hidden_CharityID" in data
                             else f'<a href="javascript:CharityInfo(35089)">{registry_name}</a>')
            return response
        session.post.side_effect = post
        with patch.object(cc, "curl_requests", Mock(Session=Mock(return_value=session))), \
             patch.object(cc, "build_search_queries", return_value=["Eckerd"]):
            return cc.sc_official_detail_lookup(cc.checker.Organization(name, "592551416"))

    def test_sc_official_combined_and_separate_names(self):
        combined = "Eckerd Youth Alternatives, Inc. / Eckerd Connects"
        for name, registry in [(combined, "Eckerd Youth Alternatives Inc"), (combined, "Eckerd Connects"),
                               ("Eckerd Youth Alternatives, Inc.", "Eckerd Youth Alternatives Inc"),
                               ("Eckerd Connects", "Eckerd Connects")]:
            with self.subTest(name=name, registry=registry):
                result = self.sc_official(name, registry)
                self.assertIsNotNone(result)
                self.assertEqual(result.status, "Upcoming Filing")
                self.assertEqual(result.matched_registry_identifier, "P35089")

    def test_sc_fallback_retains_combined_alias(self):
        name = "Eckerd Youth Alternatives, Inc. / Eckerd Connects"
        result = cc.checker.StateResult(name, "592551416", "SC", "Upcoming Filing", "https://search.scsos.com/charities",
                                        raw_status_text="Due Date 11/15/2026", matched_registry_name="Eckerd Youth Alternatives Inc", success=True)
        with patch.object(cc, "sc_official_detail_lookup", return_value=None), \
             patch.object(cc, "preflight_name_search_registry", return_value=(True, "", None)), \
             patch.object(cc, "search_with_name_variants", return_value=result):
            actual = cc.search_sc_resilient(Mock(), cc.checker.Organization(name, "592551416"))
        self.assertEqual(actual.status, "Upcoming Filing")
        self.assertTrue(actual.success)

    def test_sc_extension_guard_still_rejects_different_entity(self):
        name = "Example Foundation"
        targets = cc.organization_match_target_variants(name)
        self.assertTrue(cc.distinctive_entity_extension_mismatch_against_targets(name, "Example Foundation Academy", targets))
        self.assertIsNone(self.sc_official(name, "Example Foundation Academy"))

    def test_sc_existing_terminal_and_date_rules_preserved(self):
        for status, expected in [("Closed", "Closed / Withdrawn / Canceled"), ("Exempt", "Exempt"),
                                 ("Suspended", "Suspended"), ("Delinquent", cc.checker.STATUS_DELINQUENT)]:
            with self.subTest(status=status):
                result = self.sc_official("Eckerd Connects", "Eckerd Connects", status)
                self.assertEqual(result.status, expected)


if __name__ == "__main__":
    unittest.main()
