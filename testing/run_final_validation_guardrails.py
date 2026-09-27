"""Regressions for query completion, blank filing data, and entity corroboration."""
import json, sys, time, unittest, urllib.error
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class Pennsylvania(unittest.TestCase):
    def setUp(self):
        self.org = c.checker.Organization('Example National Charity', '12-3456789')
    def rows(self, **kw):
        return [dict(EntityName='Example National Charity', PersonId=101, EIN=None, ExpDate=None,
                     StatusName=None, CertificateNumber=None, **kw)]
    def test_loaded_exact_name_blank_filing_is_delinquent(self):
        r=c.pa_completed_name_rows(self.org,self.rows(),'https://www.charities.pa.gov/')
        self.assertEqual(r.status,'Delinquent');self.assertTrue(r.success)
        self.assertEqual(r.reason_code,'PA_SAFE_NAME_MATCH_BLANK_FILING_DATA')
    def test_empty_search_is_not_blank_record(self):
        self.assertIsNone(c.pa_completed_name_rows(self.org,[],'https://www.charities.pa.gov/'))
    def test_different_ein_never_accepted(self):
        rows=self.rows();rows[0]['EIN']='98-7654321'
        self.assertIsNone(c.pa_completed_name_rows(self.org,rows,''))
    def test_unrelated_blank_record_never_delinquent(self):
        rows=self.rows();rows[0]['EntityName']='Another Community Organization'
        self.assertIsNone(c.pa_completed_name_rows(self.org,rows,''))
    def test_current_and_adverse_status(self):
        for raw,expected in [('APPROVED','Current'),('Revoked','Revoked'),('Exempt','Exempt')]:
            rows=self.rows();rows[0].update(StatusName=raw,ExpDate=(date.today()+timedelta(days=400)).isoformat())
            self.assertEqual(c.pa_completed_name_rows(self.org,rows,'').status,expected)
    def test_duplicate_current_record_beats_blank_old_record(self):
        rows=self.rows();rows.append(dict(rows[0],PersonId=102,StatusName='APPROVED',ExpDate=(date.today()+timedelta(days=400)).isoformat()))
        self.assertEqual(c.pa_completed_name_rows(self.org,rows,'').status,'Current')
    def test_contains_query_plan_removes_only_literal_coverage(self):
        self.org.organization_name='Beacon Harbor Research Society'
        with patch.object(c,'build_search_queries',return_value=['Beacon Harbor Research Society','Different Alias']),patch.object(c,'high_signal_search_phrases',return_value=[]):
            plan=c.pa_name_search_plan(self.org)
        self.assertIn('beacon harbor',plan)
        self.assertIn('Different Alias',plan)
        self.assertNotIn('Beacon Harbor Research Society',plan)
    def test_completed_response_path_and_failure_preserve_attempt(self):
        initial=c.checker.StateResult(self.org.organization_name,self.org.ein,'PA','Not Registered','')
        for payload in [{'Table':self.rows(),'Table1':[{'RESULTCOUNT':1}]},{'Table':self.rows(),'Table1':[{'RESULTCOUNT':2}]}]:
            with patch.object(c.checker,'search_pa',return_value=initial),patch.object(c,'pa_name_search_plan',return_value=['Example National']),patch.object(c,'identity_fetch',return_value=json.dumps(payload).encode()):
                r=c.search_pa_with_name_fallback_core(None,self.org,lambda value:value)
            if payload['Table1'][0]['RESULTCOUNT']==1:self.assertEqual(r.status,'Delinquent')
            else:
                self.assertFalse(r._pa_api_attempts[0]['complete'])
                guarded=c.pa_guard_search_completion(r,self.org,[dict(step='search',ein='123456789',complete=True,http_status=200,row_eins=[]),*r._pa_api_attempts])
                self.assertNotEqual(guarded.status,'Not Registered')

class TaxPeriod(unittest.TestCase):
    def setUp(self):c.TAX_PERIOD_EVIDENCE_CACHE.clear()
    def run_case(self,code=404,document=False):
        err=urllib.error.HTTPError('https://charity.ehawaii.gov/charity/123456789/details.html',code,'public response',{},None)
        def fetch(url,*a,**kw):
            if 'ehawaii' in url:
                if not document:raise err
                return b'loaded organization page'
            return b'no electronic returns'
        with patch.object(c,'irs_latest_period',return_value={}),patch.object(c,'identity_fetch',side_effect=fetch),patch.object(c,'hi_attachment_period',side_effect=err):
            return c.irs_period_for_label('123456789',2024,time.monotonic()+20)
    def test_missing_alternate_organization_page_is_absence(self):self.assertEqual(self.run_case(),{})
    def test_missing_linked_document_is_incomplete(self):
        r=self.run_case(document=True);self.assertTrue(r['period_unconfirmed']);self.assertIn('attachment: HTTP 404',r['period_read_failure'])
    def test_block_or_server_error_is_incomplete(self):
        for status in [403,429,500]:
            r=self.run_case(status);self.assertTrue(r['period_unconfirmed']);self.assertIn(str(status),r['period_read_failure'])

class ForeignIdentity(unittest.TestCase):
    def setUp(self):
        self.org=c.checker.Organization('Beacon Harbor University','12-3456789')
        self.row=dict(name='Beacon Harbor University Foundation',street='100 Main Street',region='VA',postal_code='12345',identifier='REG1',location='Example, VA')
        self.source=dict(name=self.row['name'],principaladdress='100 MAIN ST',principalstate='VA',principalzipcode='12345-6789',fein='98-7654321')
    def evidence(self,records):
        with patch.object(c,'identity_fetch',return_value=json.dumps(records).encode()):
            return c.licensed_charity_foreign_ein(self.org,self.row,time.monotonic()+10)
    def test_exact_full_name_street_region_zip_foreign_ein(self):self.assertEqual(self.evidence([self.source])['decision'],'different_ein')
    def test_partial_name_or_address_never_excludes(self):
        for key,value in [('name','Example National Foundation'),('principaladdress','101 Main St'),('principalstate','CA'),('principalzipcode','54321'),('fein','')]:
            self.assertEqual(self.evidence([{**self.source,key:value}]),{})
    def test_ambiguous_or_same_ein_never_excludes(self):
        self.assertEqual(self.evidence([{**self.source,'fein':'12-3456789'}]),{})
        self.assertEqual(self.evidence([self.source,{**self.source,'fein':'12-3456789'}]),{})
    def test_source_failure_retains_review(self):
        with patch.object(c,'identity_fetch',side_effect=TimeoutError()):
            self.assertEqual(c.licensed_charity_foreign_ein(self.org,self.row,time.monotonic()+10),{})
        self.assertEqual(self.row['foreign_ein_check']['outcome'],'unavailable')

class GeorgiaReview(unittest.TestCase):
    def test_full_name_match_without_address_retains_status_and_offers_review(self):
        org=c.checker.Organization('Example National Charity','12-3456789')
        rows=[dict(name=org.organization_name,identifier='CH101',status='Current',raw_status='Active',expiration=date.today()+timedelta(days=400),location='',license_category='Charity',url='https://verify.sos.ga.gov/')]
        with patch.object(c,'reconciled_registry_address',return_value={'decision':'unavailable'}):
            r=c.licensed_charity_result(org,'GA',rows,time.monotonic()+10,'https://verify.sos.ga.gov/')
        self.assertEqual(r.status,'Current');self.assertTrue(r._cc_identity_review['search_complete'])
        self.assertIn('no usable organization address',r.source_note)
        with patch.object(c,'APP_VERSION','2026.09.26.8-staging'),patch.object(c,'NY_CONNECTOR_SIGNING_KEY','test-only-'*8):
            data=dict(ein=org.ein,state='GA',comments=r.source_note)
            c.attach_identity_review(data,r._cc_identity_review)
        self.assertEqual(len(data['identity_review']['candidates']),1)

if __name__=='__main__':unittest.main(verbosity=2)
