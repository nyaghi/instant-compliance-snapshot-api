"""NY extension policy controls sourced from the AG's CHAR500 deadline table.

https://ag.ny.gov/sites/default/files/regulatory-documents/extensiongranted.pdf
Verified September 11, 2026. All registry responses here are fixtures.
"""
import copy
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc

class AsOf(date):
    value=date(2026,9,11)
    @classmethod
    def today(cls):return cls(cls.value.year,cls.value.month,cls.value.day)

class NYExtensionTests(unittest.TestCase):
    def setUp(self):
        AsOf.value=date(2026,9,11)
        self.clock=patch.object(cc,'date',AsOf);self.clock.start();self.addCleanup(self.clock.stop)
        self.org=cc.checker.Organization('Year Up, Inc.','04-3534407')
    def result(self,fye='2024-12-31',category='7A',status='Unknown'):
        r=cc.checker.StateResult(self.org.organization_name,self.org.ein,'NY',status,'')
        r.matched_registry_name=self.org.organization_name;r.matched_registry_identifier='043534407'
        r.raw_status_text=f'Registration category: {category} | Latest FYE: {fye}'
        return r
    def interpret(self,r):
        return cc.apply_ny_latest_fye_next_cycle_status(self.org,r)
    def test_year_up_exact_deadline_and_comment(self):
        r=self.interpret(self.result())
        self.assertEqual(r.status,'Upcoming Filing');self.assertEqual(r.computed_due_date,'11/15/2026')
        self.assertEqual(cc.ny_safe_due_status_from_evidence(self.org,r),'Upcoming Filing')
        self.assertEqual(cc.true_status_from_body(r,r.raw_status_text),'Upcoming Filing')
        comment=cc.comments_for_result(r,'','Upcoming Filing')
        for text in ['12/31/2024','12/31/2025','5/15/2026','11/15/2026','automatic filing extension']:self.assertIn(text,comment)
        self.assertNotIn('This date has passed',comment)
    def test_deadline_boundaries(self):
        for today,expected in [(date(2026,5,14),'Current'),(date(2026,5,15),'Upcoming Filing'),
              (date(2026,5,16),'Upcoming Filing'),(date(2026,9,11),'Upcoming Filing'),
              (date(2026,11,14),'Upcoming Filing'),(date(2026,11,15),'Upcoming Filing'),(date(2026,11,16),'Delinquent')]:
            with self.subTest(today=today):
                AsOf.value=today;self.assertEqual(self.interpret(self.result()).status,expected)
    def test_all_twelve_published_7a_dual_dates(self):
        # Independent literal rows from the state table, for fiscal years in 2025.
        rows=[('1/31/2025','6/15/2025','12/15/2025'),('2/28/2025','7/15/2025','1/15/2026'),
          ('3/31/2025','8/15/2025','2/15/2026'),('4/30/2025','9/15/2025','3/15/2026'),
          ('5/31/2025','10/15/2025','4/15/2026'),('6/30/2025','11/15/2025','5/15/2026'),
          ('7/31/2025','12/15/2025','6/15/2026'),('8/31/2025','1/15/2026','7/15/2026'),
          ('9/30/2025','2/15/2026','8/15/2026'),('10/31/2025','3/15/2026','9/15/2026'),
          ('11/30/2025','4/15/2026','10/15/2026'),('12/31/2025','5/15/2026','11/15/2026')]
        for category in ['7A','DUAL']:
            for fye,base,extended in rows:
                with self.subTest(category=category,fye=fye):
                    actual=cc.ny_filing_deadlines(cc.parse_due_date(fye),category)
                    self.assertEqual(tuple(cc.format_date(d) for d in actual),(base,extended))
    def test_eptl_separate_schedule_and_leap_year(self):
        for fye,base,extended in [('12/31/2025','6/30/2026','12/31/2026'),('6/30/2025','12/31/2025','6/30/2026'),
          ('8/31/2023','2/29/2024','8/31/2024'),('2/28/2023','8/31/2023','2/29/2024')]:
            with self.subTest(fye=fye):
                self.assertEqual(tuple(cc.format_date(d) for d in cc.ny_filing_deadlines(cc.parse_due_date(fye),'EPTL')),(base,extended))
        self.assertEqual(self.interpret(self.result(category='EPTL')).computed_due_date,'12/31/2026')
    def test_current_overdue_and_noncalendar_controls(self):
        for fye,expected,due in [('2025-12-31','Current','11/15/2027'),('2023-12-31','Delinquent','11/15/2025'),
             ('2024-06-30','Delinquent','5/15/2026'),('2025-09-30','Current','8/15/2027')]:
            r=self.interpret(self.result(fye));self.assertEqual((r.status,r.computed_due_date),(expected,due))
    def test_idempotency_and_stale_derived_date_replacement(self):
        r=self.result();r.raw_status_text+=' | Next Required Period: 2025-12-31 | Next Filing Due: 5/15/2026'
        self.interpret(r);once=copy.deepcopy(vars(r));self.interpret(r)
        self.assertEqual(vars(r),once);self.assertEqual(r.raw_status_text.count('Next Filing Due:'),1)
        self.assertNotIn('Next Filing Due: 5/15/2026',r.raw_status_text)
    def test_exempt_and_explicit_adverse_records_preserved(self):
        for status in ['Exempt','Pending','Suspended','Revoked','Closed / Withdrawn / Canceled','Delinquent']:
            r=self.result(status=status)
            if status=='Delinquent':r.raw_status_text+=' | Registration Status: Delinquent'
            self.interpret(r);self.assertEqual(r.status,status)
            self.assertEqual(cc.ny_safe_due_status_from_evidence(self.org,r),'')
    def test_explicit_denial_uses_base_deadline(self):
        r=self.result();r.raw_status_text+=' | Extension status: Denied';self.interpret(r)
        self.assertEqual((r.status,r.computed_due_date),('Delinquent','5/15/2026'))
        self.assertIn('extension was denied',cc.comments_for_result(r,'',r.status))
    def test_no_identity_no_filing_and_non_ny_are_not_promoted(self):
        r=self.result();r.matched_registry_identifier='123456789';r.matched_registry_name='Unrelated Charity'
        self.assertEqual(self.interpret(r).status,'Unknown')
        r=self.result(status='Not Registered');r.raw_status_text='No results found';self.assertEqual(self.interpret(r).status,'Not Registered')
        for state in ['CO','MA','CA','MD']:
            r=self.result();r.state=state;before=copy.deepcopy(vars(r));self.interpret(r);self.assertEqual(vars(r),before)
    def test_live_response_requires_category_and_retains_eptl(self):
        row={'orgName':self.org.organization_name,'ein':'043534407','orgID':'21-57-43'}
        def response(data):
            r=Mock();r.json.return_value={'success':True,'statusCode':200,'data':data};return r
        for category in ['7A','DUAL','EPTL',None,'UNKNOWN']:
            detail={**row,'regType':'NFP','regStatute':category,'documents':{'Annual Filing for Charitable Organizations':[{'fiscalYearEnd':'12/31/2024'}]}}
            session=Mock();session.__enter__=Mock(return_value=session);session.__exit__=Mock(return_value=False)
            session.get.side_effect=[response([row]),response(detail)]
            with patch.object(cc.curl_requests,'Session',return_value=session):r=cc.search_ny_direct(self.org)
            if category in ['7A','DUAL','EPTL']:
                self.assertEqual(r.status,'Upcoming Filing');self.assertEqual(r.ny_filing_evidence['category'],category)
            else:self.assertEqual(r.status,'Unable to Confirm');self.assertFalse(r.success)

if __name__=='__main__':unittest.main(verbosity=2)
