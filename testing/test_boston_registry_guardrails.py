"""Replay observed identities alongside close names that must remain in scope."""
import json
import time
import unittest
from unittest.mock import patch

import registry_snapshot_server as cc

BOSTON = "Children's Hospital Corporation"
EIN = "042774441"
OTHER = "Children's Hospital Colorado Foundation"
OFFICE = {"ein": EIN, "street": "300 Longwood Avenue", "city": "Boston",
          "state": "MA", "zipcode": "02115"}
DC_FILER = {"ein": "530196580", "street": "111 Michigan Avenue NW", "city": "Washington",
            "state": "DC", "zipcode": "20010", "source_url": "https://apps.irs.gov/example"}


class BostonRegistryControls(unittest.TestCase):
    def setUp(self):
        self.org = cc.checker.Organization(BOSTON, EIN)
        self.limit = time.monotonic() + 25

    def test_public_dc_name_and_street_bind_a_different_filer(self):
        row = {"name": "CHILDREN'S HOSPITAL", "street": "111 MICHIGAN AVE NW",
               "region": "DC", "postal_code": "20010", "location": "",
               "identifier": "400216000323", "aliases": [], "ein": ""}
        names = [{"name": "Childrens Hospital", "verified": True}]
        results = {"organizations": [{"ein": 530196580, "name": "Childrens Hospital", "state": "DC"}],
                   "total_results": 1}
        for address, expected in [(DC_FILER, "rejected"), (DC_FILER | {"street": "222 Other Street"}, "possible")]:
            with self.subTest(expected=expected), patch.object(cc, "identity_fetch", return_value=json.dumps(results)), \
                    patch.object(cc, "identity_irs_names", return_value={"names": names, "filer_address": address}), \
                    patch.object(cc, "licensed_charity_street_evidence", return_value={}):
                observed = dict(row)
                cc.dc_screen_generic_candidates(self.org, [observed], self.limit)
                self.assertEqual(cc.licensed_charity_identity(self.org, observed, "DC", self.limit), expected)
        own = dict(row, ein="530196580")
        cc.dc_screen_generic_candidates(cc.checker.Organization("Children's Hospital", "530196580"), [own],
                                       self.limit)
        self.assertNotIn("_dc_generic_local_name", own)

    def test_dc_filer_region_does_not_exclude_a_full_reviewed_name(self):
        aliases = ("Boston Children's Hospital",)
        token = cc.REVIEWED_NAME_CONTEXT.set({EIN: aliases})
        rows = [
            dict(name=OTHER, region="CO", location="Aurora, CO"),
            dict(name=aliases[0], region="NY", location="New York, NY"),
            dict(name=OTHER, region="MA", location="Boston, MA"),
        ]
        try:
            with patch.object(cc, "identity_irs_names", return_value={"filer_address": OFFICE}):
                cc.dc_screen_generic_candidates(self.org, rows, self.limit)
            self.assertEqual([bool(row.get("_dc_generic_namesake")) for row in rows], [True, False, False])
        finally:
            cc.REVIEWED_NAME_CONTEXT.reset(token)

    def test_alabama_filters_only_weak_out_of_region_rows_after_office_match(self):
        candidates = [
            dict(name=OTHER, region="CO", street="Other Street", postal_code="80011", identifier="AL17-249"),
            dict(name="The Children's Hospital Foundation", region="MA", street="300 Longwood AVE",
                 postal_code="02115", identifier="AL25-369"),
            dict(name=BOSTON, region="NY", street="Other Street", postal_code="10001", identifier="primary"),
            dict(name=OTHER, region="", identifier="missing-office"),
        ]
        with patch.object(cc, "identity_cached_source_result", return_value={"filer_address": OFFICE}):
            self.assertEqual([r["identifier"] for r in cc.al_prioritize_plausible_office(self.org, candidates)],
                             ["AL25-369", "primary", "missing-office"])
        with patch.object(cc, "identity_cached_source_result", return_value=None):
            self.assertEqual(cc.al_prioritize_plausible_office(self.org, candidates), candidates)

    def test_north_carolina_exact_profile_completes_without_a_broad_grid(self):
        aliases = ("The Children's Hospital Corporation", "Boston Children's Hospital", "Children's Hospital Boston")
        token = cc.REVIEWED_NAME_CONTEXT.set({EIN: aliases})
        profile_url = "https://www.sosnc.gov/online_services/search/charities_profile/1000000"
        card = {"CSL Legal Name": aliases[0], "CSL Type": "Charitable Organization",
                "Status": "Current Active", "License": "SL017506", "Expiration Date": "02/15/2027",
                "profile_url": profile_url}
        detail = {"Name": aliases[0], "Registration #": card["License"], "Status": card["Status"],
                  "Expiration Date": card["Expiration Date"], "Last Application Date": "03/23/2026",
                  "Street": OFFICE["street"], "City": "Boston", "State": "MA", "Zip": "02115",
                  "profile_url": profile_url}
        lookups = []

        def collect(query):
            lookups.append(query)
            if query.get("operation") == "detail":
                return {"query": query, "complete": True, "fields": detail}
            self.assertIn(query["name"], [BOSTON, aliases[0]])
            rows = [card] if query["name"] == aliases[0] else []
            return {"state": "NC", "query": query, "complete": True, "verification_pending": False,
                    "search_mode": "STARTS_WITH", "total": len(rows), "rows": rows}

        try:
            with patch.object(cc, "trial_identity", return_value=True), \
                    patch.object(cc, "reconciled_registry_address", return_value={"decision": "corroborated"}):
                result = cc.final_four_browser_lookup(self.org, "NC", collect)
            self.assertEqual(result.matched_registry_identifier, "SL017506")
            self.assertEqual(lookups[0]["name"], BOSTON)
            self.assertEqual([r["operation"] for r in lookups], ["search", "search", "detail"])
        finally:
            cc.REVIEWED_NAME_CONTEXT.reset(token)


if __name__ == "__main__":
    unittest.main()
