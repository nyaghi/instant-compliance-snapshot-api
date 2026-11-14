import unittest
from datetime import date, timedelta
from unittest.mock import patch
import registry_snapshot_server as cc
from testing.run_dc_ri_guardrails import row


class RhodeIslandMississippiRepair(unittest.TestCase):
    def test_mississippi_reviewed_literal_precedes_generated_probes(self):
        org = cc.checker.Organization("Beacon Learning Foundation, Inc.", "12-3456789")
        alias = "Beacon Education Society"
        searched = []
        def evidence(query):
            searched.append(query["name"])
            return dict(state="MS", query=query, complete=True, verification_pending=False, rows=[], total=0)
        result = cc.ms_browser_lookup(org, evidence, [alias])
        self.assertEqual(result.status, "Not Registered")
        self.assertEqual(searched[:2], [org.organization_name, alias])
        self.assertEqual(len(searched), len(set(q.casefold() for q in searched)))

    def test_mississippi_verified_record_ignores_weaker_detail_that_times_out(self):
        name = "Beacon Learning Academy"
        org = cc.checker.Organization(name, "12-3456789")
        wanted = dict(name=name, identifier="100001780", raw_status="Closed/Withdrawn")
        weaker = dict(name=name + " Foundation", identifier="100033077", raw_status="Current")
        requests = []

        def evidence(query):
            requests.append(query)
            if query["operation"] == "search":
                return dict(state="MS", query=query, complete=True, verification_pending=False,
                            rows=[weaker, wanted], total=2)
            if query["identifier"] != wanted["identifier"]:
                raise TimeoutError("weak detail failed")
            return dict(query=query, complete=True, source_url=cc.MS_BROWSER_SOURCE, fields={
                "Name": name, "Registered Name": name, "Filing Number": wanted["identifier"],
                "Filing Status": wanted["raw_status"], "Expiration Date": ""})

        result = cc.ms_browser_lookup(org, evidence)
        self.assertEqual(result.matched_registry_identifier, wanted["identifier"])
        self.assertTrue(result.status.startswith("Closed / Withdrawn"))
        self.assertEqual([q["identifier"] for q in requests if q["operation"] == "detail"], ["100001780"])

    def test_mississippi_generic_hospital_uses_its_registered_identity(self):
        org = cc.checker.Organization("CHILDREN'S HOSPITAL CORPORATION", "04-2774441")
        aliases = ["THE CHILDREN'S HOSPITAL CORPORATION", "Boston Children's Hospital",
                   "Children's Hospital Boston", "Boston Children's Hospital Trust",
                   "BCH Trust", "Children's Hospital Corporation, The"]
        registry_name = "Children's Hospital"
        filing = "100001780"
        unrelated = "Children's Hospital & Research Center Foundation"

        def lookup(registered_name):
            details = []
            def evidence(query):
                if query["operation"] == "detail":
                    details.append(query["identifier"])
                    self.assertEqual(query["identifier"], filing)
                    return dict(query=query, complete=True, source_url=cc.MS_BROWSER_SOURCE, fields={
                        "Name": registry_name, "Registered Name": registered_name, "Filing Number": filing,
                        "Filing Status": "Closed - Expired", "Expiration Date": "04/12/1995"})
                rows = []
                if query["name"].casefold() == registry_name.casefold():
                    rows = [
                        dict(name=registry_name, identifier=filing, raw_status="Closed - Expired"),
                        dict(name=unrelated, identifier="100001931", raw_status="Current"),
                    ]
                return dict(state="MS", query=query, complete=True, verification_pending=False,
                            rows=rows, total=len(rows))
            return cc.ms_browser_lookup(org, evidence, aliases), details

        result, details = lookup("Children's Hospital D/B/A FOUNDATION")
        self.assertEqual(result.status, "Not Registered")
        self.assertIn(filing, result.source_note)
        self.assertEqual(details, [filing])

        result, _ = lookup("Boston Children's Hospital")
        self.assertTrue(result.status.startswith("Closed / Withdrawn"))
        self.assertEqual(result.matched_registry_identifier, filing)

        result, _ = lookup("")
        self.assertEqual(result.status, "Needs Review")
        self.assertFalse(result.success)

    def test_rhode_island_foundation_requires_expiry_and_absence_of_identity(self):
        org = cc.checker.Organization("Children's Hospital Corporation", "04-2774441")
        name = "Children's Hospital Foundation Inc"
        candidate = {"id": "1", "title": name}
        historical = row(name, "CO.9701175", days=-1000)
        historical.update(raw_status="Inactive", location="", ein="", street="")
        for key, value in [(None, None), ("ein", "042774441"), ("expiration", date.today() + timedelta(days=7)), ("raw_status", "Active")]:
            record = dict(historical)
            if key:
                record[key] = value
            with self.subTest(key=key), patch.object(cc,"trial_identity",return_value=True), patch.object(cc,"registry_json_request",return_value={"access_token":"fixture"}), patch.object(cc,"licensed_charity_names",return_value=([org.organization_name],[])), patch.object(cc,"ri_charity_search",return_value=[candidate]), patch.object(cc,"ri_charity_detail",return_value=record), patch.object(cc,"score_candidate",return_value={"decision":"possible"}), patch.object(cc,"licensed_charity_foreign_ein",return_value={}), patch.object(cc,"licensed_charity_result",wraps=cc.licensed_charity_result) as final:
                result = cc.search_ri(org)
                if key is None:
                    self.assertEqual(result.status,"Not Registered")
                    self.assertIn("CO.9701175",result.source_note)
                    self.assertEqual(final.call_args.args[2], [])
                else:
                    self.assertNotEqual(result.status, "Not Registered")
                    final.assert_not_called()

    def test_rhode_island_timeout_is_not_a_completed_negative(self):
        org = cc.checker.Organization("Beacon Learning Foundation", "12-3456789")
        with patch.object(cc,"registry_json_request",side_effect=TimeoutError("source timed out")), patch.object(cc,"log_error"):
            result = cc.search_ri(org)
        self.assertFalse(result.success)
        self.assertEqual(result.status_reason,"RI_LOOKUP_TIMEOUT")
        self.assertNotEqual(result.status,"Not Registered")
