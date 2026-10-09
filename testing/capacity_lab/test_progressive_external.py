"""Offline protocol/transaction controls; real Postgres controls live separately.

Exercise the real release method with a transactional in-memory ledger, including
concurrent callers. This does not substitute for the isolated Postgres tests.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
import io
import json
import os
import threading
import time
import types
import unittest
from unittest.mock import Mock, patch

from deployment.durable_queue import Queue, NotFound, workflow_state_limit
from deployment import staging_workflows as workflows


class Ledger:
    def __init__(self, slots=8, ceiling=20):
        self.record={'payload':{'external_state_slots':slots,'state_concurrency':ceiling}}
        self.lock=threading.Lock()
        self.events=[]
        self.writes=0

    @contextmanager
    def transaction(self):
        with self.lock:
            yield self,time.time()

    def execute(self,query,args):
        if query.startswith('SELECT'):
            return types.SimpleNamespace(fetchone=lambda:deepcopy(self.record) if args==('owner','workflow') else None)
        if query.startswith('UPDATE'):
            self.record['payload']=deepcopy(args[0].obj)
            self.writes+=1
            return
        raise AssertionError(query)

    def event(self,*args,**kwargs):self.events.append(kwargs)
    def release(self,count=None):return Queue.release_external_slots(self,'owner','workflow',count)


class ProgressiveExternalControls(unittest.TestCase):
    def test_slots_return_incrementally_with_same_standard_and_sales_ceiling(self):
        for ceiling in (15,20):
            ledger=Ledger(ceiling=ceiling)
            for settled in (0,1,1,0,4,3,7,8,5,8):
                ledger.release(settled)
                p=ledger.record['payload']
                self.assertEqual(p['external_state_slots']+p.get('external_slots_released',0),8)
                self.assertEqual(workflow_state_limit(ledger.record)+p['external_state_slots'],ceiling)
            self.assertEqual(ledger.writes,4)
            self.assertEqual(workflow_state_limit(ledger.record),ceiling)

    def test_concurrent_duplicate_and_out_of_order_callbacks_release_once(self):
        ledger=Ledger()
        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(ledger.release,[1,4,2,3,4,5,8,6,8,7]*4))
        self.assertEqual(ledger.record['payload']['external_state_slots'],0)
        self.assertEqual(ledger.record['payload']['external_slots_released'],8)
        self.assertEqual(sorted(set(e['settled'] for e in ledger.events)),[e['settled'] for e in ledger.events])

    def test_invalid_counts_and_other_owner_cannot_release_capacity(self):
        ledger=Ledger()
        for invalid in (-1,9,1.0,True,False,'1',[],{}):
            with self.assertRaises(ValueError):ledger.release(invalid)
        with self.assertRaises(NotFound):Queue.release_external_slots(ledger,'other','workflow',1)
        self.assertEqual(ledger.writes,0)

    def test_legacy_all_settled_release_remains_idempotent_after_partial_release(self):
        ledger=Ledger(slots=2,ceiling=15)
        ledger.release(1);ledger.release();ledger.release();ledger.release(1)
        self.assertEqual(workflow_state_limit(ledger.record),15)
        self.assertEqual(ledger.writes,2)

    def test_transport_negotiates_only_for_trial_and_forwards_cumulative_count(self):
        master=types.SimpleNamespace(APP_VERSION='fixture',NY_CONNECTOR_SIGNING_KEY='x'*48,
            SUPPORTED_STATES=['CO','IL','NY','NM','GA','AL','NC','NV','TN','MS'],IDENTITY_STATES=['CO'],
            canonical_ein_digits=lambda v:v.replace('-',''),normalize_email=lambda v:v,
            normalize_device_id=lambda v:v,staging_access_error=lambda *args:False,
            is_verified_internal_passcode=lambda *args:True,log_error=lambda *args:None)
        owner=['fixture@example.test','device']
        ident='11111111-1111-1111-1111-111111111111'
        queue=Mock();queue.submit.return_value=(ident,True)
        def request(body,trial=True):
            raw=json.dumps({'email':owner[0],'device_id':owner[1],'admin_passcode':'fixture',**body}).encode()
            handler=Mock(headers={'Content-Length':str(len(raw))},rfile=io.BytesIO(raw))
            with patch.object(workflows,'enabled',return_value=not trial),patch('deployment.lab_identity.trial_identity',return_value={'origin':'fixture'} if trial else None):
                workflows.handle(master,handler,trial_queue=queue if trial else None)
            self.assertEqual(handler._send_json.call_args.args[0],200,handler._send_json.call_args)
            return handler._send_json.call_args.args[1]
        start={'action':'start','organization_name':'Fixture','ein':'123456789','states':['CO','IL','NY','NM'],
               'alternate_names':['Reviewed'],'request_id':ident,'mode':'standard','consent':True}
        with patch('deployment.durable_queue.trial_identity',return_value={'origin':'fixture'}):
            result=request(start)
        self.assertTrue(result['progressive_external_release'])
        request({'action':'release-external','token':result['token'],'settled_count':2})
        queue.release_external_slots.assert_called_once_with('private-performance-lab',ident,2)
        queue.reset_mock()
        queue.status.return_value={'source_version':'fixture','ein':'123456789','phase':'active',
            'completed':0,'total':1,'submitted':1,'deadline':61,'started':1,'finished':None,'jobs':[]}
        with patch.dict(os.environ,{'CE_STAGING_WORKFLOW_VERSION':'fixture'}):
            request({'action':'poll','token':result['token'],'settled_count':3})
        self.assertEqual([c[0] for c in queue.mock_calls],['release_external_slots','status'])
        queue.release_external_slots.assert_called_once_with('private-performance-lab',ident,3)
        queue.reset_mock()
        all_browser={**start,'states':['CO','NY','IL','GA','AL','NC','NV','TN','NM','MS']}
        with patch('deployment.durable_queue.trial_identity',return_value={'origin':'fixture'}):
            nine=request(all_browser)
        queued_payload=queue.submit.call_args.args[2]
        self.assertEqual(queued_payload['external_state_slots'],8)
        queue.reset_mock()
        with patch.dict(os.environ,{'CE_STAGING_WORKFLOW_VERSION':'fixture'}):
            request({'action':'poll','token':nine['token'],'settled_count':9})
        queue.release_external_slots.assert_called_once_with('private-performance-lab',ident,8)
        queue.reset_mock()
        request({'action':'release-external','token':nine['token'],'settled_count':9})
        queue.release_external_slots.assert_called_once_with('private-performance-lab',ident,8)
        with patch.object(workflows,'call',return_value={'id':ident}) as transport:
            legacy=request(start,trial=False)
            self.assertNotIn('progressive_external_release',legacy)
            request({'action':'release-external','token':legacy['token'],'settled_count':2},trial=False)
            self.assertEqual(transport.call_args.args[1],{})


if __name__=='__main__':unittest.main()
