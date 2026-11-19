"""70 recorded identities with synthetic fresh-source/account conditions.

Offline transport/ownership contracts, not 70 independent live adjudications.
"""
import copy,json,unittest
from pathlib import Path
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
from deployment import tn_extensions_demo as t,tn_extension_refresh as f
from testing.test_tn_extensions_demo import Accounts,ACCOUNT,OTHER,NOW,Handler

CASES=[]
def result(identifier='680412350',name='Foundation for California Community Colleges',co='CO50328'):
    return dict(ein=identifier,organization_name=name,state='TN',success=True,status='Upcoming Filing',source_url=t.SOURCE,
        matched_registry_name=name,matched_registry_identifier=co,raw_status_text='Active',computed_due_date='2026-12-31',
        renewal_filing_type='filed_period_end',renewal_filing_value='2025-06-30')

class Fresh(unittest.TestCase):
    def setUp(self):
        self.a=Accounts();del self.a.extension_reference_provider;self.c=self.a.c;self.s=t.Service(self.a);self.addCleanup(self.c.db.close)
    def start(self,identifier='680412350',name='Foundation for California Community Colleges'):
        return self.s.dispatch(self.c,ACCOUNT,dict(action='begin-check',ein=identifier,name=name),NOW)
    def complete(self,r=None,now=NOW):
        r=r or result();b=self.start(r['ein'],r['organization_name']);f.complete(self.s,self.c,ACCOUNT,r['ein'],b['nonce'],r,now);return b
    def status(self,identifier='680412350',now=NOW):return self.s.dispatch(self.c,ACCOUNT,dict(action='status',ein=identifier),now)
    def test_no_static_reference_fallback_before_check_or_on_failure(self):
        self.assertFalse(self.status()['eligibility']['eligible']);b=self.complete()
        self.s.dispatch(self.c,ACCOUNT,dict(action='confirm-prior',ein=b['ein'],answer='no'),NOW)
        self.assertTrue(self.status()['eligibility']['eligible'])
        self.s.dispatch(self.c,ACCOUNT,dict(action='refresh-failed',ein=b['ein'],nonce=b['nonce']),NOW)
        self.assertFalse(self.status()['eligibility']['eligible'])
    def test_70_distinct_recorded_inputs_and_mixed_guard_conditions(self):
        CASES.clear();inputs=json.loads(Path('testing/fixtures/gate53/LOCAL-70.json').read_text(encoding='utf-8'))
        inputs=[dict(ein='680412350',name='Foundation for California Community Colleges'),dict(ein='521273585',name='Global Impact')]+[x for x in inputs if x['ein'] not in {'680412350','521273585'}]
        for i,org in enumerate(inputs[:70]):
            self.setUp();r=result(org['ein'],org['name'],'CO'+str(50000+i));mode=i%10
            if mode==1:r['raw_status_text']='Expired';r['status']='Delinquent'
            if mode==2:r['ein']='999999999'
            if mode==3:r['computed_due_date']=''
            if mode==4:r['renewal_filing_type']='current_issue_date'
            if mode==5:r['confirmation_required']=True
            if mode==6:r['success']=False;r['status']='Site Not Reachable'
            if mode==7:r['matched_registry_identifier']='OTHER'
            b=self.start(org['ein'],org['name'])
            if mode in [2,5,6,7]:
                with self.assertRaises(t.Invalid):f.complete(self.s,self.c,ACCOUNT,org['ein'],b['nonce'],r,NOW)
                observed=self.status(org['ein']);self.assertFalse(observed['eligibility']['eligible'])
            else:
                fresh=f.complete(self.s,self.c,ACCOUNT,org['ein'],b['nonce'],r,NOW)
                if mode not in [1,3,4]:self.s.dispatch(self.c,ACCOUNT,dict(action='confirm-prior',ein=org['ein'],answer='no'),NOW)
                observed=self.status(org['ein'],NOW+301 if mode==8 else NOW)
                self.assertEqual(observed['eligibility']['eligible'],mode in [0,9])
                self.assertEqual(fresh['checked_at'],t.local_day(NOW).isoformat());self.assertEqual(fresh['checked_at_epoch'],NOW)
            CASES.append(dict(ein=org['ein'],name=org['name'],mode=mode,passed=True,eligible=observed['eligibility']['eligible'],conditions='Offline recorded identity; constructed fresh connector result and account state'))
        self.assertEqual(len({x['ein'] for x in CASES}),70)
    def test_scope_nonce_replacement_and_owner_isolation(self):
        old=self.start();new=self.start()
        for owner,nonce,identifier in [(ACCOUNT,old['nonce'],new['ein']),(OTHER,new['nonce'],new['ein']),(ACCOUNT,new['nonce'],'521273585')]:
            with self.assertRaises(t.Invalid):f.complete(self.s,self.c,owner,identifier,nonce,result(),NOW)
    def test_pending_new_check_invalidates_previous_positive_and_declaration(self):
        b=self.complete();self.s.dispatch(self.c,ACCOUNT,dict(action='confirm-prior',ein=b['ein'],answer='no'),NOW)
        self.assertTrue(self.status()['eligibility']['eligible']);self.start();self.assertFalse(self.status()['eligibility']['eligible'])
    def test_returned_record_requires_explicit_period_review(self):
        b=self.complete();p=dict(action='account-observation',ein=b['ein'],nonce=b['nonce'],observation=dict(state='checked',records=[dict(tracking='9000001234',coid='CO50328',description='First Extension Request',type='Extension Request',status='Rejected',updated='Test timestamp',source='https://tncab.tnsos.gov/portal/my-filings',identity_method='co_number')]))
        self.s.dispatch(self.c,ACCOUNT,p,NOW)
        with self.assertRaises(t.Invalid):self.s.dispatch(self.c,ACCOUNT,dict(action='confirm-prior',ein=b['ein'],answer='no'),NOW)
        yes=self.s.dispatch(self.c,ACCOUNT,dict(action='confirm-prior',ein=b['ein'],answer='yes'),NOW);self.assertFalse(yes['eligibility']['eligible'])
        other=self.s.dispatch(self.c,ACCOUNT,dict(action='confirm-prior',ein=b['ein'],answer='no',records_not_for_period=True),NOW);self.assertTrue(other['eligibility']['eligible'])
        self.s.dispatch(self.c,ACCOUNT,p,NOW+1);self.assertFalse(self.status()['eligibility']['eligible'])
    def test_unavailable_account_is_not_a_negative_search(self):
        b=self.complete()
        for state in ['sign_in_required','partial','unavailable','busy']:
            d=self.s.dispatch(self.c,ACCOUNT,dict(action='account-observation',ein=b['ein'],nonce=b['nonce'],observation={'state':state,'records':[]}),NOW)
            self.assertEqual(d['facts']['account_check']['state'],state);self.assertIsNone(d['facts']['existing_filing'])
    def test_unsent_draft_is_visible_but_is_not_a_submitted_extension(self):
        b=self.complete();record=dict(tracking='9000001234',coid='CO50328',description='Renewal draft',type='Charity Renewal Registration',status='Incomplete',updated='Test',source='https://tncab.tnsos.gov/portal/my-filings',identity_method='co_number')
        d=self.s.dispatch(self.c,ACCOUNT,dict(action='account-observation',ein=b['ein'],nonce=b['nonce'],observation={'state':'checked','records':[record]}),NOW)
        self.assertFalse(d['facts']['account_check']['requires_period_review']);self.assertEqual(len(d['facts']['account_check']['records']),1)
        ready=self.s.dispatch(self.c,ACCOUNT,dict(action='confirm-prior',ein=b['ein'],answer='no'),NOW);self.assertTrue(ready['eligibility']['eligible'])
    def test_account_observation_rejects_other_co_names_sources_and_owner(self):
        b=self.complete();good=dict(tracking='9000001234',coid='CO50328',description='First Extension Request',type='Extension Request',status='Rejected',updated='Test',source='https://tncab.tnsos.gov/portal/my-filings',identity_method='co_number')
        for change in [dict(coid='CO1'),dict(source='https://example.com/'),dict(coid='',identity_method='exact_name',description='Unrelated Charity')]:
            with self.assertRaises(t.Invalid):f.account_observation(self.s,self.c,ACCOUNT,dict(ein=b['ein'],nonce=b['nonce'],observation={'state':'checked','records':[good|change]}),NOW)
    def test_fresh_changed_deadline_blocks_old_draft_and_reuses_unchanged_draft(self):
        b=self.complete();self.s.dispatch(self.c,ACCOUNT,dict(action='confirm-prior',ein=b['ein'],answer='no'),NOW)
        r=self.s.dispatch(self.c,ACCOUNT,dict(action='prepare',ein=b['ein']),NOW)
        b=self.complete();self.s.dispatch(self.c,ACCOUNT,dict(action='confirm-prior',ein=b['ein'],answer='no'),NOW)
        again=self.s.dispatch(self.c,ACCOUNT,dict(action='prepare',ein=b['ein']),NOW);self.assertEqual(again['id'],r['id']);self.assertEqual(again['documents'],r['documents'])
        changed=result();changed['computed_due_date']='2027-01-31';f.complete(self.s,self.c,ACCOUNT,b['ein'],b['nonce'],changed,NOW)
        with self.assertRaises(t.Invalid):self.s.submit(self.c,ACCOUNT,self.s.load(self.c,ACCOUNT,r['id']),dict(fields={'coid':'CO50328'},prior_filing='no',reviewed=True,authorized=True),NOW)
    def test_confirmed_not_registered_has_clear_ineligibility_reason(self):
        r=result();r.update(status='Not Registered',matched_registry_name='',matched_registry_identifier='')
        self.complete(r);self.assertIn('no qualifying registration',self.status()['eligibility']['reasons'][0])
    def test_read_only_transport_whitelists_tn_and_binds_server_output(self):
        b=self.start();called=[]
        master=SimpleNamespace(normalize_email=lambda s:s,ny_connector_unpack=lambda *args:{'state':'TN','ein':b['ein']},
            final_four_connector_request=lambda p,o:(called.append(p) or (200,{'phase':'complete','result':result()})))
        p=dict(action='start',state='TN',ein=b['ein'],organization_name=b['name'],extension_ein=b['ein'],extension_refresh=b['nonce'],email=ACCOUNT)
        with patch.object(f.time,'time',return_value=NOW):
            status=f.handle_source(self.a,master,Handler(p),origin='https://staging.example')[0]
        self.assertEqual(status,200);self.assertEqual(len(called),1)
        for change in [dict(state='GA'),dict(extension_refresh='bad'),dict(ein='521273585')]:
            with patch.object(f.time,'time',return_value=NOW):self.assertEqual(f.handle_source(self.a,master,Handler(p|change),origin='https://staging.example')[0],400)
        self.assertEqual(len(called),1)

if __name__=='__main__':unittest.main()
