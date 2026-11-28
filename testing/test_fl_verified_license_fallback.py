"""Replay the Florida timeout path with an owner-bound license proof."""
from concurrent.futures import Future
from datetime import date, timedelta
import io
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import registry_snapshot_server as cc
from deployment import fl_license_proof, fl_registry_migration, performance_lab, source_visual_adapters, staging_workflows
from deployment.state_snapshots import CaptureRun
from testing.test_fl_registry_migration import document


class FloridaVerifiedLicenseFallback(unittest.TestCase):
    ID = "CH38285"
    NAME = "Children's Hospital Medical Center"
    EIN = "31-0833936"
    OWNER = ["test@example.com", "test-device"]
    URL = cc.FL_CHECK_A_CHARITY_URL

    def setUp(self):
        self.master = SimpleNamespace(NY_CONNECTOR_SIGNING_KEY="fixture-key".ljust(48, "0"),
            complete_name_identity_key=cc.complete_name_identity_key)
        self.issued = int(time.time())
        self.future_date = (date.today() + timedelta(days=300)).strftime("%m/%d/%Y")

    def legacy(self, name, ein, identifier, **override):
        record = dict(mode="standard", owner=self.OWNER, name=name,
                      ein=cc.canonical_ein_digits(ein), issued=self.issued)
        result = dict(state="FL", ein=ein, success=True, status="Upcoming Filing",
                      matched_registry_name=name.upper(), matched_registry_identifier=identifier,
                      source_url=self.URL, reason_code="MATCH_NAME_EXACT",
                      evidence_url="/state-snapshots/" + "a" * 64 + ".pdf", evidence_captured_at=self.issued)
        return record, result | override

    def proof(self, name, ein, identifier):
        record, result = self.legacy(name, ein, identifier)
        issued = fl_license_proof.issue(self.master, record, result)
        self.assertIsNotNone(issued)
        return fl_license_proof.verify(self.master, issued["token"], self.OWNER, name, ein)

    def run_check(self, name, ein, proof, fresh=None, *, old_status="Site Not Reachable",
                  modern_pages=None, timeout=False, closed_budget=False, evidence=None):
        org = cc.checker.Organization(name, ein)
        old = cc.checker.StateResult(name, ein, "FL", old_status, self.URL, success=old_status != "Site Not Reachable")
        if old_status == "Site Not Reachable":
            old.reason_code = "FL_SOURCE_NOT_RESPONDING"
        elif old_status != "Not Registered":
            old.matched_registry_identifier = self.ID
        with CaptureRun(name, ein, "FL") as run, fl_license_proof.use(proof):
            change = fl_registry_migration.MigrationCheck(cc, run)
            change.names = (name,)
            change.deadline = time.monotonic() + (2 if closed_budget else 8)
            change.prior_pages = {}
            change.future = Future()
            pages = {name: ((), document(name))} if modern_pages is None else modern_pages
            change.future.set_result(pages)
            run.fl_query_progress = {"completed": {name: old}}
            with patch.object(fl_registry_migration, "fetch", return_value=fresh,
                              side_effect=TimeoutError if timeout else None) as fetch:
                actual = change.finish(old, org)
                if evidence is not None:
                    evidence(run, actual)
                return actual, run, fetch

    def test_proof_is_owner_name_ein_and_time_bound(self):
        record, row = self.legacy(self.NAME, self.EIN, self.ID)
        issued = fl_license_proof.issue(self.master, record, row)
        token = issued["token"]
        self.assertEqual(issued["id"], self.ID)
        self.assertEqual(fl_license_proof.verify(self.master, token, self.OWNER, self.NAME, self.EIN)["id"], self.ID)
        for candidate, owner, name, ein in (
            (token[:-1] + ("0" if token[-1] != "0" else "1"), self.OWNER, self.NAME, self.EIN),
            (token, [self.OWNER[0], "other-device"], self.NAME, self.EIN),
            (token, ["other@example.com", self.OWNER[1]], self.NAME, self.EIN),
            (token, self.OWNER, self.NAME + " Foundation", self.EIN),
            (token, self.OWNER, self.NAME, "12-3456789"),
        ):
            self.assertIsNone(fl_license_proof.verify(self.master, candidate, owner, name, ein))
        with patch.object(fl_license_proof.time, "time", return_value=issued["expires"]):
            self.assertIsNone(fl_license_proof.verify(self.master, token, self.OWNER, self.NAME, self.EIN))
        for disqualifier in (dict(confirmation_required=True), dict(source_url=fl_registry_migration.URL),
                             dict(evidence_url=""), dict(reason_code="MATCH_REVIEWED_ALTERNATE_NAME"),
                             dict(matched_registry_name=self.NAME + " Foundation"),
                             dict(status="Review Required"), dict(evidence_captured_at=self.issued - 60)):
            self.assertIsNone(fl_license_proof.issue(self.master, record, row | disqualifier))

    def test_fresh_card_accepts_a_current_status_change(self):
        verified = self.proof(self.NAME, self.EIN, self.ID)
        cards = [(self.ID, self.ID, "Suspended", "", "N/A", "")]
        result, run, fetch = self.run_check(self.NAME, self.EIN, verified, document(self.ID, cards))
        self.assertEqual((result.status, result.matched_registry_identifier, result.matched_registry_name),
                         ("Suspended", self.ID, self.NAME.upper()))
        self.assertEqual(result.source_url, fl_registry_migration.query_url(self.ID))
        self.assertIn("recent Florida check", result.source_note)
        self.assertEqual(run.fl_modern_selected[-1], cards[0])
        self.assertEqual(run.search_history_receipts[-1]["query"]["name"], self.ID)
        fetch.assert_called_once()
        self.assertIsNone(fl_license_proof.PROOF.get())

    def test_prefix_neighbors_do_not_replace_the_exact_verified_license(self):
        verified = self.proof(self.NAME, self.EIN, self.ID)
        exact = (self.ID, self.ID, "Registered", self.future_date, "N/A", "")
        neighbor = (self.ID + "7", self.ID + "7", "Expired", "01/31/2020", "N/A", "")
        for cards in ([exact, neighbor], [neighbor, exact]):
            result, run, _ = self.run_check(self.NAME, self.EIN, verified, document(self.ID, cards))
            self.assertEqual(result.matched_registry_identifier, self.ID)
            self.assertEqual(run.fl_modern_selected[-1], exact)
        for cards in ([neighbor], [exact, exact], [neighbor, (*exact[:-1], "88-7654321")]):
            result, _, _ = self.run_check(self.NAME, self.EIN, verified, document(self.ID, cards))
            self.assertEqual(result.status, "Site Not Reachable")

    def test_conflicts_empty_results_and_network_failures_remain_inconclusive(self):
        verified = self.proof(self.NAME, self.EIN, self.ID)
        base = (self.ID, self.ID, "Registered", self.future_date, "N/A", "")
        for card_list in ([], [base, ("CH10", "Other Charity", "Registered", self.future_date, "N/A", "")],
                          [("CH10", "CH10", "Registered", self.future_date, "N/A", "")],
                          [(self.ID, "Other Charity", "Registered", self.future_date, "N/A", "")],
                          [(self.ID, self.ID, "Registered", self.future_date, "N/A", "88-7654321")],
                          [(self.ID, self.ID, "Registered", "", "N/A", "")]):
            result, run, fetch = self.run_check(self.NAME, self.EIN, verified, document(self.ID, card_list))
            self.assertEqual(result.status, "Site Not Reachable")
            self.assertIsNone(getattr(run,"fl_modern_selected",None))
            fetch.assert_called_once()
        for options in ({"timeout": True}, {"closed_budget": True},
                        {"modern_pages": {self.NAME: ((base,), document(self.NAME, [base]))}}):
            result, _, fetch = self.run_check(self.NAME, self.EIN, verified, document(self.ID, [base]), **options)
            self.assertIn(result.status, {"Site Not Reachable", "Unable to Confirm"})
            self.assertEqual(fetch.call_count, 1 if options.get("timeout") else 0)

    def test_actual_portal_pages_can_supply_exact_original_evidence(self):
        directory = os.environ.get("CC_FL_EXACT_PORTAL_FIXTURES")
        if not directory:
            self.skipTest("Provide both saved, direct exact-license FDACS responses.")
        for identifier, name, ein in (
                (self.ID, self.NAME, self.EIN), ("CH29365", "Chronic Disease Fund, Inc.", "61-1462062")):
            original = (Path(directory)/(identifier+"-modern.html")).read_text(encoding="utf-8")
            verified = self.proof(name, ein, identifier)
            def capture(run, result):
                page = MagicMock()
                url = fl_registry_migration.query_url(identifier)
                page.url = url
                page.content.return_value = original
                card = page.locator.return_value
                card.count.return_value = 1
                card.inner_text.return_value = "Registry result " + identifier
                card.screenshot.return_value = b"original fixture pixels"

                def navigate(link, **kwargs):
                    request = SimpleNamespace(url=link, method="GET", resource_type="document")
                    route = MagicMock(request=request)
                    page.route.call_args.args[1](route)
                    route.fulfill.assert_called_once_with(status=200, content_type="text/html; charset=utf-8", body=original)
                    return SimpleNamespace(status=200)

                page.goto.side_effect = navigate
                data = dict(source_url=result.source_url, matched_registry_name=result.matched_registry_name,
                            matched_registry_identifier=result.matched_registry_identifier)
                with patch.object(run, "document") as archive:
                    fl_registry_migration.capture(run, data | {"matched_registry_name": "Other Charity"}, page, time.monotonic()+7)
                    archive.assert_not_called()
                    fl_registry_migration.capture(run, data, page, time.monotonic()+7)
                    archive.assert_called_once()
                    self.assertEqual(archive.call_args.args[:3], (url, b"original fixture pixels", "image"))
            with self.subTest(identifier=identifier):
                result, _, _ = self.run_check(name, ein, verified, original, evidence=capture)
                self.assertTrue(result.success)
                self.assertEqual(result.matched_registry_identifier, identifier)

    def test_actual_card_pixels_are_archived_without_a_fabricated_name(self):
        from playwright.sync_api import sync_playwright
        path = os.environ.get("CC_FL_EXACT_PORTAL_FIXTURES")
        if not path:
            self.skipTest("Provide the saved, direct exact-license FDACS responses.")
        directory = Path(path)
        with sync_playwright() as playwright, playwright.chromium.launch(headless=True) as browser:
            context = browser.new_context()
            context.route("**/*", lambda route: route.abort())
            failed_page = MagicMock()
            failed_page.goto.side_effect = RuntimeError("The pending Chromium error page interrupted navigation")
            for identifier, name, ein in ((self.ID, self.NAME, self.EIN),
                                          ("CH29365", "Chronic Disease Fund, Inc.", "61-1462062")):
                original = (directory/(identifier+"-modern.html")).read_text(encoding="utf-8")
                verified = self.proof(name, ein, identifier)
                def capture(run, result):
                    data = {key: getattr(result, key) for key in (
                        "source_url", "matched_registry_name", "matched_registry_identifier",
                        "status_reason", "raw_status_text", "state", "ein", "status", "success")}
                    source_visual_adapters.capture_owned_fl_page(cc, run, data, failed_page, context, time.monotonic()+9)
                    failed_page.goto.assert_not_called()
                    self.assertEqual(context.pages, [])
                    self.assertEqual(len(run.documents), 1)
                    url, pixels, kind, text, _, note = run.documents[0]
                    self.assertIn(identifier, text)
                    self.assertNotIn(name.casefold(), text.casefold())
                    self.assertEqual(note, fl_registry_migration.LICENSE_EVIDENCE_NOTE)
                    self.assertTrue(pixels.startswith(bytes([255,216,255])))
                    for conflict in ({"ein": "00-0000000"}, {"matched_registry_identifier":"CH10"},
                                     {"raw_status_text":"other"}, {"matched_registry_name":"Other Charity"}):
                        self.assertFalse(fl_registry_migration.verified_license_image_bound(run, data | conflict, url, pixels, kind))
                    self.assertFalse(fl_registry_migration.verified_license_image_bound(run, data, url, pixels+b"x", kind))
                    archived = run.finish(data)
                    self.assertEqual(archived["evidence_capture"], "captured")
                    self.assertEqual(archived["_worker_source_archives"][0]["identifier"], identifier)
                    (directory/(identifier+"-candidate-evidence.jpg")).write_bytes(pixels)
                with self.subTest(identifier=identifier):
                    result, _, _ = self.run_check(name, ein, verified, original, evidence=capture)
                    self.assertTrue(result.success)
                    self.assertEqual(result.matched_registry_identifier, identifier)

    def test_at_least_100_distinct_recorded_organizations(self):
        path = os.environ.get("CC_FL_MIGRATION_ROSTER")
        if not path:
            self.skipTest("Provide the saved organization roster.")
        roster = Path(path)
        entries = json.loads(roster.read_text(encoding="utf-8-sig"))
        self.assertGreaterEqual(len({cc.canonical_ein_digits(row["ein"]) for row in entries}), 100)
        for idx, row in enumerate(entries, 1):
            name, ein, identifier = row["name"], row["ein"], f"CH{10000 + idx}"
            with self.subTest(ein=ein):
                verified = self.proof(name, ein, identifier)
                self.assertEqual(verified["id"], identifier)
                fresh = document(identifier, [(identifier, identifier, "Registered", self.future_date, "N/A", "")])
                recovered, _, fetch = self.run_check(name, ein, verified, fresh)
                self.assertEqual(recovered.status, "Current")
                self.assertEqual(recovered.matched_registry_identifier, identifier)
                fetch.assert_called_once()
                for status, proof in (("Current", verified), ("Not Registered", verified), ("Site Not Reachable", None)):
                    control, _, fetch = self.run_check(name, ein, proof, fresh, old_status=status)
                    self.assertEqual(control.status, status)
                    fetch.assert_not_called()

    def test_token_moves_only_through_allowed_staging_workflow(self):
        class Handler:
            def __init__(self, payload):
                body = json.dumps(payload).encode()
                self.headers = {"Content-Length": str(len(body))}
                self.rfile = io.BytesIO(body)

            def _send_json(self, status, data, *args):
                self.response = status, data

        record, row = self.legacy(self.NAME, self.EIN, self.ID)
        stub = MagicMock(wraps=cc)
        stub.NY_CONNECTOR_SIGNING_KEY = self.master.NY_CONNECTOR_SIGNING_KEY
        stub.SUPPORTED_STATES = cc.SUPPORTED_STATES
        stub.IDENTITY_STATES = cc.IDENTITY_STATES
        stub.APP_VERSION = cc.APP_VERSION
        stub.normalize_email.side_effect = lambda x: x
        stub.normalize_device_id.side_effect = lambda x: x
        stub.staging_access_error.return_value = None
        stub.is_verified_internal_passcode.return_value = True
        queue = MagicMock()
        queue.submit.return_value = "12345678-1234-1234-1234-123456789012", True
        creds = dict(email=self.OWNER[0], device_id=self.OWNER[1], admin_passcode="test")
        data = dict(action="start", consent=True, request_id=queue.submit.return_value[0],
                    organization_name=self.NAME, ein=self.EIN, states=["FL"], **creds)
        with patch("deployment.lab_identity.trial_identity", return_value={"permanent_staging": True}), patch.dict(
                os.environ, {"CE_STAGING_WORKFLOW_VERSION": cc.APP_VERSION}):
            handler = Handler(data)
            staging_workflows.handle(stub, handler, trial_queue=queue)
            self.assertEqual(handler.response[0], 200)
            workflow = handler.response[1]["token"]
            queue.status.return_value = dict(phase="completed", completed=1, total=1, submitted=self.issued,
                deadline=self.issued+900, started=self.issued, finished=self.issued, ein=record["ein"],
                source_version=cc.APP_VERSION, jobs=[dict(state="FL", phase="done", result=row | {"app_version":cc.APP_VERSION})])
            handler = Handler(dict(action="poll", token=workflow, **creds))
            staging_workflows.handle(stub, handler, trial_queue=queue)
            self.assertEqual(handler.response[0], 200)
            proof = handler.response[1]["fl_license_proof"]["token"]
            self.assertNotIn("fl_license_proof", handler.response[1]["results"][0])
            for token, valid in ((proof, True), ("tampered", False)):
                request = Handler(data | {"fl_license_token": token})
                staging_workflows.handle(stub, request, trial_queue=queue)
                self.assertEqual(request.response[0], 200)
                self.assertEqual("_fl_verified_license" in queue.submit.call_args.args[2], valid)

    def test_only_permanent_staging_asset_uses_proof(self):
        root = Path(__file__).resolve().parents[1]
        text = (root/"web-staging/optimized-workflows.js").read_text(encoding="utf-8")
        identity = {"origin":"https://private-staging.example.com"}
        for data, included in ((None, False), (identity, False), (identity | {"permanent_staging":True}, True)):
            with patch.object(performance_lab,"trial_identity",return_value=data):
                asset = performance_lab.final_four_asset("optimized-workflows.js",text)
                self.assertEqual("fl_license_token" in asset, included)
                if included:
                    self.assertIn(r"replace(/\D/g,'')",asset)


if __name__ == "__main__":
    unittest.main()
