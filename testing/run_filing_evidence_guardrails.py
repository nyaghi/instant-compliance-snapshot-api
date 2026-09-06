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
                text=cc.comments_for_result(r,"","Unable to Confirm")
                self.assertIn("Massachusetts cautions" if state=='MA' else "Missing filing information",text)

    def test_empty_template_after_no_charity_found_is_not_a_matched_record(self):
        r=self.result("MA","No record found","Not Registered")
        r.matched_registry_name=""
        body="No Charity Found. Annual Filings and Documents: No documents found. Charity Registration Documents"
        self.assertEqual(cc.true_status_from_body(r,body),"Not Registered")

    def test_explicit_adverse_status_preserved(self):
        r=self.result("MA","Registration Status: Delinquent | Annual Filings: No documents found")
        self.assertEqual(cc.true_status_from_body(r,""),"Delinquent")

    def test_no_match_preserved(self):
        r=self.result("CO","No matching organization record","Not Registered");r.matched_registry_name=""
        self.assertEqual(cc.true_status_from_body(r,""),"Not Registered")

    def test_completed_current_expiration_preserved(self):
        r=self.result("CO","Expiration Date: 4/15/2027","Current")
        self.assertEqual(cc.true_status_from_body(r,""),"Current")

class WashingtonFieldsTests(unittest.TestCase):
    def apply(self, text, ein="012345678"):
        m=cc.load_wa_nm_module()
        r=m.SearchResult(organization_name="Example",ein=ein,state="WA",status="Unknown",raw_status_text="",source_url="https://example.org",source_note="")
        return cc.wa_apply_detail_master(r,text)

    def body(self, status="Active", renewal="", optional="Yes", ein="012345678"):
        return f"FEIN Number:\n{ein}\nFederal Tax Exempt Status:\nYes\nFederal Status Type:\n501(c)(3)\nStatus:\n{status}\nRenewal Date:\n{renewal + chr(10) if renewal else ''}Is Optional Charities?\n{optional}\nCONTACT INFORMATION"

    def test_active_optional_is_exempt_with_plain_evidence(self):
        r=self.apply(self.body())
        self.assertEqual(r.status,"Exempt")
        self.assertIn("Status: Active",r.raw_status_text)
        self.assertNotIn("Renewal Date:",r.raw_status_text)
        self.assertIn("Optional Charity: Yes",r.raw_status_text)

    def test_exact_status_does_not_read_federal_tax_status(self):
        self.assertEqual(cc.wa_detail_field(self.body(),"Status"),"Active")
        self.assertEqual(cc.wa_detail_field(self.body(),"Renewal Date"),"")

    def test_standard_renewal_is_preserved(self):
        r=self.apply(self.body(renewal="12/31/2099",optional="No"))
        self.assertEqual(r.status,"Current")
        self.assertEqual(cc.true_status_from_body(r,""),"Current")
        self.assertIn("Renewal Date: 12/31/2099",r.raw_status_text)

    def test_pending_is_not_optional_exemption(self):
        self.assertEqual(self.apply(self.body(status="Pending")).status,"Pending")

    def test_missing_optional_flag_does_not_establish_exemption(self):
        self.assertEqual(self.apply(self.body(optional="No")).status,"Unable to Confirm")

    def test_wrong_fein_is_not_classified(self):
        r=self.apply(self.body(ein="999999999"))
        self.assertEqual(r.status,"Unable to Confirm")
        self.assertFalse(r.success)

    def test_closed_optional_is_not_exempt(self):
        r=self.apply(self.body(status="Voluntarily Closed"))
        self.assertEqual(r.status,cc.load_wa_nm_module().STATUS_CLOSED)

    def test_inline_labels_supported(self):
        self.assertEqual(cc.wa_detail_field("Status: Active\nRenewal Date: 12/31/2099","Status"),"Active")

if __name__ == '__main__': unittest.main(verbosity=2)
