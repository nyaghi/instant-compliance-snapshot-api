"""Replay the open Arkansas and Florida cases without contacting registries."""
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

import registry_snapshot_server as cc
from deployment import fl_response_evidence, search_history, search_observation, source_visual_adapters, state_snapshots
from testing.capacity_lab.test_fl_business_lookup import card, source
from testing import run_ar_completion_guardrails


class OpenIssueRepairs(TestCase):
    def test_arkansas_exact_source_rows_are_held_for_confirmation(self):
        cases = [
            ("NATIONAL COUNCIL OF YOUNG MEN'S CHRISTIAN ASSOCIATIONS OF THE USA",
             "NATIONAL COUNCIL OF YOUNG",
             "National Council of Young Men's Christian Associat"),
            ("NEW YORK SOCIETY FOR THE RELIEF OF THE RUPTURED AND CRIPPLED, MAINTAINING THE HOSPITAL FOR SPECIAL SURGERY",
             "NEW YORK SOCIETY FOR THE RELIEF OF THE",
             "New York Society for the Relief of the Ruptured &"),
        ]
        fixture = run_ar_completion_guardrails.ArkansasCompletionTests()
        fixture.setUp()
        try:
            for name, prefix, label in cases:
                row = {"name": label, "type": "Charity", "status": "Current", "registration_date": "2014-08-14"}
                with self.subTest(name=name):
                    with patch.object(cc, "ar_reviewed_search_plan", return_value=([prefix, name], {})):
                        result, queries = fixture.lookup(
                            {prefix: {"body": "Back to Search Form Registration Date", "rows": [row]}},
                            name=name, aliases=[name],
                        )
                    self.assertEqual(queries, [prefix])
                    self.assertFalse(result.success)
                    self.assertEqual(result.status_reason, "AR_NAME_LENGTH_IDENTITY_REVIEW")
                    self.assertEqual(result._cc_identity_review["records"][0]["name"], label)
                    self.assertEqual(result._cc_identity_review["records"][0]["status"], "Current")
                    self.assertFalse(result._cc_identity_review["search_complete"])
                    self.assertFalse(cc.ar_truncated_legal_name(label[:-2], name))
                    self.assertFalse(cc.ar_truncated_legal_name("Not " + label[4:], name))
                    for foreign_ein in ("136714749", "993258696"):
                        self.assertEqual(cc.ar_candidate_identity(
                            dict(row, ein=foreign_ein), name, [name], "123456789"), "reject")
        finally:
            fixture.tearDown()

    def run_florida(self, name, legacy, *, bound=True, primary_rows=None, lookup_error=False, repeats=1):
        org = cc.checker.Organization(name, "311746269")
        page = MagicMock()
        page.url = cc.FL_CHECK_A_CHARITY_URL
        page.expect_navigation.return_value.__enter__.return_value.value = SimpleNamespace(status=200)
        page.input_value.return_value = name if bound else "DIFFERENT QUERY"
        page.evaluate.return_value = primary_rows
        body = "No matching records found" if primary_rows is None else "Charitable organization results"
        page.locator.return_value.inner_text.return_value = body
        def submit(**kwargs):
            if lookup_error:
                raise TimeoutError("state did not respond")
            observed = search_observation.start_transport(
                cc.FL_CHECK_A_CHARITY_URL, urlencode({"ctl00$cpMainContent$BusinessNameTb": name}),
            )
            search_observation.received(observed, 200)
        page.get_by_role.return_value.click.side_effect = submit
        def public(query, stop):
            fl_response_evidence.remember_response(cc, legacy, query)
            return cc.fl_business_candidate_rows(legacy)

        with (
            state_snapshots.CaptureRun(name, org.ein, "FL") as capture,
            patch.object(cc, "trial_identity", return_value=True),
            patch.object(cc, "fl_business_lookup_enabled", return_value=False),
            patch.object(cc, "reviewed_queries_first", return_value=[name]),
            patch.object(cc.checker, "find_visible_input", return_value=page),
            patch.object(cc, "readable_page_text", return_value=body),
            patch.object(cc, "fl_reviewed_alias_address", return_value=None),
            patch.object(cc, "_fl_business_public_rows_once", side_effect=public) as alternate,
            patch.object(cc.time, "sleep"),
        ):
            capture.semantic_history_scope = True
            for _ in range(repeats):
                result = cc.search_fl(page, org)
            out = {
                "state": "FL", "ein": org.ein, "status": cc.public_status(result), "success": result.success,
            }
            if out["status"] == "Not Registered" and bound and not lookup_error:
                proof_page = MagicMock()
                source_visual_adapters.capture_owned_fl_empty(cc, capture, out, proof_page, time.monotonic() + 10)
                proof_page.goto.assert_not_called()
            data = search_history.finish_worker_history(capture, out)
            return result, data, alternate.call_count

    def test_florida_history_survives_without_screenshot(self):
        name = "Music For Life Institute"
        legacy = source(card(name=name, identifier="CH17269", status="Not Operating in FL", expiry="04/16/25"))
        result, data, calls = self.run_florida(name, legacy, repeats=2)
        self.assertEqual(cc.public_status(result), "Not Registered")
        self.assertEqual(result.source_note.count('CH17269'), 1)
        self.assertIn('Not Operating in FL', result.source_note)
        self.assertEqual(calls, 1)
        history = data["_worker_search_history"]
        self.assertEqual(history["search_failed_receipts"], [])
        receipt = history["completed"][0]
        self.assertEqual(receipt["query"]["name"], name)
        self.assertEqual(receipt["search_receipt"]["returned_rows"], 0)

    def test_florida_nonmatching_rows_are_not_an_empty_grid(self):
        name = "New York University"
        rows = [{"text": "Business Name Other University License/Registration Number CH90909 Status Registered"}]
        result, data, _ = self.run_florida(name, source(count=0, body=""), primary_rows=rows)
        self.assertEqual(cc.public_status(result), "Not Registered")
        receipt = data["_worker_search_history"]["completed"][0]
        self.assertEqual(receipt["query"]["name"], name)
        self.assertIsNone(receipt["search_receipt"]["returned_rows"])

    def test_florida_stale_query_and_failed_submission_create_no_completed_receipt(self):
        name = "Music For Life Institute"
        for options in ({"bound": False}, {"lookup_error": True}):
            with self.subTest(options=options):
                result, data, _ = self.run_florida(name, source(count=0, body=""), **options)
                receipts = data.get("_worker_search_history", {}).get("completed", [])
                self.assertTrue(all(r["search_receipt"]["observation_kind"] == "transport_response"
                                    for r in receipts))
                if options.get("lookup_error"):
                    self.assertFalse(result.success)

    def test_florida_current_credential_has_priority(self):
        name = "Music For Life Institute"
        primary = [{"text": f"Business Name {name} License/Registration Number CH98765 Expiration Date 12/31/2028 Status Registered"}]
        legacy = source(card(name=name, identifier="CH17269", status="Not Operating in FL", expiry="04/16/25"))
        result, _, calls = self.run_florida(name, legacy, primary_rows=primary)
        self.assertEqual(result.status, "Current")
        self.assertEqual(result.matched_registry_identifier, "CH98765")
        self.assertEqual(calls, 0)

    def test_tennessee_new_reasons_keep_incomplete_search_history(self):
        for reason, note in search_history.TN_INCOMPLETE_NOTES.items():
            with self.subTest(reason=reason):
                result = cc.final_four_connector_failure({
                    "organization_name": "Northeastern University", "ein": "041679980", "state": "TN",
                    "issued": time.time(),
                    "completed": [{"query": {"name": "NORTHEASTERN UNIVERSITY"}}],
                    "pending": {"query": {"name": "NU", "operation": "search"}},
                }, reason)
                self.assertFalse(result["success"])
                self.assertIn(note, result["source_note"])
                self.assertTrue(search_history.needs_search_history(result))


    def test_replay_arkansas_and_florida_for_recorded_organizations(self):
        roster_path = os.environ.get("CC_GATE_REPAIR_ROSTER")
        if not roster_path:
            self.skipTest("Provide the archived 70-organization roster for release validation.")
        roster = json.loads(Path(roster_path).read_text(encoding="utf-8"))
        self.assertEqual(len({row["ein"] for row in roster}), 70)
        fixture = run_ar_completion_guardrails.ArkansasCompletionTests()
        fixture.setUp()
        try:
            for row in roster:
                with self.subTest(name=row["name"], ein=row["ein"]):
                    name = cc.canonical_name_punctuation(row["name"])
                    result, queries = fixture.lookup(name=name, aliases=[])
                    self.assertTrue(queries)
                    self.assertEqual(cc.public_status(result), "Not Registered")
                    related = "Unrelated " + name
                    self.assertFalse(cc.ar_truncated_legal_name(related[:50], name))
                    result, data, calls = self.run_florida(name, source(count=0, body=""))
                    self.assertEqual(cc.public_status(result), "Not Registered")
                    self.assertEqual(calls, 1)
                    receipts = data["_worker_search_history"]["completed"]
                    self.assertEqual(len(receipts), 1)
                    self.assertEqual(receipts[0]["query"]["name"], name)
                    self.assertEqual(receipts[0]["search_receipt"]["returned_rows"], 0)
        finally:
            fixture.tearDown()
