"""Verify the two documented California identity bindings and their guards."""
import json
import os
from pathlib import Path
import time
from unittest import TestCase
from unittest.mock import patch

import registry_snapshot_server as cc
from deployment import ca_documented_identity as proof, source_visual_adapters, state_snapshots

PEPPER = {
    "id": "5000736", "entityType": "Business", "entityName": "PEPPERDINE UNIVERSITY",
    "entityStatus": "Exempt", "fein": "94-1644037", "sosId": "0171635",
    "officialAddress": {"line1": "24255 PACIFIC COAST HIGHWAY", "city": "MALIBU", "state": "CA", "zipCode": "90263"},
}
FOUNDATION = {
    "id": "6575026", "entityType": "Business", "entityName": "SAINT FRANCIS FOUNDATION INC.",
    "entityStatus": "Withdrawn", "fein": "48-1059281",
    "officialAddress": {"line1": "405 E. IRON AVE.", "city": "SALINA", "state": "KS", "zipCode": "67401"},
}
CLOSED = {
    "id": "1616276", "entityRelated": {"id": "6575026", "name": "SAINT FRANCIS FOUNDATION INC. - 6575026"},
    "registrationType": "Charitable Organization", "registrationStatus": "Not Registered",
    "registrationNumber": "CT0261177", "currentExpirationDate": "2023-11-15",
    "initialRegistrationDate": "2018-11-20",
}


class ReviewedCaliforniaIdentityTests(TestCase):
    def replay(self, entity, ein, registrations, extra=None):
        name = entity["entityName"]
        org = cc.checker.Organization(name, ein)
        negative = cc.checker.StateResult(name, ein, "CA", cc.checker.STATUS_NOT_REGISTERED,
                                         cc.checker.CA_EVOKE_PUBLIC_PORTAL_URL, success=True)
        with (
            patch.object(cc, "trial_identity", return_value=True),
            patch.object(cc.checker, "search_ca", return_value=negative),
            patch.object(cc.checker, "ca_evoke_entity_search_by_name", return_value=[entity, *(extra or [])]),
            patch.object(cc.checker, "ca_evoke_api_get", return_value=registrations) as fetch,
        ):
            result = cc.search_ca_master(None, org)
            return result, fetch.call_count

    def test_pepperdine_keeps_original_visible_state_ein_in_snapshot(self):
        result, calls = self.replay(PEPPER, "95-1644037", [])
        self.assertEqual(calls, 1)
        self.assertEqual(cc.true_status_from_body(result, ""), "Exempt")
        self.assertEqual(result.matched_registry_identifier, "5000736")
        self.assertIn("94-1644037", result.source_note)
        with state_snapshots.CaptureRun(result.organization_name, result.ein, "CA") as run:
            source_visual_adapters.remember_ca_selected(run, result)
            hint = run.source_detail_hints["5000736"]
            self.assertEqual((hint["exempt_entity_ein"],hint["exempt_source_ein"]), ("951644037","941644037"))

    def test_foundation_uses_its_filed_number_instead_of_a_san_francisco_homonym(self):
        other = dict(FOUNDATION, id="5025990", fein="94-2597514")
        result, calls = self.replay(FOUNDATION, "81-5469765", [CLOSED], extra=[other])
        self.assertEqual(calls, 1)
        self.assertEqual(cc.true_status_from_body(result, ""), "Closed / Withdrawn / Canceled")
        self.assertEqual(result.matched_registry_identifier, "CT0261177")
        self.assertIn("Not Registered", result.source_note)
        with state_snapshots.CaptureRun(result.organization_name, result.ein, "CA") as run:
            source_visual_adapters.remember_ca_selected(run, result)
            self.assertTrue(run.source_detail_hints["CT0261177"]["url"].endswith("/1616276"))

    def test_independent_ids_name_and_location_must_all_match(self):
        for entity, ein, changes in (
            (PEPPER, "95-1644037", {"sosId": "123"}),
            (PEPPER, "95-1644037", {"id": "5000737"}),
            (PEPPER, "95-1644037", {"fein": "94-1644038"}),
            (FOUNDATION, "81-5469765", {"id": "5025990", "fein": "94-2597514"}),
            (FOUNDATION, "81-5469765", {"officialAddress": dict(FOUNDATION["officialAddress"], zipCode="67402")}),
        ):
            with self.subTest(changes=changes):
                result, calls = self.replay(dict(entity, **changes), ein, [])
                self.assertEqual(calls, 0)
                self.assertEqual(result.status_reason, "CA_REGISTRY_EIN_CONFLICT")

    def test_live_registration_conflict_does_not_publish_reviewed_standing(self):
        for records in ([dict(CLOSED, id="1616277")], [dict(CLOSED, registrationStatus="Registered")],
                        [CLOSED, dict(CLOSED, registrationNumber="CT1234567")], None):
            result, calls = self.replay(FOUNDATION, "81-5469765", records)
            self.assertEqual(calls, 1)
            self.assertEqual(result.status_reason, "CA_REGISTRY_EIN_CONFLICT")
            self.assertFalse(result.success)

    def test_seventy_distinct_organization_controls(self):
        path = os.environ.get("CC_GATE_REPAIR_ROSTER")
        if not path:
            self.skipTest("Provide the archived 70-organization roster for release validation.")
        roster = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual(len({o["ein"] for o in roster}),70)
        for i, org in enumerate(roster):
            with self.subTest(ein=org["ein"]):
                ein, name = org["ein"], org["name"]
                template = PEPPER if i % 2 else FOUNDATION
                entity = dict(template, id=f"88000{i}", entityName=name, fein="99-1234567")
                result, calls = self.replay(entity, ein, [])
                self.assertEqual(calls, 0)
                self.assertEqual(result.status_reason, "CA_REGISTRY_EIN_CONFLICT")
                self.assertEqual(cc.ca_master_name_identity(
                    cc.checker.Organization(name, ein), dict(entity, fein=ein)), "accepted")

