"""Replay the NJ exemption row observed for Catholic Relief Services."""
import time
import unittest
from unittest.mock import patch

import registry_snapshot_server as cc

NAME = "CATHOLIC RELIEF SERVICES-UNITED STATES CONFERENCE OF CATHOLIC BISHOPS"
LISTED = "CATHOLIC RELIEF SERVICES-USCC"


class CatholicLegacyExemption(unittest.TestCase):
    def setUp(self):
        self.org = cc.checker.Organization(NAME, "135563422")
        token = cc.LAB_LOOKUP_MODE_CONTEXT.set("standard")
        self.addCleanup(cc.LAB_LOOKUP_MODE_CONTEXT.reset, token)
        for name, value in [("trial_identity", {"origin": "local"}),
                            ("known_names_for_ein", []),
                            ("user_rejected_credential", False)]:
            active = patch.object(cc, name, return_value=value)
            active.start()
            self.addCleanup(active.stop)

    def result(self, name=LISTED, ein="000000000"):
        fields = {"name": name, "crsm_federalein": ein, "crsm_filestanding": "Exempt"}
        data = {"ItemCount": 1, "PageNumber": 1, "MoreRecords": False,
                "Records": [{"Attributes": [{"Name": key, "DisplayValue": value}
                                           for key, value in fields.items()]}]}
        return cc.nj_name_exemption_result(data, self.org, time.monotonic() + 2)

    def test_abbreviated_legacy_exemption_is_available_for_identity_confirmation(self):
        result = self.result()
        self.assertEqual(result.reason_code, "NJ_UNNUMBERED_EXEMPTION_REVIEW")
        self.assertFalse(result.success)
        row, = result._cc_identity_review["records"]
        self.assertEqual((row["name"], row["ein"], row["status"]), (LISTED, "", "Exempt"))

    def test_real_ein_mismatch_and_unrelated_acronym_remain_excluded(self):
        self.assertIsNone(self.result(ein="123456789"))
        self.assertIsNone(self.result(name="CATHOLIC RELIEF SERVICES-XYZ"))

    def test_distinctive_compound_component_precedes_generated_fragments(self):
        queries = cc.nj_name_fallback_queries(self.org)
        self.assertEqual(cc.normalized_match_name(queries[0]), cc.normalized_match_name(NAME))
        self.assertEqual(queries[1], "CATHOLIC RELIEF SERVICES")
        self.assertEqual(len(queries), len(set(map(cc.normalized_match_name, queries))))


if __name__ == "__main__":
    unittest.main()
