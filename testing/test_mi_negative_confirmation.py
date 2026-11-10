"""Regression for Michigan negatives derived from one HTTP session."""
import ast
from contextlib import nullcontext
from pathlib import Path
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

import registry_snapshot_server as cc
from testing.run_mi_name_fallback_guardrails import frame_for, link

EMPTY = ('<html><body><h1>Search Results</h1><span id="ctl00_MainContent_lblSearchResults">'
         'Results for the following input: Organization Type: Charity or Public Safety Organization<br>'
         'EIN: 63-1135091; 0 record(s) found</span><table id="ctl00_MainContent_GridView1">'
         '<tr><td>No records found for your search criteria</td></tr></table></body></html>')

NAME = "Equal Justice Initiative"
EIN = "63-1135091"
RESULTS = "https://www.ag.state.mi.us/CharitableTrust/frmSearchResults.aspx"
PREFIX = ("Results for the following input: Organization Type: Charity or Public Safety Organization "
          f"EIN: {EIN}; ")


class MichiganNegativeConfirmation(unittest.TestCase):
    def setUp(self):
        self.org = cc.checker.Organization(NAME, EIN)

    def lookup(self, *, rows=(), echo=None, grid="No records found for your search criteria", url=RESULTS,
               old_status=None, deadline=None):
        frame = frame_for(rows)
        frame.url = url
        links = frame.locator.return_value
        fields = {"#ctl00_MainContent_lblSearchResults": Mock(inner_text=Mock(
            return_value=echo if echo is not None else PREFIX + f"{len(rows)} record(s) found")),
            "#ctl00_MainContent_GridView1": Mock(inner_text=Mock(return_value=grid))}
        frame.locator.side_effect = lambda selector: fields.get(selector, links)
        page = Mock()
        page.expect_navigation.return_value = nullcontext()
        page._cc_mi_lookup_deadline = time.perf_counter() + (60 if deadline is None else deadline)
        page._cc_mi_search_progress = {"identity": (NAME, "631135091"), "completed_empty_name_queries": [NAME]}
        module = SimpleNamespace(open_search_form=Mock(return_value=True), find_results_frame=Mock(return_value=frame),
                                 body_text=Mock(return_value=old_status or f"{len(rows)} record(s) found"),
                                 normalize_name=cc.normalized_match_name, MI_SEARCH_URL=RESULTS,
                                 format_ein=lambda value: value)
        with patch.object(cc, "state_extension_module", return_value=module), \
             patch.object(cc, "patch_mi_module_for_fast_lookups"), \
             patch.object(cc, "mi_name_fallback_queries", return_value=[NAME, "The " + NAME]):
            result = cc.search_mi_name_fallback(page, self.org, confirm_ein=True)
        return result, page

    def test_initial_http_zero_does_not_skip_the_live_browser_query(self):
        result, page = self.lookup(rows=[link(NAME, "58055", expiration="9/30/2037")])
        self.assertEqual((result.status, result.matched_registry_identifier), ("Current", "58055"))
        self.assertEqual(result.queries_attempted, [EIN])
        page.expect_navigation.assert_called_once()
        self.assertLessEqual(page.expect_navigation.call_args.kwargs["timeout"], 20000)

    def test_genuine_negative_with_matching_echo_and_empty_grid(self):
        result, _ = self.lookup()
        self.assertTrue(result.success)
        self.assertEqual(cc.public_status(result), "Not Registered")
        self.assertEqual(result.queries_attempted, [EIN])

    def test_wrong_echo_incomplete_grid_and_official_url_are_required(self):
        for kwargs in (
            {"echo": PREFIX.replace(EIN, "63-9999999") + "0 record(s) found"},
            {"grid": "Loading"}, {"url": "https://example.org/"},
            {"rows": [link("Unrelated Group", "12345")]},
            {"rows": [link(NAME, "58055")], "old_status": "0 record(s) found"},
            {"deadline": -1},
        ):
            with self.subTest(kwargs=kwargs):
                result, _ = self.lookup(**kwargs)
                self.assertFalse(result.success)
                self.assertEqual(result.status, "Unable to Verify")
                self.assertEqual(result.reason_code, "MI_NEGATIVE_CONFIRMATION_INCOMPLETE")

    def test_ein_retry_runs_before_any_name_search(self):
        for retry_status, success, reason in [
            ("Current", True, "MATCH_EIN_EXACT"),
            ("Not Registered", True, "MI_BROWSER_EIN_NO_MATCH"),
            ("Unable to Verify", False, "MI_NEGATIVE_CONFIRMATION_INCOMPLETE"),
        ]:
            with self.subTest(retry_status=retry_status):
                session = MagicMock()
                session.get.return_value.text = ""
                session.post.side_effect = [MagicMock(text=""),
                    SimpleNamespace(status_code=200, url=RESULTS, history=[], text=EMPTY, raise_for_status=lambda: None)]
                retry = MagicMock(return_value=SimpleNamespace(
                    status=retry_status, success=success, reason_code=reason, source_attempts=["fresh EIN evidence"]))
                with patch.object(cc.curl_requests, "Session", return_value=session), \
                     patch.object(cc, "trial_identity", return_value=True), \
                     patch.object(cc, "mi_http_names_enabled", return_value=True), \
                     patch.object(cc, "mi_name_http_empty_queries") as names:
                    result = cc.search_mi_http_completion_probe(
                        self.org, time.perf_counter() + 100, retry_empty_ein=retry)
                retry.assert_called_once_with()
                names.assert_not_called()
                self.assertIn("Initial Michigan EIN search returned zero records", result.source_attempts[0])
                self.assertEqual(result.source_attempts[1], "fresh EIN evidence")
                self.assertEqual(result.status.casefold(), retry_status.casefold())
                self.assertEqual(getattr(result, "_cc_mi_browser_ein_confirmed_empty", False),
                                 reason == "MI_BROWSER_EIN_NO_MATCH")

    def test_actual_michigan_branch_runs_name_search_only_after_confirmed_negative(self):
        tree = ast.parse(Path(cc.__file__).read_text(encoding="utf-8"))
        run = next(node for node in tree.body if getattr(node, "name", "") == "_run_state_lookup_source")
        branch = next(node for node in ast.walk(run) if isinstance(node, ast.If) and ast.unparse(node.test) == "state == 'MI'")
        code = compile(ast.Module(body=branch.body[:8], type_ignores=[]), cc.__file__, "exec")
        for status, reason in [("Current", "MATCH_EIN_EXACT"), ("Not Registered", "MI_BROWSER_EIN_NO_MATCH"),
                               ("Unable to Verify", "MI_NEGATIVE_CONFIRMATION_INCOMPLETE")]:
            page = SimpleNamespace(url=RESULTS)
            retry = SimpleNamespace(success=(status != "Unable to Verify"), status=status, error="",
                                    raw_status_text="No results found" if status == "Not Registered" else "",
                                    source_note="", source_attempts=["fresh EIN evidence"], reason_code=reason)
            name_result = SimpleNamespace(status="Not Registered", source_attempts=["name search evidence"])
            browser = MagicMock(side_effect=[retry, name_result])
            def probe(org, lookup_deadline, *, retry_empty_ein):
                result = retry_empty_ein()
                if result.reason_code == "MI_BROWSER_EIN_NO_MATCH":
                    result.reason_code = "NO_CANDIDATES_AFTER_COMPLETED_SEARCH"
                    result._cc_mi_completed_exact_ein_empty = (NAME, "631135091")
                    result._cc_mi_browser_ein_confirmed_empty = True
                return result
            env = dict(vars(cc), org=self.org, page=page, lookup_started=time.perf_counter(),
                       mi_progress={}, trial_identity=lambda: True, search_mi_http_completion_probe=probe,
                       search_mi_name_fallback=browser, MI_ENABLE_NAME_FALLBACK=True)
            exec(code, env)
            if status == "Not Registered":
                self.assertEqual(browser.call_count, 2)
                browser.assert_called_with(page, self.org)
                self.assertEqual(env["result"].source_attempts, ["fresh EIN evidence", "name search evidence"])
            else:
                browser.assert_called_once_with(page, self.org, confirm_ein=True)
                self.assertIs(env["result"], retry)
