"""Reported ME/MA/NY failures through final master responses, with controls."""
import json
import sys
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc


class Today(date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 12)


class ReportedCases(unittest.TestCase):
    def setUp(self):
        for p in (patch.object(cc, 'date', Today),
                  patch.object(cc.urllib.request, 'urlopen', side_effect=AssertionError('Unexpected network'))):
            p.start()
            self.addCleanup(p.stop)

    def ny(self, name, ein, rows, details):
        org = cc.checker.Organization(name, ein)
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        def get(url, *, params, timeout):
            data = rows if url.endswith('/RegistrySearch') else details[params['orgID']]
            response = Mock()
            response.json.return_value = {'success': True, 'statusCode': 200, 'data': data}
            return response
        session.get.side_effect = get
        with patch.object(cc.curl_requests, 'Session', return_value=session):
            result = cc.search_ny_direct(org)
            data = cc.response_data_for_lookup(result, '', org, name, ein, 'NY', time.perf_counter())
        return data, session

    def test_ny_exact_name_and_ein_outweigh_ein_only_duplicate_in_either_order(self):
        name = 'American Friends of Sheba Medical Center, Inc.'
        exact = {'orgID':'49-35-56', 'orgName':name, 'ein':'237076117'}
        other = {'orgID':'05-64-26', 'orgName':'American Friends of Sheba Medical Center - Tel Hashomer, Inc.', 'ein':'237076117'}
        details = {exact['orgID']:{**exact,'regType':'NFP','regStatute':'7A','documents':{
            'Annual Filing for Charitable Organizations':[{'fiscalYearEnd':'12/31/2023','received':'09/09/2025'}]}}}
        details[other['orgID']]={**other,'regType':'NFP','regStatute':'7A','documents':{
            'Annual Filing for Charitable Organizations':[{'fiscalYearEnd':'06/30/2025'}]}}
        for rows in ([other,exact],[exact,other]):
            with self.subTest(order=rows[0]['orgID']):
                data, session = self.ny(name,'23-7076117',rows,details)
                self.assertEqual(data['status'],'Delinquent')
                self.assertEqual(data['matched_registry_name'],name)
                self.assertEqual(data['computed_due_date'],'11/15/2025')
                self.assertTrue(data['source_url'].endswith('/49-35-56'))
                self.assertEqual(session.get.call_count,3)

    def test_ny_equal_identity_duplicates_remain_ambiguous(self):
        row={'orgID':'10-20-30','orgName':'Example Foundation','ein':'123456789'}
        other={**row,'orgID':'11-22-33'}
        data, session=self.ny(row['orgName'],row['ein'],[row,other],{row['orgID']:row,other['orgID']:other})
        self.assertEqual(data['status'],'Unable to Confirm')
        self.assertEqual(session.get.call_count,3)

    def test_ny_tel_hashomer_request_selects_its_own_record(self):
        exact={'orgID':'05-64-26','orgName':'American Friends of Sheba Medical Center - Tel Hashomer, Inc.','ein':'237076117'}
        other={**exact,'orgID':'49-35-56','orgName':'American Friends of Sheba Medical Center, Inc.'}
        detail={**exact,'regType':'NFP','regStatute':'7A','documents':{
            'Annual Filing for Charitable Organizations':[{'fiscalYearEnd':'06/30/2025'}]}}
        data,session=self.ny(exact['orgName'],exact['ein'],[other,exact],{exact['orgID']:detail,other['orgID']:{**detail,**other}})
        self.assertEqual(data['status'],'Current')
        self.assertEqual(session.get.call_args.kwargs['params'],{'orgID':'05-64-26'})

    def test_ny_empty_documents_cannot_override_detail_identity_failure(self):
        row={'orgID':'10-20-30','orgName':'Example Foundation','ein':'123456789'}
        detail={**row,'ein':'987654321','regType':'NFP','regStatute':'7A','documents':{}}
        data,_=self.ny(row['orgName'],row['ein'],[row],{row['orgID']:detail})
        self.assertEqual(data['status'],'Unable to Confirm')
        self.assertFalse(data.get('ny_filing_evidence'))

    def test_ny_confirmed_registration_only_history_survives_final_master_response(self):
        for name, ein, record_id in [('American Independent Media','814770680','50-67-10'),
                                     ('American Statistical Association','530204661','51-32-84')]:
            with self.subTest(name=name):
                row={'orgID':record_id,'orgName':name,'ein':ein}
                detail={**row,'regType':'NFP','regStatute':'7A','documents':{'Registration Documents':[{'title':'Certificate of Incorporation'}]}}
                data,_=self.ny(name,ein,[row],{record_id:detail})
                self.assertEqual(data['status'],'Delinquent')
                self.assertTrue(data['ny_filing_evidence']['empty_history_confirmed'])
                self.assertIn('infers Delinquent',data['comments'])
                self.assertIn('not an explicit state',data['comments'])
                self.assertFalse(data.get('computed_due_date'))

    def test_ny_unknown_document_category_is_not_confirmed_empty_history(self):
        row={'orgID':'10-20-30','orgName':'Example Foundation','ein':'123456789'}
        detail={**row,'regType':'NFP','regStatute':'7A','documents':{'Changed annual report format':[{}]}}
        data,_=self.ny(row['orgName'],row['ein'],[row],{row['orgID']:detail})
        self.assertEqual(data['status'],'Unable to Confirm')
        self.assertNotEqual(data.get('status_reason'),'FILING_HISTORY_UNAVAILABLE_NO_CONFIRMED_DEADLINE')

    def test_ny_unproven_empty_text_does_not_gain_inference(self):
        org=cc.checker.Organization('Example Foundation','123456789')
        r=cc.checker.StateResult(org.organization_name,org.ein,'NY','Delinquent','https://example.org')
        r.matched_registry_name=org.organization_name
        r.raw_status_text='No filings found'
        r.success=True
        self.assertEqual(cc.true_status_from_body(r,''),'Unable to Confirm')

    def test_ny_explicit_exempt_registration_without_annuals_stays_exempt(self):
        row={'orgID':'10-20-30','orgName':'Example Foundation','ein':'123456789'}
        detail={**row,'regType':'NFP','regStatute':'EXEMPT','documents':{}}
        data,_=self.ny(row['orgName'],row['ein'],[row],{row['orgID']:detail})
        self.assertEqual(data['status'],'Exempt')

    def ma_evidence(self, rows, status='', completed=True, visible_status=''):
        org=cc.checker.Organization('American Independent Media','814770680')
        evidence={'record':{'record_id':'record1','ago_account':'084259','ein':'814770680',
                            'name':org.organization_name,'registry_status':status}}
        response=Mock(url='https://masscharities.my.site.com/FilingSearch/s/sfsites/aura')
        response.request.post_data=urlencode({'message':json.dumps({'actions':[{'id':'1','params':{
            'classname':'AeS_Apex_Controller_Class','method':'get_ALL_FILINGS_ATTACHMENTS_FOR_PUBLICUSERS',
            'params':{'agoNumber':'084259'}}}]})})
        response.json.return_value={'actions':[{'id':'1','state':'SUCCESS' if completed else 'ERROR',
                                               'returnValue':{'returnValue':rows}}]}
        cc.ma_capture_completed_response(response,org,evidence)
        page=Mock()
        page.locator.return_value.inner_text.return_value='AG Account Number 084259'+(' Charity Status: '+visible_status if visible_status else '')
        page.get_by_role.return_value.all_inner_texts.return_value=[]
        r=cc.checker.StateResult(org.organization_name,org.ein,'MA','Unknown','https://masscharities.my.site.com/FilingSearch/s/')
        r.matched_registry_name=org.organization_name
        r.matched_registry_identifier='084259'
        r.success=True
        parsed=cc.ma_read_latest_form_pc(page,r,'AG Account Number 084259',evidence)
        r=cc.annotate_ma_visible_form_pc_due(r,parsed)
        return cc.response_data_for_lookup(r,'',org,org.organization_name,org.ein,'MA',time.perf_counter())

    def schedule(self):
        return {'filingYear':'2025','nameforURL':'Schedule-A2 Data','nameforButton':'View Filing Schedule-A2 Data',
                'url':'https://masscharities.my.site.com/FilingSearch/s/detail/a0IRm00000i1n8bMAA'}

    def test_ma_completed_schedule_only_is_not_a_form_pc_or_a_fiscal_year(self):
        data=self.ma_evidence([self.schedule()])
        self.assertEqual(data['status'],'Delinquent')
        self.assertIn('Schedule A2',data['comments'])
        self.assertIn('infers Delinquent',data['comments'])
        self.assertFalse(data.get('computed_due_date'))
        self.assertFalse(data.get('fiscal_year_end'))

    def test_ma_pending_unknown_or_unreadable_annual_evidence_stays_inconclusive(self):
        for rows, completed in [([self.schedule()],False),([{'nameforURL':'New document format'}],True),
                ([self.schedule(),{'nameforURL':'Form-PC Data','filingYear':'2025'}],True),
                ([self.schedule(),{'nameforURL':'FY2025 PC - Form PC/Annual RPT.pdf','filingYear':'2025'}],True)]:
            with self.subTest(rows=rows,completed=completed):
                self.assertEqual(self.ma_evidence(rows,completed=completed)['status'],'Unable to Confirm')

    def test_ma_primary_pending_and_noncontrolling_activity_with_schedule_only(self):
        self.assertEqual(self.ma_evidence([self.schedule()],status='Not Doing Business in Mass')['status'],
                         'Delinquent')
        self.assertEqual(self.ma_evidence([self.schedule()],status='Pending')['status'],'Delinquent')
        self.assertEqual(self.ma_evidence([self.schedule()],status='Pending',visible_status='Pending')['status'],'Pending')

    def test_me_truncated_registry_name_is_discoverable_without_relaxing_identity(self):
        name='American Institute for Chartered Property Casualty Underwriters'
        org=cc.checker.Organization(name,'231352012')
        stored='AMERICAN INSTITUTE FOR CHARTERED PROPERTY CASUALTY UNDERWRIT'
        queries=cc.me_fast_direct_query_variants(org)
        self.assertLessEqual(len(queries),cc.ME_FAST_DIRECT_CONFIRMATION_MAX_VARIANTS)
        self.assertTrue(any(stored.casefold().startswith(q.casefold()) for q in queries),queries)
        self.assertTrue(cc.registry_name_is_safe_for_org(stored,name,org.ein))
        self.assertFalse(cc.registry_name_is_safe_for_org('American Institute for Cancer Research',name,org.ein))

    def test_me_short_working_punctuation_queries_remain_available(self):
        queries=cc.me_fast_direct_query_variants(cc.checker.Organization('Young Life','840385934'))
        for expected in ('Young Life','Young-Life','The Young Life'):
            self.assertIn(expected,queries)

    def test_me_prefix_does_not_displace_existing_alias_at_query_limit(self):
        org=cc.checker.Organization('American Institute for Chartered Property Casualty Underwriters','231352012')
        aliases=['First Alias Foundation','Second Alias Foundation','Third Alias Foundation',
                 'Fourth Alias Foundation','Fifth Alias Foundation']
        with patch.object(cc,'known_names_for_ein',return_value=aliases), \
             patch.object(cc,'compatible_ein_alias_for_name',return_value=True), \
             patch.object(cc,'organization_name_variants',return_value=[]):
            self.assertEqual(cc.me_fast_direct_query_variants(org),[org.organization_name]+aliases)


if __name__=='__main__':
    unittest.main()
