"""Sales same-run identity: exact EIN, reviewed scope and strict time budget."""
import json
import socket
import time
import unittest
from unittest.mock import patch

socket.getaddrinfo=lambda *a,**k: (_ for _ in ()).throw(AssertionError('No live registry in controls'))
import registry_snapshot_server as m
from deployment.queue_engine import execute

EIN='123456789'

def candidate(name, **extra):
    return dict(m.identity_candidate(name,'Colorado','Earlier registered name','https://data.colorado.gov/'),**extra)

def evidence(**extra):
    return {'ein':EIN,'state':'@sales_identity','app_version':m.APP_VERSION,
            'sources':{'CO':{'names':[candidate('Former Legal Name')]},'IRS':{'names':[candidate('Other Legal Name')]}},
            'errors':{},**extra}

class SalesIdentityTests(unittest.TestCase):
    def setUp(self):
        self.oregon=patch.object(m,'identity_or_names',return_value={'complete':True,'names':[]})
        self.oregon.start();self.addCleanup(self.oregon.stop)

    def test_local_oregon_registered_name_survives_metadata_truncation(self):
        with patch.object(m,'identity_or_names',return_value={'complete':True,'names':[candidate('Full Registered Legal Name')]}), \
             patch.object(m,'identity_co_names',return_value={'complete':True,'names':[]}), \
             patch.object(m,'identity_irs_names',return_value={'complete':True,'names':[candidate('Truncated Legal')]}):
            r=m.sales_identity_evidence('Entered',EIN)
        self.assertEqual(m.sales_names_from_evidence(EIN,r),['Truncated Legal','Full Registered Legal Name'])

    def test_irs_metadata_does_not_fetch_filings_and_rejects_wrong_ein(self):
        payload={'organization':{'ein':EIN,'name':'Legal Name','latest_object_id':'202543019349300749','city':'Chicago','state':'IL'}}
        with patch.object(m,'identity_fetch',return_value=json.dumps(payload).encode()), \
             patch.object(m,'irs_return_header',side_effect=AssertionError('No filing work')):
            r=m.identity_irs_names(EIN,time.monotonic()+2,metadata_only=True)
            self.assertEqual([n['name'] for n in r['names']],['Legal Name'])
            self.assertEqual(r['address']['ein'],EIN)
            with self.assertRaises(ValueError):m.identity_irs_names('987654321',time.monotonic()+2,metadata_only=True)

    def test_group_subordinate_never_adds_parent_name(self):
        payload={'organization':{'ein':EIN,'name':'National Parent','sort_name':'Local Chapter','affiliation_code':9}}
        with patch.object(m,'identity_fetch',return_value=json.dumps(payload).encode()):
            r=m.identity_irs_names(EIN,time.monotonic()+2,metadata_only=True)
        self.assertEqual([n['name'] for n in r['names']],['Local Chapter'])

    def test_latest_header_preserves_full_name_without_history_fetch(self):
        payload={'organization':{'ein':EIN,'name':'Truncated Legal Name','latest_object_id':'202543019349300749'}}
        with patch.object(m,'identity_fetch',return_value=json.dumps(payload).encode()), \
             patch.object(m,'irs_return_header',return_value={'names':[candidate('Complete Legal Name From Filer')],'dba_disclosed':False}) as header, \
             patch.object(m,'identity_irs_historical_names',side_effect=AssertionError('No history for Sales')):
            r=m.identity_irs_names(EIN,time.monotonic()+2,latest_only=True)
        self.assertTrue(r['complete'])
        self.assertEqual([n['name'] for n in r['names']],['Truncated Legal Name','Complete Legal Name From Filer'])
        self.assertFalse(header.call_args.kwargs['require_period'])

    def test_header_failure_keeps_metadata_but_marks_identity_incomplete(self):
        payload={'organization':{'ein':EIN,'name':'Metadata Name','latest_object_id':'202543019349300749'}}
        with patch.object(m,'identity_fetch',return_value=json.dumps(payload).encode()), \
             patch.object(m,'irs_return_header',side_effect=TimeoutError('unfinished')), \
             patch.object(m,'identity_co_names',return_value={'complete':True,'names':[]}):
            r=m.sales_identity_evidence('Entered name',EIN)
        self.assertEqual(r['errors'],{'IRS':'Incomplete identity evidence'})
        self.assertEqual(m.sales_names_from_evidence(EIN,r),['Metadata Name'])
        result=m.sales_result_with_identity({'ein':EIN,'state':'DC','status':'Not Registered'},r)
        self.assertEqual(result['status'],'Unable to Confirm')

    def test_collectors_are_parallel_bounded_and_partial_evidence_survives(self):
        calls=[]
        def co(ein,deadline):
            calls.append(('CO',ein,deadline));time.sleep(.05);return {'names':[candidate('Former Legal Name')]}
        def irs(ein,deadline,**kw):
            calls.append(('IRS',ein,deadline,kw));raise TimeoutError('unavailable')
        with patch.object(m,'identity_co_names',side_effect=co),patch.object(m,'identity_irs_names',side_effect=irs):
            start=time.monotonic();r=m.sales_identity_evidence('Original',EIN)
        self.assertEqual(r['ein'],EIN);self.assertEqual(r['errors'],{'IRS':'TimeoutError'})
        self.assertEqual(m.sales_names_from_evidence(EIN,r),['Former Legal Name'])
        self.assertLess(r['seconds'],1);self.assertEqual(calls[0][2],calls[1][2])
        self.assertLessEqual(calls[0][2]-start,6.1);self.assertTrue(calls[1][3]['latest_only'])

    def test_verified_ein_and_version_fences(self):
        for extra in ({'ein':'987654321'},{'app_version':'old'},{'state':'CO'}):
            with self.assertRaises(ValueError):m.sales_names_from_evidence(EIN,evidence(**extra))
        r=evidence();r['sources']['CO']['names'] += [candidate('Wrong Identity',identity_conflict={'ein':'bad'}),candidate('Unverified',verified=False)]
        self.assertEqual(m.sales_names_from_evidence(EIN,r),['Former Legal Name','Other Legal Name'])

    def test_automatic_names_apply_only_to_this_sales_state_job(self):
        result={'ein':EIN,'state':'DC','app_version':m.APP_VERSION,'status':'Current','success':True}
        job={'state':'DC','version':m.APP_VERSION,'payload':{'organization_name':'Original','ein':EIN,'alternate_names':[],'mode':'sales'},'sales_identity':evidence()}
        def registry(*args):
            self.assertEqual(m.known_names_for_ein(EIN),['Former Legal Name','Other Legal Name']);return dict(result)
        with patch.object(m,'run_single_state_lookup_reliably',side_effect=registry):
            actual=execute(m,job)
        self.assertEqual(m.known_names_for_ein(EIN),[]);self.assertEqual(job['payload']['alternate_names'],[])
        self.assertEqual(actual['status'],'Current');self.assertIn('same EIN',actual['comments'])
        for changes in ({'mode':'standard'},{'alternate_names':['Reviewed']}):
            with self.assertRaises(ValueError):execute(m,{**job,'payload':{**job['payload'],**changes}})

    def test_incomplete_identity_never_becomes_definitive_name_only_negative(self):
        for state in ('DC','NH','ND','RI','WI'):
            r=m.sales_result_with_identity({'ein':EIN,'state':state,'status':'Not Registered','success':True},evidence(errors={'CO':'TimeoutError'}))
            self.assertEqual(r['status'],'Unable to Confirm');self.assertFalse(r['success'])
        for status in ('Current','Unable to Confirm','Site Not Reachable'):
            r=m.sales_result_with_identity({'ein':EIN,'state':'DC','status':status},evidence(errors={'CO':'TimeoutError'}))
            self.assertEqual(r['status'],status)
        r=m.sales_result_with_identity({'ein':EIN,'state':'NY','status':'Not Registered'},evidence(errors={'CO':'TimeoutError'}))
        self.assertEqual(r['status'],'Not Registered')

    def test_client_cannot_submit_identity_evidence(self):
        from deployment.durable_queue import normalize_submission
        with self.assertRaises(ValueError):normalize_submission({'organization_name':'Original','ein':EIN,'states':['DC'],'sales_identity':evidence()},['DC'])

if __name__=='__main__':unittest.main(verbosity=2)
