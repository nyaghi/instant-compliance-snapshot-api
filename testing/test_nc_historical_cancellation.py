import unittest
from unittest.mock import patch

import registry_snapshot_server as cc


NAME = "Dana-Farber Cancer Institute, Inc."
ALIAS = "Dana-Farber, Inc."
EIN = "042263040"
PREFIX = "https://www.sosnc.gov/online_services/search/charities_profile/"
OLD = {"CSL Legal Name": ALIAS, "CSL Type": "Charitable Organization", "Status": "Cancelled",
       "License": "SL001463", "Expiration Date": "2/15/1999", "profile_url": PREFIX + "5698383"}
PRIMARY = {"CSL Legal Name": NAME, "CSL Type": "Charitable Organization", "Status": "Current Active",
           "License": "SL001850", "Expiration Date": "2/15/2027", "Extension End Date": "4/15/2027",
           "profile_url": PREFIX + "5701125"}
PROFILE = {"Name": NAME, "Registration #": "SL001850", "Status": "Current Active",
           "Expiration Date": "2/15/2027", "Extension End Date": "4/15/2027",
           "Last Application Date": "8/19/2026", "Street": "450 Brookline Ave Bp418",
           "City": "Boston", "State": "MA", "Zip": "02215-5418", "profile_url": PREFIX + "5701125"}


class HistoricalCancellation(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.org = cc.checker.Organization(NAME, EIN)
        token = cc.REVIEWED_NAME_CONTEXT.set({EIN: (ALIAS,)})
        self.addCleanup(cc.REVIEWED_NAME_CONTEXT.reset, token)
        for attr, value in {"trial_identity": True, "licensed_charity_names": ([NAME, ALIAS], []),
                            "licensed_charity_foreign_ein": {}, "user_rejected_credential": False}.items():
            p = patch.object(cc, attr, return_value=value)
            p.start()
            self.addCleanup(p.stop)

    def lookup(self, primary=True, corroborated=True):
        def source(q):
            if q["operation"] == "search":
                rows = [OLD, PRIMARY] if primary else [OLD]
                return {"state": "NC", "query": q, "complete": True, "verification_pending": False,
                        "rows": rows, "total": len(rows), "search_mode": q.get("search_mode", "STARTS_WITH")}
            self.calls.append(q["identifier"])
            if q["identifier"] == "SL001463":
                raise ValueError("official profile warning")
            return {"query": q, "complete": True, "fields": PROFILE}
        if corroborated:
            return cc.final_four_browser_lookup(self.org, "NC", source)
        with patch.object(cc, "licensed_charity_identity", return_value="possible"):
            return cc.final_four_browser_lookup(self.org, "NC", source)

    def test_live_cards_exact_current_primary_precedes_broken_canceled_profile(self):
        result = self.lookup()
        self.assertTrue(result.success)
        self.assertEqual(result.matched_registry_identifier, "SL001850")
        self.assertEqual(result.status, cc.status_from_calendar_date(cc.date(2027, 4, 15)))
        self.assertEqual(self.calls, ["SL001850"])
        self.assertIn("SL001463", result.source_note)

    def test_without_corroboration_or_exact_primary_does_not_ignore_warning(self):
        with self.assertRaisesRegex(ValueError, "official profile warning"):
            self.lookup(corroborated=False)
        self.assertIn("SL001463", self.calls)
        with self.assertRaisesRegex(ValueError, "official profile warning"):
            self.lookup(primary=False)

    def test_only_past_explicit_shorter_charity_cancellation_can_be_set_aside(self):
        record = cc.nc_charity_record_evidence(OLD)
        primary = cc.normalized_match_name(NAME)
        self.assertTrue(cc.nc_short_historical_cancellation(record, primary))
        for change in ({"name": NAME}, {"name": "Farber"}, {"name": "Dana Farber Partners"},
                       {"raw_status": "Expired License"}, {"raw_status": "Suspended"},
                       {"expiration": None}, {"expiration": cc.date.today()}, {"identifier": "EX1"}):
            self.assertFalse(cc.nc_short_historical_cancellation({**record, **change}, primary), change)
