import time
import unittest
from datetime import date
from unittest.mock import patch

import registry_snapshot_server as cc
from testing.run_il_ga_guardrails import ga_html, search_row


class Gate37Replays(unittest.TestCase):
    full = "The National Alliance to End Homelessness, Incorporated"
    shortened = "The National Alliance to End Homeless, Incorporated"

    def ga(self, grid, detail, **changes):
        queries = []
        org = cc.checker.Organization(self.full, "521299641")
        def evidence(query):
            queries.append(query)
            if "identifier" in query:
                return {"body": ga_html(**{"full_name":detail, "license_no":"CH011901",
                    "status":"Active", "expiry":"12/21/2027", **changes})}
            return {"rows": [search_row(grid, "CH011901", "fixture")]}
        with patch.object(cc, "known_names_for_ein", return_value=[]), patch.object(
                cc, "reconciled_registry_address", return_value={"decision":"unavailable"}):
            return cc.il_ga_browser_lookup(org, "GA", evidence), queries

    def test_ga_observed_shortened_grid_and_detail_retained_for_review(self):
        result, queries = self.ga(self.shortened, self.shortened)
        self.assertFalse(result.success)
        records = result._cc_identity_review["records"]
        self.assertEqual([(r["identifier"], r["_identity_outcome"]) for r in records], [("CH011901", "possible")])
        self.assertEqual(len([q for q in queries if "identifier" in q]), 1)

    def test_ga_full_grid_and_shortened_bound_detail_still_requires_review(self):
        result, _ = self.ga(self.full, self.shortened)
        self.assertFalse(result.success)
        self.assertEqual(result._cc_identity_review["records"][0]["name"], self.shortened)

    def test_ga_exact_bound_record_preserves_status(self):
        result, _ = self.ga(self.full, self.full)
        self.assertTrue(result.success)
        self.assertEqual(result.matched_registry_identifier, "CH011901")

    def test_ga_different_license_or_name_still_rejected(self):
        for name, options in ((self.shortened, {"license_no":"CH011902"}),
                              ("National Alliance to End Housing", {})):
            with self.subTest(name=name, options=options), self.assertRaises(ValueError):
                self.ga(self.full, name, **options)

    def ri(self, second, other=None):
        values = [
            {"label":"Credential", "value":["CO.9703004", "Charitable Organization"]},
            {"label":"Status", "value":["ACTIVE PENDING RENEWAL"]},
            {"label":"Expiration Date", "value":["01/03/2027"]},
            {"label":"Business Address", "value":["", "1600 Broadway, Suite 2000", "", "Denver, Colorado 80202", "United States"]},
            {"label":"Business Address", "value":["", second[0], "", second[1], second[2]]},
        ]
        if other is not None: values.append(other)
        payload = {"id":"C39348", "name":"Details for Mercy Housing, Inc.", "tiles":[{"steps":[
            {"name":"Summary", "contents":[{"data":values}]}]}]}
        with patch.object(cc, "registry_json_request", return_value=payload):
            return cc.ri_charity_detail({"id":"C39348", "title":"Mercy Housing, Inc."}, time.monotonic()+2, {})

    def test_ri_observed_duplicate_locality_retains_original_pending_record(self):
        record = self.ri(("1600 Broadway, Suite 2000, Denver,", "DENVER, Colorado 80202", "United States"))
        self.assertEqual((record["identifier"], record["status"], record["expiration"]),
                         ("CO.9703004", "Pending", date(2027,1,3)))
        self.assertEqual((record["street"], record["location"]), ("1600 Broadway, Suite 2000", "Denver, CO"))

    def test_ri_true_conflicts_remain_rejected(self):
        for street, locality, country in (
            ("1600 Broadway, Suite 3000, Denver,", "Denver, Colorado 80202", "United States"),
            ("1600 Broadway, Suite 2000, Denver,", "Denver, Colorado 80203", "United States"),
            ("1600 Broadway, Suite 2000, Denver,", "Denver, Colorado 80202", "Canada"),
            ("1600 Broadway, Suite 2000, Aurora,", "Denver, Colorado 80202", "United States"),
        ):
            with self.subTest(street=street, locality=locality, country=country), self.assertRaisesRegex(ValueError, "conflicting"):
                self.ri((street, locality, country))
        with self.assertRaisesRegex(ValueError, "conflicting"):
            self.ri(("1600 Broadway, Suite 2000, Denver,", "Denver, Colorado 80202", "United States"),
                    {"label":"Status", "value":["REVOKED"]})


if __name__ == "__main__":
    unittest.main()
