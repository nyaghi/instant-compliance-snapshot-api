"""Recorded ND extensions and the single user-approved Arkansas name pair."""
import sys, time, unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc
import charity_clarity_report as report

class Today(date):
    @classmethod
    def today(cls): return cls(2026, 9, 14)

class NorthDakotaTests(unittest.TestCase):
    def setUp(self):
        for p in [patch.object(cc, 'date', Today), patch.object(cc, 'filing_context', return_value={
                'due_date': None, 'represented_year': None, 'fiscal_end': None})]:
            p.start(); self.addCleanup(p.stop)

    def result(self, status='Active', state='ND', matched=True):
        r=cc.checker.StateResult('Test Charity', '01-2345678', state, status, 'https://firststop.sos.nd.gov/search/charitable')
        r.raw_status_text=status; r.success=True
        if matched:r.matched_registry_name='Test Charity';r.matched_registry_identifier='test-record'
        return r

    def test_explicit_extension_and_cycle_boundaries(self):
        cases=[('9/1/2026','12/1/2026','Upcoming Filing'), ('9/1/2027','N/A','Current'),
               ('9/1/2026','N/A','Delinquent'), ('9/1/2025','12/1/2025','Delinquent'),
               ('9/1/2027','12/1/2027','Current'), ('9/1/2026','invalid','Delinquent'),
               ('9/1/2026','12/1/2025','Delinquent'), ('9/1/2026','12/1/2027','Delinquent'),
               ('9/1/2026','12/2/2026','Delinquent'), ('9/1/2026','9/14/2026','Upcoming Filing'),
               ('9/1/2026','9/13/2026','Delinquent')]
        for base,extended,expected in cases:
            with self.subTest(base=base,extended=extended):
                self.assertEqual(cc.true_status_from_body(self.result(),f'Status: Active\nAR Due Date: {base}\nAR Extended Due Date: {extended}\nInactive Date: N/A'),expected)

    def test_explicit_overrides_remain(self):
        for status,expected in [('Inactive','Closed / Withdrawn / Canceled'),('Revoked','Revoked'),
                                ('Suspended','Suspended'),('Pending','Pending'),('Exempt','Exempt'),
                                ('Delinquent','Delinquent'),('Not Registered','Not Registered'),
                                ('Site Not Reachable','Site Not Reachable'),('Unable to Confirm','Unable to Confirm')]:
            with self.subTest(status=status):
                r=self.result(status,matched=status!='Not Registered')
                self.assertEqual(cc.true_status_from_body(r,f'Status: {status}\nAR Due Date: 9/1/2026\nAR Extended Due Date: 12/1/2026'),expected)
                self.assertNotEqual(getattr(r,'status_reason',''),'ND_RECORDED_ANNUAL_REPORT_EXTENSION')

    def test_other_state_date_rule_unchanged(self):
        for state in ['FL','WI']:
            r=self.result('Current',state)
            self.assertEqual(cc.true_status_from_body(r,'Status: Current\nAR Due Date: 9/1/2026\nAR Extended Due Date: 12/1/2026'),'Delinquent')
            self.assertNotEqual(getattr(r,'status_reason',''),'ND_RECORDED_ANNUAL_REPORT_EXTENSION')

    def test_full_response_and_report_agree(self):
        r=self.result(); org=cc.checker.Organization('Test Charity','01-2345678')
        body='Status: Active\nAR Due Date: 9/1/2026\nAR Extended Due Date: 12/1/2026\nInactive Date: N/A'
        response=cc.response_data_for_lookup(r,body,org,org.organization_name,org.ein,'ND',time.perf_counter())
        self.assertEqual(response['status'],'Upcoming Filing')
        self.assertEqual(response['computed_due_date'],'12/1/2026')
        self.assertEqual(report.snapshot_due_date(response),date(2026,12,1))
        self.assertIn('12/1/2026',response['comments'])
        self.assertNotIn('does not fully explain',response['comments'])

class ArkansasTests(unittest.TestCase):
    name='Chemical Coaters Association International Finishing Education Foundation, Inc.'
    short='Chemical Coaters Association International'

    def lookup(self, rows, ein='832985088', name=None):
        org=cc.checker.Organization(name or self.name,ein)
        with patch.object(cc,'ar_preferred_name_variants',return_value=[org.organization_name,*cc.literal_name_retrieval_forms(org.organization_name)[:1]]), \
             patch.object(cc,'organization_name_variants',return_value=[]), \
             patch.object(cc,'ar_wait_for_search_form',return_value=True), \
             patch.object(cc,'registry_page_body',return_value='Back to Search Form Registration Date'), \
             patch.object(cc,'safe_wait_for_network_idle'),patch.object(cc,'ar_result_rows',return_value=rows):
            r=cc.search_ar_precise(Mock(),org)
        return cc.response_data_for_lookup(r,r.raw_status_text,org,org.organization_name,org.ein,'AR',time.perf_counter())

    def row(self, status='Current', **extra):
        return dict(name=self.short,status=status,type='Charity',registration_date='2020-05-28',**extra)

    def test_approved_pair_retains_status_and_ein_caution(self):
        for raw,expected in [('Current','Current'),('Not Current','Delinquent')]:
            with self.subTest(raw=raw):
                value=self.lookup([self.row(raw)])
                self.assertEqual(value['status'],expected)
                self.assertEqual(value['reason_code'],'AR_APPROVED_NAME_EIN_CONFIRMATION')
                self.assertEqual(value['matched_registry_name'],self.short)
                self.assertIn('Confirm the EIN with Arkansas.',value['comments'])
                self.assertIn(f'as {raw}.',value['comments'])
                self.assertNotIn('exact EIN',value['comments'])

    def test_approval_does_not_cross_identity_boundaries(self):
        self.assertEqual(self.lookup([self.row()],ein='832985089')['status'],'Needs Review')
        self.assertEqual(self.lookup([self.row()],name=self.name.replace('Finishing','Painting'))['status'],'Needs Review')
        self.assertEqual(self.lookup([self.row(ein='237159835')])['status'],'Not Registered')
        self.assertFalse(cc.ar_user_accepted_name_match(self.short+' Education',self.name,'832985088'))
        self.assertFalse(cc.ar_user_accepted_name_match(self.short,self.name,''))
        self.assertEqual(cc.ar_candidate_identity(self.row(ein='832985088'),self.name,[self.name],'832985088'),'accept')

    def test_active_tie_break_remains(self):
        for rows in [[self.row('Not Current'),self.row('Current')],[self.row('Current'),self.row('Not Current')]]:
            self.assertEqual(self.lookup(rows)['status'],'Current')

    def test_other_registered_and_no_record_controls(self):
        row={'name':'Make-A-Wish Foundation of America','status':'Current','type':'Charity','registration_date':'2020-05-28'}
        value=self.lookup([row],ein='860481941',name=row['name'])
        self.assertEqual(value['status'],'Current')
        self.assertNotIn('Confirm the EIN',value['comments'])
        self.assertEqual(self.lookup([self.row()],ein='271635830',name='Achieving the Dream')['status'],'Not Registered')

if __name__=='__main__':unittest.main(verbosity=2)
