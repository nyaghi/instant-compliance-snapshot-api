"""Same-workflow source reuse: lazy, exact EIN, bounded freshness, isolated."""
import ast
import copy
import json
from pathlib import Path
import socket
import subprocess
import time
import unittest
from unittest.mock import patch, MagicMock

socket.getaddrinfo=lambda *a,**k: (_ for _ in ()).throw(AssertionError('No live network in controls'))
import registry_snapshot_server as m
from deployment.queue_engine import execute

EIN='123456789'
PROFILE={'organization':{'ein':EIN,'name':'Example Foundation','city':'Oakland','state':'CA','latest_object_id':'202543019349300749'},
         'filings_with_data':[{'tax_prd':202412,'tax_prd_yr':2024,'totrevenue':123}], 'filings_without_data':[]}

def evidence():
    return {'state':'@sales_identity','ein':EIN,'app_version':m.APP_VERSION,'errors':{},
            'sources':{'IRS':{'names':[], 'public_profile':{
                'url':f'https://projects.propublica.org/nonprofits/api/v2/organizations/{EIN}.json',
                'retrieved_after':time.time(),'payload':copy.deepcopy(PROFILE)}}}}

class Reuse(unittest.TestCase):
    def setUp(self):
        self.cache=patch.dict(m.PUBLIC_PROFILE_CACHE,{},clear=True);self.cache.start();self.addCleanup(self.cache.stop)
        self.orgs=[{'organization_name':'Example Foundation','ein':EIN,'alternate_names':[]}]

    def run_with(self,e,lookup):
        with patch.object(m,'run_state_lookups_parallel',side_effect=lookup):
            return m.run_sales_lookups_with_source_evidence(self.orgs,['NJ'],e)

    def test_exact_same_profile_replaces_duplicate_request_only_when_needed(self):
        e=evidence()
        def lookup(*a):
            self.assertNotIn(EIN,m.PUBLIC_PROFILE_CACHE)
            self.assertEqual(m.public_profile_for_ein(EIN),PROFILE)
            self.assertIn(EIN,m.PUBLIC_PROFILE_CACHE)
            return m.public_profile_for_ein(EIN)
        with patch.object(m.urllib.request,'urlopen',side_effect=AssertionError('No repeated profile GET')):
            self.assertEqual(self.run_with(e,lookup),PROFILE)
        self.assertEqual(m.SALES_PROFILE_CONTEXT.get(),{})
        m.PUBLIC_PROFILE_CACHE[EIN]['organization']['name']='changed by child'
        self.assertEqual(e['sources']['IRS']['public_profile']['payload'],PROFILE)

    def test_lookup_without_profile_does_not_change_cache_presence(self):
        with patch.object(m.urllib.request,'urlopen') as network:
            self.assertEqual(self.run_with(evidence(),lambda *a: {'status':'Current'}),{'status':'Current'})
        network.assert_not_called();self.assertNotIn(EIN,m.PUBLIC_PROFILE_CACHE)

    def test_missing_stale_wrong_ein_wrong_origin_and_bad_payload_keep_normal_fetch(self):
        cases=[{}, {'retrieved_after':time.time()-61}, {'retrieved_after':time.time()+10},
               {'retrieved_after':float('nan')}, {'url':'https://untrusted.example/'},
               {'payload':{'organization':{'ein':'987654321'}}}, {'payload':None}]
        for change in cases:
            m.PUBLIC_PROFILE_CACHE.clear();e=evidence()
            e['sources']['IRS']['public_profile'].update(change)
            if not change:e['sources']['IRS'].pop('public_profile')
            response=MagicMock();response.__enter__.return_value=response;response.read.return_value=json.dumps(PROFILE).encode()
            with patch.object(m.urllib.request,'urlopen',return_value=response) as network:
                self.assertEqual(self.run_with(e,lambda *a:m.public_profile_for_ein(EIN)),PROFILE)
            self.assertEqual(network.call_count,1)

    def test_wrong_release_or_workflow_identity_rejected(self):
        for change in ({'ein':'987654321'},{'app_version':'old'},{'state':'@discovery'}):
            e=evidence();e.update(change)
            with self.assertRaises(ValueError):self.run_with(e,lambda *a:None)

    def test_exception_resets_context_and_other_ein_cannot_read_seed(self):
        def lookup(*a):
            self.assertEqual(m.public_profile_for_ein('987654321'),{})
            raise RuntimeError('lookup failed')
        with patch.object(m.urllib.request,'urlopen',side_effect=TimeoutError()) as network:
            with self.assertRaises(RuntimeError):self.run_with(evidence(),lookup)
        self.assertEqual(network.call_count,1);self.assertEqual(m.SALES_PROFILE_CONTEXT.get(),{})
        self.assertNotIn(EIN,m.PUBLIC_PROFILE_CACHE)

    def test_failed_identity_source_does_not_reuse_prior_process_cache(self):
        m.PUBLIC_PROFILE_CACHE[EIN]=copy.deepcopy(PROFILE)
        with patch.object(m,'identity_irs_names',side_effect=TimeoutError()), \
             patch.object(m,'identity_co_names',return_value={'complete':True,'names':[]}), \
             patch.object(m,'identity_or_names',return_value={'complete':True,'names':[]}):
            e=m.sales_identity_evidence('Example Foundation',EIN)
        self.assertNotIn('IRS',e['sources']);self.assertEqual(e['errors'],{'IRS':'TimeoutError'})

    def test_real_identity_collector_retains_response_without_extra_request(self):
        with patch.object(m,'identity_fetch',return_value=json.dumps(PROFILE).encode()) as fetch, \
             patch.object(m,'irs_return_header',return_value={'names':[],'dba_disclosed':False}), \
             patch.object(m,'identity_co_names',return_value={'complete':True,'names':[]}), \
             patch.object(m,'identity_or_names',return_value={'complete':True,'names':[]}):
            e=m.sales_identity_evidence('Example Foundation',EIN)
        self.assertEqual(fetch.call_count,1)
        self.assertEqual(e['sources']['IRS']['public_profile']['payload'],PROFILE)

    def test_queue_routes_only_internal_sales_evidence_to_reuse(self):
        result={'ein':EIN,'state':'CO','status':'Current','success':True}
        job={'state':'CO','version':m.APP_VERSION,'payload':{'organization_name':'Example','ein':EIN,'alternate_names':[],'mode':'sales'},'sales_identity':evidence()}
        with patch.object(m,'run_single_state_lookup_reliably',side_effect=lambda *a:dict(result,profile=m.public_profile_for_ein(EIN))), \
             patch.object(m.urllib.request,'urlopen',side_effect=AssertionError('Duplicate network')):
            r=execute(m,job)
        self.assertEqual(r['profile'],PROFILE)
        for changes in ({'mode':'standard'},{'alternate_names':['Reviewed']}):
            with self.assertRaises(ValueError):execute(m,{**job,'payload':{**job['payload'],**changes}})

    def test_remaining_master_and_queue_behavior_unchanged(self):
        from testing.capacity_lab.parsing_scope import strip_sales_profile_reuse, strip_browser_pool_metric
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show',BASE_COMMIT+':registry_snapshot_server.py'],cwd=root).decode('utf-8'))
        new=ast.parse(Path(m.__file__).read_text(encoding='utf-8'));strip_sales_profile_reuse(new)
        self.assertEqual(ast.dump(old),ast.dump(new))
        old=ast.parse(subprocess.check_output(['git','show',BASE_COMMIT+':deployment/queue_engine.py'],cwd=root).decode('utf-8'))
        new=ast.parse((root/'deployment/queue_engine.py').read_text(encoding='utf-8'))
        strip_browser_pool_metric(new)
        for n in ast.walk(new):
            if isinstance(n,ast.Assign) and isinstance(n.value,ast.IfExp) and 'run_sales_lookups_with_source_evidence' in ast.unparse(n.value):
                n.value=n.value.orelse
        self.assertEqual(ast.dump(old),ast.dump(new))

BASE_COMMIT='e3b09d5a3cc031374925a17fe0211ff4398273f2'
if __name__=='__main__':unittest.main()
