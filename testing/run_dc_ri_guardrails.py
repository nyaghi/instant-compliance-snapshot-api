"""DC/RI integration controls: identity, source completeness, dates, mature parity."""
import ast, copy, json, subprocess, sys, time, unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import registry_snapshot_server as cc
import charity_clarity_report as report

def row(name='Beacon Learning Foundation', identifier='CO.123', status='Current', days=365, **extra):
    return dict(name=name,identifier=identifier,status=status,raw_status='ACTIVE',expiration=date.today()+timedelta(days=days),location='Boston, MA',**extra)

class LicenseControls(unittest.TestCase):
    def setUp(self):
        self.org=cc.checker.Organization('Beacon Learning Foundation','123456789')
        self.deadline=time.monotonic()+40
        self.address=patch.object(cc,'reconciled_registry_address',return_value={'decision':'corroborated','basis':'EIN-linked office agrees.'})
        self.address.start();self.addCleanup(self.address.stop)
    def select(self,rows):return cc.select_licensed_charity(self.org,rows,'RI',self.deadline)
    def test_adverse_status_overrides_future_expiration(self):
        for raw,status in [('INACTIVE','Closed / Withdrawn / Canceled'),('Revoked','Revoked'),('Suspended','Suspended'),('Expired - Enforcement','Delinquent')]:
            self.assertEqual(cc.licensed_charity_status(raw,date.today()+timedelta(days=365)),status)
    def test_calendar_windows_and_pending(self):
        for days,status in [(-1,'Delinquent'),(0,'Upcoming Filing'),(60,'Upcoming Filing'),(365,'Current')]:
            self.assertEqual(cc.licensed_charity_status('ACTIVE',date.today()+timedelta(days=days)),status)
            self.assertEqual(cc.licensed_charity_status('ACTIVE PENDING RENEWAL',date.today()+timedelta(days=days)),'Pending')
        self.assertEqual(cc.licensed_charity_status('PENDING',None),'Pending')
        self.assertEqual(cc.licensed_charity_status('Unrecognized',None),'Unable to Confirm')
    def test_original_and_reviewed_names_before_generated(self):
        token=cc.REVIEWED_NAME_CONTEXT.set({'123456789':['Former Education Society','Beacon Learning']})
        try:
            required,generated=cc.licensed_charity_names(self.org)
            self.assertEqual(required,['Beacon Learning Foundation','Former Education Society','Beacon Learning'])
            self.assertFalse(set(required)&set(generated))
        finally:cc.REVIEWED_NAME_CONTEXT.reset(token)
    def test_generated_phrases_bounded_and_deadline_preserved(self):
        required,generated=cc.licensed_charity_names(self.org)
        self.assertLessEqual(len(generated),3*len(required))
        self.assertTrue(all(cc.distinctive_match_tokens(name) for name in generated))
        with self.assertRaises(TimeoutError):cc.select_licensed_charity(self.org,[row()],'RI',time.monotonic()-1)
    def test_chapter_rejected_even_if_listed_first(self):
        selected,review=self.select([row('Beacon Learning Foundation - Milwaukee'),row()])
        self.assertEqual(selected['name'],self.org.organization_name);self.assertFalse(review)
    def test_other_ein_rejected_even_same_name_and_address(self):
        selected,review=self.select([row(ein='987654321')]);self.assertIsNone(selected);self.assertFalse(review)
    def test_old_closed_primary_does_not_hide_active_verified_alias(self):
        token=cc.REVIEWED_NAME_CONTEXT.set({'123456789':['Former Education Society']})
        try:
            selected,_=self.select([row(status='Closed / Withdrawn / Canceled'),row('Former Education Society','CO.456')])
            self.assertEqual(selected['identifier'],'CO.456')
        finally:cc.REVIEWED_NAME_CONTEXT.reset(token)
    def test_two_live_same_entity_choose_latest_period(self):
        selected,_=self.select([row(days=60,identifier='CO.OLD'),row(days=365,identifier='CO.NEW')])
        self.assertEqual(selected['identifier'],'CO.NEW')
    def test_tied_conflicting_statuses_need_review(self):
        selected,review=self.select([row(),row(identifier='CO.OTHER',status='Suspended')])
        self.assertIsNone(selected);self.assertIn('conflicting statuses',review)
    def test_both_inactive_are_closed(self):
        rows=[row(identifier=str(i),status='Closed / Withdrawn / Canceled') for i in range(2)]
        result=cc.licensed_charity_result(self.org,'DC',rows,self.deadline,'https://example.org')
        self.assertEqual(result.status,'Closed / Withdrawn / Canceled')
    def test_address_conflict_is_not_negative(self):
        with patch.object(cc,'reconciled_registry_address',return_value={'decision':'conflict','ein_linked_location':'Madison, WI'}):
            result=cc.licensed_charity_result(self.org,'RI',[row()],self.deadline,'https://example.org')
        self.assertEqual(result.status,'Needs Review');self.assertIn('Madison, WI',result.source_note)
    def test_unavailable_address_does_not_create_conflict(self):
        with patch.object(cc,'reconciled_registry_address',return_value={'decision':'unavailable'}):
            selected,review=self.select([row()])
        self.assertIsNotNone(selected);self.assertFalse(review)
    def test_complete_negative(self):
        result=cc.licensed_charity_result(self.org,'RI',[],self.deadline,'https://example.org')
        self.assertTrue(result.success);self.assertEqual(result.status,'Not Registered')
    def test_reversed_name_is_not_an_address_conflict(self):
        self.org=cc.checker.Organization('Focus on the Family','953188150')
        selected,review=self.select([row('Family Focus')])
        self.assertIsNone(selected);self.assertFalse(review)
    def test_different_city_exact_street_region_zip_is_corroborated(self):
        r=row(street='3160 Francis RD',region='GA',postal_code='30004')
        evidence={'organization_records':[{'ein':'123456789','address_role':'organization','street':'3160 FRANCIS ROAD','state':'GA','city':'Another City','postal_code':'30004-1234','names':['Beacon Learning Foundation'],'source_url':'https://state.example/record'}]}
        with patch.object(cc,'identity_source_result',return_value=evidence):
            result=cc.licensed_charity_street_evidence(self.org,r,self.deadline)
            self.assertEqual(result['decision'],'corroborated')
            for key,value in [('ein','987654321'),('address_role','agent'),('street','3161 Francis Road'),('postal_code','30005'),('state','FL')]:
                changed=copy.deepcopy(evidence);changed['organization_records'][0][key]=value
                with patch.object(cc,'identity_source_result',return_value=changed):self.assertEqual(cc.licensed_charity_street_evidence(self.org,r,self.deadline),{})
    def test_primary_trailing_article_beats_uncorroborated_campaign_alias(self):
        token=cc.REVIEWED_NAME_CONTEXT.set({'123456789':['Other Campaign']})
        try:
            with patch.object(cc,'reconciled_registry_address',return_value={'decision':'unavailable'}):
                selected,_=self.select([row('Beacon Learning Foundation, The',status='Delinquent',days=-5),row('Other Campaign')])
            self.assertEqual(selected['name'],'Beacon Learning Foundation, The')
        finally:cc.REVIEWED_NAME_CONTEXT.reset(token)
    def test_confirmed_current_alias_beats_expired_exact_primary(self):
        token=cc.REVIEWED_NAME_CONTEXT.set({'123456789':['Former Education Society']})
        try:
            selected,_=self.select([row(status='Delinquent',days=-30),row('Former Education Society','CO.NEW')])
            self.assertEqual(selected['identifier'],'CO.NEW')
        finally:cc.REVIEWED_NAME_CONTEXT.reset(token)
    def test_dc_trade_name_can_identify_legacy_row_without_entity_name(self):
        data={'features':[{'attributes':{'OBJECTID':1,'CUSTOMERNUMBER':'123','ENTITYNAME':None,'ENTITYTRADENAME':'Beacon Learning Foundation','BUSINESSACTIVITY':'Charitable Solicitation','DATAREFRESHEDON':int(time.time()*1000),'LICENSESTATUS':'Active'}}]}
        with patch.object(cc,'registry_json_request',return_value=data):rows,_=cc.dc_charity_records(self.org,self.deadline)
        self.assertEqual(rows[0]['name'],'Beacon Learning Foundation')
    def test_failed_source_is_never_negative(self):
        for state,method in [('DC','dc_charity_records'),('RI','registry_json_request')]:
            with patch.object(cc,method,side_effect=TimeoutError('source timed out')),patch.object(cc,'log_error'):
                result=(cc.search_dc if state=='DC' else cc.search_ri)(self.org)
            self.assertEqual(result.status,'Unable to Confirm');self.assertFalse(result.success)
    def test_ri_generated_query_continues_after_only_rejected_rows(self):
        candidate={'id':'C1','title':'Beacon Learning Foundation'}
        with patch.object(cc,'registry_json_request',return_value={'access_token':'public-test-token'}),patch.object(cc,'licensed_charity_names',return_value=(['Original'],['Fallback'])),patch.object(cc,'ri_charity_search',side_effect=[[candidate],[]]) as search,patch.object(cc,'ri_charity_detail',return_value=row(ein='987654321')):
            result=cc.search_ri(self.org)
        self.assertEqual(search.call_count,2);self.assertEqual(result.status,'Not Registered')
    def test_pending_comment_does_not_assert_late_renewal(self):
        pending=row(status='Pending',days=-30);pending['raw_status']='ACTIVE PENDING RENEWAL'
        result=cc.licensed_charity_result(self.org,'RI',[pending],self.deadline,'https://example.org')
        self.assertIn('expiration alone does not establish delinquency',result.source_note)
    def test_dc_error_payload_is_not_completed_negative(self):
        with patch.object(cc,'registry_json_request',return_value={'error':{'message':'Invalid field'}}):
            with self.assertRaises(ValueError):cc.dc_charity_records(self.org,self.deadline)
    def test_dc_truncated_repeated_page_fails(self):
        page={'features':[{'attributes':{'OBJECTID':1,'ENTITYNAME':'Beacon'}}],'exceededTransferLimit':True}
        with patch.object(cc,'registry_json_request',return_value=page):
            with self.assertRaisesRegex(ValueError,'repeated'):cc.dc_charity_records(self.org,self.deadline)
    def test_dc_empty_requires_fresh_source(self):
        with patch.object(cc,'registry_json_request',side_effect=[{'features':[]},{'features':[]} ]):
            with self.assertRaisesRegex(ValueError,'freshness'):cc.dc_charity_records(self.org,self.deadline)
    def test_dc_no_match_refresh_probe(self):
        epoch=int(time.time()*1000)
        with patch.object(cc,'registry_json_request',side_effect=[{'features':[]},{'features':[{'attributes':{'DATAREFRESHEDON':epoch}}]}]):
            rows,note=cc.dc_charity_records(self.org,self.deadline)
        self.assertEqual(rows,[]);self.assertIn('Data freshness',note)
    def test_ri_pagination_complete(self):
        batches=[{'results':[{'id':'C1','title':'One'}],'resultCount':2},{'results':[{'id':'C2','title':'Two'}],'resultCount':2}]
        with patch.object(cc,'registry_json_request',side_effect=batches) as fetch:
            rows=cc.ri_charity_search('Beacon',self.deadline,{})
        self.assertEqual(len(rows),2);self.assertEqual(fetch.call_args.kwargs['payload']['start'],1)
        self.assertEqual(fetch.call_args.kwargs['payload']['formRequest']['values']['licenseType'],'Charitable Organization')
        self.assertEqual(fetch.call_args.kwargs['payload']['formRequest']['values']['organizationName'],'Beacon')
    def test_ri_missing_count_and_truncation_fail(self):
        for data in [{'results':[]},{'results':[],'resultCount':2},{'results':[],'resultCount':0,'message':{'errors':['Failed']}}]:
            with patch.object(cc,'registry_json_request',return_value=data):
                with self.assertRaises(ValueError):cc.ri_charity_search('Beacon',self.deadline,{})
    def ri_detail(self,expiry=None):
        values=[{'label':'Credential','value':['CO.123','Charitable Organization']},{'label':'Status','value':['ACTIVE']},
                {'label':'Expiration Date','value':[expiry or (date.today()+timedelta(days=60)).strftime('%m/%d/%Y')]}]
        return {'id':'C1','name':'Details for Beacon Learning Foundation','tiles':[{'steps':[{'name':'Summary','contents':[{'data':values}]},
            {'name':'Relationships','contents':[{'data':[{'label':'Initial Registration Date','value':['01/01/2000']}]}]}]}]}
    def test_ri_future_expiration_parsed_and_relationship_dates_ignored(self):
        with patch.object(cc,'registry_json_request',return_value=self.ri_detail()):
            r=cc.ri_charity_detail({'id':'C1','title':self.org.organization_name},self.deadline,{})
        self.assertEqual(r['status'],'Upcoming Filing');self.assertNotIn('initial',r)
    def test_ri_detail_id_must_match(self):
        d=self.ri_detail();d['id']='C2'
        with patch.object(cc,'registry_json_request',return_value=d):
            with self.assertRaises(ValueError):cc.ri_charity_detail({'id':'C1','title':self.org.organization_name},self.deadline,{})
    def test_ri_bad_date_cannot_become_current(self):
        with patch.object(cc,'registry_json_request',return_value=self.ri_detail('not a date')):
            with self.assertRaises(ValueError):cc.ri_charity_detail({'id':'C1','title':self.org.organization_name},self.deadline,{})
    def test_selected_dates_only_and_labels_retained(self):
        result=cc.licensed_charity_result(self.org,'DC',[row(initial=date(2010,1,1),initial_label='Initial Issue Date',renewal=date(2025,1,1),renewal_label='License Start Date',renewal_type='current_effective_date')],self.deadline,'https://example.org')
        before=copy.deepcopy(vars(result));meta=cc.registration_date_metadata(result)
        self.assertEqual(meta['registration_date'],'2010-01-01');self.assertEqual(meta['renewal_date'],'2025-01-01')
        self.assertEqual(cc.renewal_filing_metadata(result,meta)['renewal_filing_label'],'Current period effective')
        self.assertEqual(vars(result),before)
        result.matched_registry_identifier='another';self.assertFalse(cc.registration_date_metadata(result)['registration_date'])
    def test_inconclusive_never_exposes_dates(self):
        result=cc.licensed_charity_result(self.org,'RI',[row(initial=date(2010,1,1),initial_label='Initial Registration Date')],self.deadline,'https://example.org')
        for status in ['Needs Review','Unable to Confirm','Not Registered']:
            self.assertFalse(cc.registration_date_metadata(result,status)['registration_date'])
    def test_pipeline_keeps_status_and_source_note(self):
        result=cc.licensed_charity_result(self.org,'DC',[row()],self.deadline,'https://example.org',freshness='Data freshness: checked today.')
        with patch.object(cc,'filing_context',side_effect=AssertionError('new state must not infer a tax period')):
            data=cc.response_data_for_lookup(result,result.raw_status_text,self.org,self.org.organization_name,self.org.ein,'DC',time.perf_counter())
        self.assertEqual(data['status'],'Current');self.assertIn('Data freshness:',data['comments'])

class MatureParity(unittest.TestCase):
    def previous(self,path):return subprocess.check_output(['git','show','6c3504f:'+path],cwd=ROOT).decode('utf-8')
    def test_existing_functions_unchanged_except_scoped_entry_points(self):
        old={n.name:ast.dump(n) for n in ast.parse(self.previous('registry_snapshot_server.py')).body if isinstance(n,ast.FunctionDef)}
        current={n.name:ast.dump(n) for n in ast.parse((ROOT/'registry_snapshot_server.py').read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef)}
        allowed={'registration_date_metadata','true_status_from_body','comments_for_result_base','run_state_lookup'}
        self.assertEqual({k for k,v in old.items() if current.get(k)!=v},allowed)
    def test_discovery_connector_and_state_modules_unchanged(self):
        for path in ['Charity_Checker_Script for 13_states.py','web-staging/organization-identity.js','web-staging/ny-connector.js']:
            self.assertEqual((ROOT/path).read_text(encoding='utf-8').replace('\r\n','\n'),self.previous(path).replace('\r\n','\n'))
    def test_frontend_concurrency_unchanged(self):
        start='    async function runStateChecks('
        def body(s):return s[s.index(start):].split('\n    stateCheckboxes.forEach')[0]
        self.assertEqual(body(self.previous('web-staging/index.html')),body((ROOT/'web-staging/index.html').read_text(encoding='utf-8')))
    def test_old_lane_indices_preserved_and_ui_has_32(self):
        tree=ast.parse(self.previous('registry_snapshot_server.py'))
        states=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SUPPORTED_STATES' for t in n.targets))
        self.assertEqual(cc.SUPPORTED_STATES[:30],states)
        self.assertEqual(len(cc.SUPPORTED_STATES),32)
        import re
        ui=(ROOT/'web-staging/index.html').read_text(encoding='utf-8')
        self.assertEqual(set(re.findall(r'name="states" value="([A-Z]{2})"',ui)),set(cc.SUPPORTED_STATES))
    def test_report_accepts_32_unique_results(self):
        rows=[{'state':s,'organization_name':'Control','ein':'123456789','status':'Current'} for s in cc.SUPPORTED_STATES]
        self.assertEqual(len(report.validate_results({'results':rows},set(cc.SUPPORTED_STATES))),32)
        with self.assertRaises(ValueError):report.validate_results({'results':rows+[rows[0]]},set(cc.SUPPORTED_STATES))

if __name__=='__main__':unittest.main()
