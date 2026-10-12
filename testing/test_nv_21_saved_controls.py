"""Replay saved Nevada selector evidence from the 21-organization control group.

This tests the changed identity-selection/review path, not fresh registry access,
name discovery, or end-to-end timing. The source is the October 10 first passes.
"""
import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc


CASES = json.loads((Path(__file__).parent / "fixtures" / "nv-21-saved-controls.json")
                   .read_text(encoding="utf-8"))["cases"]


class NevadaSavedControlGroup(unittest.TestCase):
    def test_all_21_saved_selector_outcomes(self):
        self.assertEqual(len(CASES), 21)

        def accepted(_org, row, _state, _deadline):
            row["match"] = {"decision": "accepted"}
            row["address_evidence"] = {"decision": "corroborated"}
            return "accepted"

        for case in CASES:
            with self.subTest(organization=case["organization"]):
                org = cc.checker.Organization(case["organization"], case["ein"])
                rows = []
                if case["registry_id"]:
                    rows.append({"name": case["registry_name"],
                                 "identifier": case["registry_id"],
                                 "status": case["saved_status"],
                                 "raw_status": case["raw_status"],
                                 "ein": "", "location": "", "expiration": None,
                                 "initial": "", "url": "https://orion.nv.gov/portal/public/"})
                with patch.object(cc, "licensed_charity_identity", side_effect=accepted):
                    result = cc.licensed_charity_result(
                        org, "NV", rows, time.monotonic() + 5,
                        "https://orion.nv.gov/portal/public/")
                self.assertEqual(result.status, case["saved_status"])
                self.assertEqual(getattr(result, "matched_registry_identifier", ""),
                                 case["registry_id"])
                self.assertFalse(getattr(result, "_cc_identity_review", None))
                self.assertFalse(any(row.get("_optional_identity_review") for row in rows))


if __name__ == "__main__":
    unittest.main(verbosity=2)
