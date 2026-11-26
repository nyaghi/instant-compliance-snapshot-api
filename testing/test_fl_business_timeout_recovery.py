import html
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import registry_snapshot_server as cc
from deployment.fl_initial_recovery import completed_empty_business_query
from deployment.fl_response_evidence import remember_response, capture_bound
from deployment.state_snapshots import CaptureRun

LEGAL_ORIGINAL = "Christian Healthcare Ministries, Inc."
LEGAL_REGISTERED = "Christian Healthcare Ministries"


class FloridaBusinessTimeoutRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = os.environ.get("CC_FL_PAGE_FIXTURES")
        roster = os.environ.get("CC_FL_MIGRATION_ROSTER")
        if not directory or not roster:
            raise unittest.SkipTest("Provide the saved FDACS responses and local organization roster.")
        root = Path(directory)
        cls.empty = (root / "business-inc.html").read_text(encoding="utf-8")
        cls.positive = (root / "business-registered-name.html").read_text(encoding="utf-8")
        cls.cases = json.loads(Path(roster).read_text(encoding="utf-8"))

    def exercise(self, name, ein, *, initial=None, alternate=None, fault=True, explicit_row=None):
        page = MagicMock()
        page.url = cc.FL_CHECK_A_CHARITY_URL
        transport = cc.FloridaVerifiedTransport(page)
        calls = []

        def goto(url, **kwargs):
            if url == cc.FL_CHECK_A_CHARITY_URL and fault:
                if transport.enabled:
                    transport.error = TimeoutError("Verified registry response timed out")
                raise TimeoutError("Registry response timed out")
            return SimpleNamespace(status=200)

        def business(query, deadline):
            calls.append(query)
            source = initial if len(calls) == 1 else alternate
            if source is None:
                raise cc.FloridaEntryTimeout("Business Lookup response unavailable")
            remember_response(cc, source, query)
            return [explicit_row] if len(calls) > 1 and explicit_row else cc.fl_business_candidate_rows(source)

        page.goto.side_effect = goto
        row = {"index": 0, "text": f"{name} License/Registration Number CH3543 "
                                  f"Expiration Date 1/31/2027 Status Current EIN {ein}"}
        page.evaluate.return_value = [row]
        page.expect_navigation.return_value.__enter__.return_value.value = SimpleNamespace(status=200)
        org = SimpleNamespace(organization_name=name, ein=ein)
        with CaptureRun(name, ein, "FL") as run:
            run.semantic_history_scope = True
            with patch.object(cc, "trial_identity", return_value={"permanent_staging": True}), \
                    patch.object(cc, "fl_business_lookup_enabled", return_value=True), \
                    patch.object(cc, "_fl_business_public_rows_once", side_effect=business), \
                    patch.object(cc, "CAPTURE_EVIDENCE_SCREENSHOTS", False), \
                    patch.object(cc, "CAPTURE_LIGHTWEIGHT_SOURCE_SNAPSHOT", False), \
                    patch.object(cc.time, "sleep"), patch.object(cc.checker, "find_visible_input", return_value=page), \
                    patch.object(cc, "readable_page_text", return_value=row["text"]), \
                    patch.object(cc, "registry_candidate_fields", return_value={"status": "Current"}):
                result = cc.search_fl_with_transport(page, org, transport, migration=MagicMock())
            evidence = capture_bound(run, {
                "state": "FL", "ein": ein, "success": result.success, "status": cc.public_status(result),
                "source_url": result.source_url, "matched_registry_name": result.matched_registry_name,
                "matched_registry_identifier": result.matched_registry_identifier,
            })
            return result, calls, evidence, page.route.call_count

    def test_real_fdacs_empty_then_exact_license_and_original_evidence(self):
        result, calls, evidence, second_transport = self.exercise(
            LEGAL_ORIGINAL, "34-1964742", initial=self.empty, alternate=self.positive)
        self.assertEqual(calls, [LEGAL_ORIGINAL, LEGAL_REGISTERED])
        self.assertEqual(result.matched_registry_identifier, "CH3543")
        self.assertEqual(result.status, cc.classify_expiration_date(cc.date(2027, 1, 31)))
        self.assertEqual(evidence["html"], self.positive)
        self.assertEqual(second_transport, 0)

    def test_132_offline_organization_controls_keep_healthy_path_and_unsafe_results(self):
        self.assertGreaterEqual(len({item["ein"] for item in self.cases}), 100)
        for item in self.cases:
            name = cc.literal_name_retrieval_forms(item["name"])[0] + ", Inc."
            literal = cc.literal_name_retrieval_forms(name)[0]
            ein = item["ein"]
            empty = self.empty.replace(LEGAL_ORIGINAL, html.escape(name))
            positive = self.positive.replace(LEGAL_REGISTERED.upper(), html.escape(literal.upper())).replace(
                LEGAL_REGISTERED, html.escape(literal))
            with self.subTest(ein=ein):
                healthy, calls, _, wire = self.exercise(name, ein, initial=empty, fault=False)
                self.assertEqual(calls, [name])
                self.assertTrue(healthy.success)
                self.assertEqual(wire, 0)
                failure, calls, _, wire = self.exercise(name, ein)
                self.assertEqual(failure.reason_code, "FL_SOURCE_NOT_RESPONDING")
                self.assertEqual(calls, [name])
                self.assertEqual(wire, 1)
                different_org = positive.replace(html.escape(literal.upper()), html.escape(literal.upper()+" FOUNDATION"))
                failed, calls, evidence, wire = self.exercise(name, ein, initial=empty, alternate=different_org)
                self.assertEqual(failed.reason_code, "FL_SOURCE_NOT_RESPONDING")
                self.assertEqual(calls, [name, literal])
                self.assertIsNone(evidence)
                self.assertEqual(wire, 1)

    def test_response_must_belong_to_current_submitted_business_query(self):
        case = SimpleNamespace(run_id="a",fl_response_candidate={"run_id":"a","query":LEGAL_ORIGINAL,"html":self.empty})
        self.assertTrue(completed_empty_business_query(case, LEGAL_ORIGINAL))
        case.fl_response_candidate["html"] = self.positive
        self.assertFalse(completed_empty_business_query(case, LEGAL_ORIGINAL))
        case.fl_response_candidate["html"] = self.empty
        case.fl_response_candidate["run_id"] = "b"
        self.assertFalse(completed_empty_business_query(case, LEGAL_ORIGINAL))
