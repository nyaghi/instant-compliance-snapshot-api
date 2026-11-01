"""Bounded signed NC retrieval recovery; all source responses are local models."""
import copy,json,time,unittest
from pathlib import Path
from unittest.mock import patch
import registry_snapshot_server as c
from testing import run_final_four_continuation_guardrails as signed
from testing.run_final_four_source_guardrails import NC,NC_PROFILE
ROOT=Path(__file__).resolve().parents[1]
REASON='NY_CONNECTOR_REGISTRY_NC_RESULT_COUNT_MISMATCH'

class SpecificFallback(unittest.TestCase):
    def setUp(self):
        self.t=signed.ContinuationControls('test_all_four_complete_through_signed_master_replay')
        self.t.setUp();self.addCleanup(self.t.doCleanups)
        self.plans=[]
    def start(self,state='NC',**kwargs):
        return self.t.start(state,recovery_protocol='nc-fresh-search-v1',**kwargs)
    def plan(self,required,generated,probes,primary):
        self.plans.append(primary)
        return [required[0]],{},{required[0]:'BREAST CANCER'},[]
    def source_fail(self,res,**kw):
        return self.t.request({'action':'fail','check_token':res['check_token'],
            'query_id':res['query_id'],'reason':REASON,**kw})
    def unpack(self,res):
        return c.ny_connector_unpack(res['check_token'],self.t.auth['email'],self.t.auth['device_id'])
    def contexts(self,name,aliases=()):
        from contextlib import ExitStack
        stack=ExitStack()
        stack.enter_context(patch.object(c,'licensed_charity_names',return_value=([name,*aliases],[])))
        stack.enter_context(patch.object(c,'nc_covering_query_plan',side_effect=self.plan))
        stack.enter_context(patch.object(c,'reconciled_registry_address',return_value={'decision':'corroborated','basis':'modeled EIN-linked address'}))
        stack.enter_context(patch.object(c,'licensed_charity_street_evidence',return_value={}))
        return stack
    def complete(self,res,out,empty=False):
        queries=[]
        source=next(row for row in out['evidence']['rows']if row['License']and row['CSL Type']=='Charitable Organization')
        for _ in range(20):
            if res.get('phase')!='search':break
            q=res['query'];queries.append(copy.deepcopy(q))
            if q['operation']=='search':
                evidence={**copy.deepcopy(out['evidence']),'query':q,'search_mode':q.get('search_mode','STARTS_WITH')}
                if empty:evidence.update(rows=[],total=0)
            elif q['operation']=='detail':
                fields={**NC_PROFILE,'Name':out['name'],'Registration #':source['License'],'Status':source['Status'],
                    'Expiration Date':source['Expiration Date'],'Extension End Date':source['Extension End Date'],'profile_url':source['profile_url']}
                evidence={'query':q,'complete':True,'fields':fields}
            elif q['operation']=='filings':evidence={'query':q,'complete':True,'url':q['url'],'rows':[{'type':'Renewal Charity','date':'7/1/2026'}]}
            else:self.fail(q)
            code,res=self.t.advance(res,evidence=evidence)
            self.assertEqual(code,200)
        self.assertEqual(res['phase'],'complete')
        return res,queries
    def test_thirty_retained_identities_two_orders_recover_with_unchanged_deadline(self):
        outputs=json.loads((ROOT/'testing/fixtures/oct19-nc-collector-outputs.json').read_text())
        self.assertEqual(len({o['ein']for o in outputs}),30)
        for out in outputs:
            with self.subTest(ein=out['ein']),self.contexts(out['name']):
                self.t.orgs['NC']=c.checker.Organization(out['name'],out['ein'])
                _,res=self.start('NC');before=self.unpack(res)
                self.assertEqual(res['query']['search_mode'],'ALL_WORDS')
                _,nextres=self.source_fail(res);after=self.unpack(nextres)
                self.assertEqual(after['expires'],before['expires']);self.assertEqual(after['issued'],before['issued'])
                self.assertEqual(after['completed'],[])
                self.assertEqual(after['search_failed_receipts'][0]['outcome'],'Completion not confirmed')
                self.assertNotEqual(nextres['query_id'],res['query_id'])
                expected_first={'68-0124097':'United Animal Nations','84-1383926':'WGU Corporation','45-0541654':'American Indian'}.get(out['ein'],out['name'])
                self.assertEqual(nextres['query']['name'],expected_first)
                self.assertNotIn('search_mode',nextres['query'])
                final,queries=self.complete(nextres,out)
                self.assertEqual(final['result']['status'],'Current',final)
                self.assertEqual(final['result']['matched_registry_identifier'],'SL123456')
                self.assertIn('incomplete broad North Carolina search',final['result']['comments'])
                self.assertTrue(all(q.get('search_mode')!='ALL_WORDS'for q in queries))
    def test_observed_lobular_search_card_recovers_through_signed_master(self):
        fixture=json.loads((ROOT/'testing/fixtures/nc-lobular-specific.json').read_text())
        actual=fixture['evidence'];card=actual['rows'][0]
        self.assertEqual(card['License'],'SL015410')
        out={'name':'Lobular Breast Cancer Alliance, Inc.','ein':'86-2260246','evidence':actual}
        with self.contexts(out['name']):
            self.t.orgs['NC']=c.checker.Organization(out['name'],out['ein'])
            _,res=self.start();_,narrow=self.source_fail(res)
            self.assertEqual(narrow['query']['name'],out['name'])
            # Detail is a bounded model populated from the actual public card;
            # this is signed-master integration, not a live detail acceptance.
            final,queries=self.complete(narrow,out)
            self.assertEqual(final['result']['matched_registry_identifier'],'SL015410')
            self.assertIn(final['result']['status'],['Current','Upcoming Filing'])
            self.assertTrue(final['result']['success'])

    def test_guards_reject_wrong_query_state_action_mode_reason_deadline_and_repeat(self):
        record={'state':'NC','mode':'standard','expires':100,
            'recovery_protocol':'nc-fresh-search-v1',
            'pending':{'query_id':'signed-query','query':{'state':'NC','operation':'search','name':'BREAST CANCER','search_mode':'ALL_WORDS'}}}
        payload={'query_id':'signed-query','reason':REASON}
        variants=[({'state':'NV'},{}),({'mode':'sales'},{}),({'expires':40},{}),({'nc_specific_name_recovery':{'attempt':1}},{}),
            ({'recovery_protocol':None},{}),({'nc_search_recovery':{'attempt':1}},{}),
            ({},{'query_id':'other'}),({},{'reason':'NY_CONNECTOR_VERIFICATION_REQUIRED'}),({},{'reason':'NY_CONNECTOR_TAB_READY_TIMEOUT'}),
            ({'pending':None},{}),({'pending':{'query_id':'signed-query','query':{'state':'NC','operation':'detail','search_mode':'ALL_WORDS'}}},{}),
            ({'pending':{'query_id':'signed-query','query':{'state':'NC','operation':'search','search_mode':'STARTS_WITH'}}},{}),
            ({'pending':{'query_id':'signed-query','query':{'state':'NV','operation':'search','search_mode':'ALL_WORDS'}}},{})]
        for changes,pchanges in variants:
            rec={**copy.deepcopy(record),**changes};old=copy.deepcopy(rec)
            self.assertFalse(c.nc_specific_name_recovery(rec,{**payload,**pchanges},20))
            self.assertEqual(rec,old)
        self.assertTrue(c.nc_specific_name_recovery(record,payload,20))
        self.assertFalse(c.nc_specific_name_recovery(record,payload,20))
    def test_signed_binding_and_failed_specific_query_do_not_complete_negative(self):
        name='Lobular Breast Cancer Alliance, Inc.'
        with self.contexts(name):
            self.t.orgs['NC']=c.checker.Organization(name,'862260246');_,res=self.start()
            self.assertEqual(self.source_fail(res,device_id='another-device')[0],410)
            self.assertEqual(self.source_fail(res,check_token=res['check_token']+'bad')[0],410)
            _,stale=self.source_fail(res,query_id='other')
            self.assertEqual(stale['phase'],'complete');self.assertEqual(stale['result']['status'],'Unable to Confirm')
            _,narrow=self.source_fail(res);_,failed=self.source_fail(narrow)
            self.assertEqual(failed['phase'],'complete');self.assertEqual(failed['result']['status'],'Unable to Confirm')
            self.assertFalse(failed['result']['success'])
    def test_completed_specific_negatives_require_all_reviewed_aliases(self):
        out=json.loads((ROOT/'testing/fixtures/oct19-nc-collector-outputs.json').read_text())[0]
        aliases=['Distinct Reviewed Campaign','Third Reviewed Campaign']
        with self.contexts(out['name'],aliases):
            self.t.orgs['NC']=c.checker.Organization(out['name'],out['ein']);_,res=self.start();_,narrow=self.source_fail(res)
            final,queries=self.complete(narrow,out,empty=True)
            self.assertEqual(final['result']['status'],'Not Registered')
            self.assertEqual([q['name']for q in queries],[out['name'],*aliases])
            self.assertTrue(all(q.get('search_mode')!='ALL_WORDS'for q in queries))
    def test_incomplete_alias_never_becomes_negative(self):
        out=json.loads((ROOT/'testing/fixtures/oct19-nc-collector-outputs.json').read_text())[0]
        with self.contexts(out['name'],['Distinct Reviewed Campaign']):
            self.t.orgs['NC']=c.checker.Organization(out['name'],out['ein']);_,res=self.start();_,narrow=self.source_fail(res)
            q=narrow['query'];ev={'state':'NC','query':q,'search_mode':'STARTS_WITH','complete':True,'verification_pending':False,'total':0,'rows':[]}
            _,alias=self.t.advance(narrow,evidence=ev);self.assertEqual(alias['query']['name'],'Distinct Reviewed Campaign')
            _,failed=self.source_fail(alias)
            self.assertEqual(failed['result']['status'],'Unable to Confirm');self.assertFalse(failed['result']['success'])

    def test_failed_collector_requires_existing_nc_fresh_transport_once(self):
        name='Lobular Breast Cancer Alliance, Inc.'
        with self.contexts(name):
            self.t.orgs['NC']=c.checker.Organization(name,'862260246')
            _,res=self.start();before=self.unpack(res)
            _,narrow=self.source_fail(res);after=self.unpack(narrow)
            self.assertEqual(narrow['recovery'],{'action':'fresh_browser','attempt':1,'reason':REASON})
            self.assertEqual(narrow['query']['state'],'NC')
            self.assertEqual(narrow['query']['name'],name)
            self.assertEqual(after['expires'],before['expires'])
            self.assertLessEqual(narrow['lookup_remaining_ms'],int((before['expires']-time.time())*1000)+100)
            for failure in [REASON,'NY_CONNECTOR_TAB_READY_TIMEOUT','NY_CONNECTOR_NC_SEARCH_NOT_STARTED']:
                _,failed=self.t.request({'action':'fail','check_token':narrow['check_token'],
                    'query_id':narrow['query_id'],'reason':failure})
                self.assertEqual(failed['phase'],'complete');self.assertNotIn('recovery',failed)
                self.assertEqual(failed['result']['status'],'Unable to Confirm')
            _,no_protocol=self.t.start('NC')
            _,failed=self.source_fail(no_protocol)
            self.assertEqual(failed['phase'],'complete');self.assertNotIn('recovery',failed)

if __name__=='__main__':unittest.main()
