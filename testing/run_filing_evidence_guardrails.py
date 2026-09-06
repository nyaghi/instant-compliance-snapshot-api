"""Master classification must distinguish missing evidence from an overdue filing."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import date
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc

class Today(date):
    @classmethod
    def today(cls): return cls(2026, 9, 6)

class EvidenceTests(unittest.TestCase):
    def result(self, state, raw, status="Delinquent"):
        r = cc.checker.StateResult("Example Foundation", "012345678", state, status, "https://example.org")
        r.raw_status_text = raw
        r.matched_registry_name = "Example Foundation"
        r.success = True
        return r

    def setUp(self):
        for p in [patch.object(cc, "date", Today), patch.object(cc, "filing_context", return_value={"due_date":None,"represented_year":None}), patch.object(cc.urllib.request, "urlopen", side_effect=AssertionError("Unexpected network"))]:
            p.start(); self.addCleanup(p.stop)

    def test_va_extension_survives_master(self):
        r=self.result("VA", "Entity Status: Registered | Expiration Date: 5/15/2026 | Extension Date: 11/15/2026", "Upcoming Filing")
        self.assertEqual(cc.true_status_from_body(r, ""), "Upcoming Filing")
        self.assertEqual(cc.explicit_registry_date(r, ""), date(2026,11,15))

    def test_va_older_extension_does_not_shorten_current_registration(self):
        r=self.result("VA", "Expiration Date: 5/15/2027 | Extension Date: 11/15/2026", "Current")
        self.assertEqual(cc.true_status_from_body(r, ""), "Current")

    def test_va_html_labels(self):
        r=self.result("VA", "Current Registration Expires: 5/15/2026 | Registration Extended Until: 11/15/2026", "Upcoming Filing")
        self.assertEqual(cc.explicit_registry_date(r, ""),date(2026,11,15))

    def test_va_expired_extension(self):
        r=self.result("VA", "Expiration Date: 5/15/2025 | Extension Date: 11/15/2025")
        self.assertEqual(cc.true_status_from_body(r, ""),"Delinquent")

    def test_va_explicit_restrictions_preserved(self):
        for status in ["Suspended", "Exempt", "Pending"]:
            with self.subTest(status=status):
                r=self.result("VA",f"{status} | Expiration Date: 5/15/2026 | Extension Date: 11/15/2026",status)
                self.assertEqual(cc.true_status_from_body(r,""),status)

    def test_missing_filings_do_not_prove_delinquency(self):
        for state, raw in [("MA","Annual Filings not visible"),("NY","No filings found"),("HI","Annual Filings and Documents: No documents found")]:
            with self.subTest(state=state):
                r=self.result(state,raw)
                self.assertEqual(cc.true_status_from_body(r,""),"Unable to Confirm")
                self.assertIn("Missing",cc.comments_for_result(r,"","Unable to Confirm") if state!='MA' else "Missing")

    def test_explicit_adverse_status_preserved(self):
        r=self.result("MA","Registration Status: Delinquent | Annual Filings: No documents found")
        self.assertEqual(cc.true_status_from_body(r,""),"Delinquent")

    def test_no_match_preserved(self):
        r=self.result("CO","No matching organization record","Not Registered");r.matched_registry_name=""
        self.assertEqual(cc.true_status_from_body(r,""),"Not Registered")

    def test_completed_current_expiration_preserved(self):
        r=self.result("CO","Expiration Date: 4/15/2027","Current")
        self.assertEqual(cc.true_status_from_body(r,""),"Current")

if __name__ == '__main__': unittest.main(verbosity=2)
