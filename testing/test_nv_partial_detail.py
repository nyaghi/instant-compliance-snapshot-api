import copy
import unittest
from unittest.mock import patch

import registry_snapshot_server as server


class NevadaPartialDetail(unittest.TestCase):
    def setUp(self):
        name = "American Civil Liberties Union, Inc."
        identifier = "NV20181623507"
        search = {"state": "NV", "operation": "search", "name": name}
        detail = {"state": "NV", "operation": "detail", "identifier": identifier}
        row = {"name": name, "identifier": identifier,
               "entity_type": "Foreign Non-Profit Corporation (80)", "raw_status": "Active"}
        fields = {"Entity Name": name, "NV Business ID": identifier,
                  "Entity Status": "Active", "Entity Type": row["entity_type"], "FEIN": "-",
                  "Solicits Charitable Contribution?": "Yes", "IRS Registered Name": "-",
                  "Campaign Name": "-", "Formation Date in Nevada": "08/29/2018",
                  "Annual Renewal Due Date/Expiration Date": "08/31/2035"}
        self.record = {"state": "NV", "ein": "133871360", "organization_name": name,
                       "completed": [
                           {"query": search, "evidence": {"state": "NV", "query": search,
                            "complete": True, "verification_pending": False, "total": 1, "rows": [row]}},
                           {"query": detail, "evidence": {"query": detail, "complete": True, "fields": fields,
                            "source_url": "https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen"
                                          "?screen=Manage-Business&id=d1b62c76-d5af-4ff3-b07d-038b7fa8d854"}}]}
        trial = patch.object(server, "trial_identity", return_value=True)
        trial.start()
        self.addCleanup(trial.stop)

    def test_keeps_source_verified_primary_as_review_only(self):
        self.record["completed"][0]["evidence"]["master_search_audit"] = {"source_total": 6, "rejected": 5}
        candidate, = server.nv_completed_candidates_for_review(self.record)
        self.assertEqual(candidate["identifier"], "NV20181623507")
        self.assertEqual(candidate["status"], "Current")
        self.assertEqual(candidate["_identity_outcome"], "possible")

    def test_rejects_conflicting_identity_and_unsourced_detail(self):
        for change in ({"FEIN": "13-1234567"}, {"Entity Name": "Different entity"},
                       {"NV Business ID": "NV9999"}):
            record = copy.deepcopy(self.record)
            record["completed"][1]["evidence"]["fields"].update(change)
            self.assertEqual(server.nv_completed_candidates_for_review(record), [])
        record = copy.deepcopy(self.record)
        record["completed"][1]["evidence"]["source_url"] = "https://example.org/invalid"
        self.assertEqual(server.nv_completed_candidates_for_review(record), [])
        record = copy.deepcopy(self.record)
        record["completed"].pop(0)
        self.assertEqual(server.nv_completed_candidates_for_review(record), [])

    def test_followup_budget_requires_a_saved_primary_and_a_different_name(self):
        search, primary = self.record["completed"]
        evidence = search["evidence"]
        main_id = primary["query"]["identifier"]
        evidence["rows"].extend([
            dict(evidence["rows"][0], identifier="NV101", name="American Civil Liberties Union Foundation"),
            dict(evidence["rows"][0], identifier="NV102", name="American Civil Liberties Union of Nevada"),
            dict(evidence["rows"][0], identifier="NV103"),
        ])
        evidence["total"] = len(evidence["rows"])
        self.record["mode"] = "standard"
        self.record["pending"] = {"query": dict(primary["query"], identifier="NV101")}
        budget = server.nv_followup_detail_budget
        self.assertIsNone(budget(self.record))
        self.record["source_snapshots"] = [{
            "state": "NV", "operation": "detail", "identifier": main_id, "ein": self.record["ein"],
            "record_name": self.record["organization_name"], "url": "/state-snapshots/fixture.pdf",
        }]
        with patch.object(server.time, "time", return_value=1000):
            self.assertEqual(budget(self.record), 45000)
        self.record["pending"]["query"]["identifier"] = "NV102"
        with patch.object(server.time, "time", return_value=1042):
            self.assertEqual(budget(self.record), 13000)
        with patch.object(server.time, "time", return_value=1056):
            self.assertEqual(budget(self.record), 0)
        self.record["pending"]["query"]["identifier"] = "NV103"
        self.assertIsNone(budget(self.record))
        self.record["pending"]["query"]["identifier"] = "NV102"
        self.record["mode"] = "sales"
        self.assertIsNone(budget(self.record))
        self.record["mode"] = "standard"
        self.record["source_snapshots"][0]["ein"] = "987654321"
        self.assertIsNone(budget(self.record))

    def test_single_distinctive_word_needs_full_name_and_same_record_image(self):
        name = "Americans for Prosperity"
        ein = "75-3148958"
        search, detail = self.record["completed"]
        key = detail["query"]["identifier"]
        self.record.update(organization_name=name, ein=ein, mode="standard")
        search["query"]["name"] = name
        search["evidence"]["rows"][0]["name"] = name
        search["evidence"]["rows"].append(dict(search["evidence"]["rows"][0],
                                                name=name+" Foundation", identifier="NV202"))
        search["evidence"]["total"] = 2
        detail["evidence"]["fields"]["Entity Name"] = name
        self.record["pending"] = {"query": dict(detail["query"], identifier="NV202")}
        self.assertEqual(server.nv_completed_candidates_for_review(self.record), [])
        ref = {"state":"NV", "operation":"detail", "identifier":key, "ein":"753148958",
               "record_name":name, "url":"/state-snapshots/fixture.pdf"}
        self.record["source_snapshots"] = [ref]
        self.assertEqual(server.nv_completed_candidates_for_review(self.record)[0]["identifier"], key)
        self.assertEqual(server.nv_followup_detail_budget(self.record), 45000)
        ref["identifier"] = "NV202"
        self.assertEqual(server.nv_completed_candidates_for_review(self.record), [])
        ref["identifier"] = key
        detail["evidence"]["fields"]["Entity Name"] = "The "+name
        self.assertEqual(server.nv_completed_candidates_for_review(self.record), [])
