"""Offline replay of the seven cards from the user's submitted NC search."""
import base64
import copy
import json
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import registry_snapshot_server as cc
from deployment import state_snapshots
from testing import run_final_four_continuation_guardrails as signed
from testing.test_state_snapshots import image

SOURCE = json.loads((Path(__file__).parent / "fixtures/nc-mercy-manual-source.json").read_text(encoding="utf-8"))
PARENT, COLORADO = SOURCE["rows"][0], SOURCE["rows"][2]


class AsOfSearch(date):
    @classmethod
    def today(cls):
        return cls(2026, 11, 8)


def payload(query, rows):
    return {"state": "NC", "query": query, "complete": True, "verification_pending": False,
            "search_mode": query.get("search_mode", "STARTS_WITH"), "total": len(rows), "rows": rows}


class MercySourceReplay(unittest.TestCase):
    def setUp(self):
        p = patch.object(cc, "date", AsOfSearch)
        p.start()
        self.addCleanup(p.stop)

    def test_past_extension_never_becomes_registration_or_due_date(self):
        row = cc.nc_charity_record_evidence(COLORADO)
        self.assertEqual(row["identifier"], "NCAPP-8874721")
        self.assertEqual(row["status"], "Unable to Confirm")
        self.assertTrue(row["unsupported_registration_scope"])
        self.assertNotIn("expiration", row)
        self.assertNotIn("extension_end", row)
        self.assertNotIn("non_charity_scope", row)

    def test_new_or_malformed_dates_and_changed_identity_still_fail(self):
        for change in (
            {"Extension End Date": "11/8/2026"}, {"Extension End Date": "11/9/2026"},
            {"Extension End Date": "2/30/2008"}, {"Expiration Date": "5/15/2008"},
            {"CSL Type": "Charitable Organization"}, {"Status": "Withdrawn"},
            {"profile_url": "https://wrong.example/8874721"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                cc.nc_charity_record_evidence({**COLORADO, **change})

    def test_seven_cards_and_selected_profile_through_signed_workflow(self):
        t = signed.ContinuationControls()
        t.setUp()
        self.addCleanup(t.doCleanups)
        t.orgs["NC"] = cc.checker.Organization("Mercy Housing Inc.", "470646706")
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        store = state_snapshots.SQLiteStore(Path(folder.name) / "source.sqlite")
        target = SOURCE["parent_profile"]
        queries = []
        with patch.object(state_snapshots, "STORE", store), patch.object(
                cc, "licensed_charity_names", return_value=(["Mercy Housing"], [])):
            code, response = t.start("NC", alternate_names=[
                "MERCY HOUSING, INC.",
                "MERCY HOUSING, INC., WHICH WILL DO BUSINESS IN CALIFORNIA AS NEBRASKA MERCY HOUSING, INC.",
            ])
            for _ in range(6):
                if response["phase"] == "complete":
                    break
                q = response["query"]
                queries.append(q)
                if q["operation"] == "search":
                    code, response = t.advance(response, evidence=payload(q, copy.deepcopy(SOURCE["rows"])))
                else:
                    self.assertEqual(q["identifier"], "SL004564")
                    self.assertEqual(q["url"], target["profile_url"])
                    evidence = {"query": q, "complete": True, "fields": target}
                    text = "Mercy Housing, Inc. SL004564 Current Active – Filing Extension Granted 11/15/2026"
                    snapshot = {"query": q, "source_url": q["url"], "captured_at": time.time(),
                                "public_text": text, "image": base64.b64encode(image("Mercy Housing, Inc.", "SL004564")).decode()}
                    code, response = t.advance(response, evidence=evidence, state_snapshot=snapshot)
        self.assertEqual((code, response["phase"]), (200, "complete"))
        r = response["result"]
        self.assertEqual(r["status"], "Upcoming Filing", r)
        self.assertEqual(r["matched_registry_identifier"], "SL004564")
        self.assertIn("2026-11-15", r["comments"])
        self.assertEqual([q["operation"] for q in queries], ["search", "detail"])
        artifact = r["evidence_url"].split("/")[-1].removesuffix(".pdf")
        meta, _, _ = store.load(artifact)
        self.assertEqual((meta["ein"], meta["identifier"]), ("470646706", "SL004564"))

    def test_matching_historical_application_cannot_become_positive_or_negative(self):
        t = signed.ContinuationControls()
        t.setUp()
        self.addCleanup(t.doCleanups)
        name = COLORADO["CSL Legal Name"]
        t.orgs["NC"] = cc.checker.Organization(name, "123456789")
        with patch.object(cc, "licensed_charity_names", return_value=([name], [])):
            code, response = t.start("NC")
            code, response = t.advance(response, evidence=payload(response["query"], [COLORADO]))
        self.assertEqual((code, response["phase"]), (200, "complete"))
        self.assertEqual(response["result"]["status"], "Unable to Confirm")
        self.assertFalse(response["result"]["success"])


if __name__ == "__main__":
    unittest.main()
