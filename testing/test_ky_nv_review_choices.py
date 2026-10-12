"""Focused Kentucky spelling and Nevada duplicate-identity review controls."""
import sys
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc


class KentuckyReviewChoices(unittest.TestCase):
    name = "Service Year Exchange, Inc. — Service Year Alliance"
    ein = "47-4970343"
    row = ("18871", "Service Year Exchanges, Inc.", "", "")

    def test_real_input_offers_single_letter_row_without_auto_match(self):
        with patch.object(cc, "load_ky_snapshot_records", return_value=[self.row]):
            result = cc.search_snapshot_or_embedded_state(cc.checker.Organization(self.name, self.ein), "KY")
        self.assertEqual(cc.public_status(result), "Needs Review")
        self.assertEqual(result._cc_identity_review["records"][0]["identifier"], "18871")
        self.assertFalse(getattr(result, "matched_registry_identifier", ""))

    def test_unrelated_or_two_letter_name_is_not_reviewable(self):
        for registry_name in ("Service Years Exchanges, Inc.", "Service Year Exchangzz, Inc.",
                              "Other Year Exchanges, Inc."):
            with self.subTest(registry_name=registry_name), patch.object(
                    cc, "load_ky_snapshot_records", return_value=[("18871", registry_name, "", "")]):
                result = cc.search_snapshot_or_embedded_state(cc.checker.Organization(self.name, self.ein), "KY")
            self.assertEqual(cc.public_status(result), "Not Registered")
            self.assertFalse(getattr(result, "_cc_identity_review", None))

    def test_exact_row_retains_existing_match(self):
        with patch.object(cc, "load_ky_snapshot_records", return_value=[self.row]):
            result = cc.search_snapshot_or_embedded_state(
                cc.checker.Organization("Service Year Exchanges, Inc.", self.ein), "KY")
        self.assertEqual(result.matched_registry_identifier, "18871")
        self.assertFalse(getattr(result, "_cc_identity_review", None))

    def test_accept_and_reject_use_signed_snapshot_and_existing_status_rules(self):
        with patch.object(cc, "load_ky_snapshot_records", return_value=[self.row]), patch.object(
                cc, "NY_CONNECTOR_SIGNING_KEY", "x" * 48), patch.object(cc, "APP_VERSION", "test-staging"):
            first = cc.run_state_lookup(self.name, self.ein, "KY")
            choice = first["identity_review"]["candidates"][0]
            self.assertEqual(first["status"], "Needs Review")
            for action, expected in (("accept", "Current"), ("reject", "Not Registered")):
                answer = cc.resolve_identity_review({"token": first["identity_review"]["token"],
                    "ein": first["ein"], "state": "KY", "action": action,
                    "candidate_id": choice["id"]}, "review@example.org", "test-device")
                self.assertEqual(answer["status"], expected)
                self.assertEqual(answer.get("matched_registry_identifier") or "", "18871" if action == "accept" else "")


class NevadaReviewChoices(unittest.TestCase):
    def test_duplicate_registrations_offer_exclusive_choice(self):
        org = cc.checker.Organization("Sexually Abused Children's Relief Endeavor — SACRED", "27-0567085")
        rows = [{"name": name, "identifier": str(index), "status": "Current", "ein": "",
                 "raw_status": "Registered", "expiration": date(2027, 6, 1), "initial": "",
                 "url": "https://esos.nv.gov/EntitySearch/OnlineEntitySearch", "location": ""}
                for index, name in enumerate(("SACRED", "Sexually Abused Children's Relief Endeavor"), 1)]
        def accepted(_org, row, _state, _deadline):
            row["match"] = {"decision": "accepted"}
            row["address_evidence"] = {"decision": "unavailable"}
            return "accepted"
        with patch.object(cc, "licensed_charity_identity", side_effect=accepted), patch.object(
                cc, "NY_CONNECTOR_SIGNING_KEY", "x" * 48), patch.object(cc, "APP_VERSION", "test-staging"):
            result = cc.licensed_charity_result(org, "NV", rows, time.monotonic() + 5, "https://esos.nv.gov/")
            self.assertEqual(result.status, "Needs Review")
            self.assertTrue(result._cc_identity_review["exclusive"])
            data = {"ein": org.ein, "state": "NV", "organization_name": org.organization_name,
                    "comments": result.source_note, "status": result.status}
            cc.attach_identity_review(data, result._cc_identity_review)
            self.assertEqual(len(data["identity_review"]["candidates"]), 2)
            self.assertTrue(all(row["_optional_identity_review"] for row in result._cc_identity_review["records"]))
            first = data["identity_review"]["candidates"][0]
            choice = cc.resolve_identity_review({"token": data["identity_review"]["token"],
                "ein": org.ein, "state": "NV", "action": "accept", "candidate_id": first["id"]},
                "review@example.org", "test-device")
            self.assertEqual(choice["status"], "Current")
            self.assertEqual(choice["matched_registry_identifier"], first["identifier"])
            self.assertEqual(len([decision for decision in choice["identity_review"]["candidates"]
                                  if decision["decision"] == "reject"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
