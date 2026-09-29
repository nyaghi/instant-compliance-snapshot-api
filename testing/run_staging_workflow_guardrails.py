"""Security, preservation and accounting controls for Aurora's worker transport."""
import ast
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c
from deployment import staging_workflows as w
from deployment.durable_queue import normalize_submission, workflow_state_limit


class WorkflowControls(unittest.TestCase):
    def setUp(self):
        self.version=patch.object(c,'APP_VERSION','2026.09.28.5-staging');self.version.start();self.addCleanup(self.version.stop)
        key=patch.object(c,'NY_CONNECTOR_SIGNING_KEY','a'*48);key.start();self.addCleanup(key.stop)
        env=patch.dict(os.environ,{'RENDER_SERVICE_ID':next(iter(w.STAGING)),
            'PUBLIC_BASE_URL':next(iter(w.STAGING.values())),'CE_STAGING_WORKFLOW_ORIGIN':w.ORIGIN,
            'CE_STAGING_WORKFLOW_KEY':'b'*48,'CE_STAGING_WORKFLOW_VERSION':'2026.09.28.5-performance-lab'})
        env.start();self.addCleanup(env.stop)
        self.owner=['reviewer@compliance-express.com','device-control']
        self.record={'owner':self.owner,'id':'a'*8+'-'+'b'*4+'-'+'c'*4+'-'+'d'*4+'-'+'e'*12,
            'issued':int(time.time()),'expires':int(time.time())+100,'version':c.APP_VERSION,
            'ein':'123456789','name':'Control Foundation','states':['PA','WI'],'mode':'sales'}
        self.payload={'organization_name':'Control Foundation','ein':'12-3456789','states':['PA','IL','GA'],
            'mode':'sales','request_id':'11111111-1111-1111-1111-111111111111','alternate_names':['Former Control']}

    def test_staging_only_and_fail_closed_without_secrets(self):
        self.assertTrue(w.enabled(c))
        for changes in [{'RENDER_SERVICE_ID':'production'},{'PUBLIC_BASE_URL':'https://compliance-express.com'},
                        {'CE_STAGING_WORKFLOW_KEY':''},{'CE_STAGING_WORKFLOW_ORIGIN':'https://elsewhere.invalid'}]:
            with patch.dict(os.environ,changes):self.assertFalse(w.enabled(c))
        with patch.object(c,'APP_VERSION','2026.09.28.5'):self.assertFalse(w.enabled(c))

    def test_connector_names_bound_to_settled_same_ein_and_worker_release(self):
        value={'state':'@sales_identity','ein':self.record['ein'],
            'app_version':os.environ['CE_STAGING_WORKFLOW_VERSION'],
            'reviewed_names':['Former Control'],'errors':{}}
        def status(v=value, **job):
            return {'preparation':[dict(state='@sales_identity',phase='done',result=v,**job)]}
        self.assertEqual(w.connector_identity(status(),self.record),
            {'ready':True,'confirmed':True,'names':['Former Control']})
        self.assertFalse(w.connector_identity(status({**value,'errors':{'IRS':'Timeout'}}),self.record)['confirmed'])
        for changes in [{'ein':'987654321'},{'app_version':'old'}, {'state':'GA'},
                        {'reviewed_names':None},{'reviewed_names':['x'*301]}]:
            self.assertEqual(w.connector_identity(status({**value,**changes}),self.record),
                {'ready':True,'confirmed':False,'names':[]})
        self.assertFalse(w.connector_identity(status(error='timeout'),self.record)['confirmed'])
        self.assertIsNone(w.connector_identity({'preparation':[]},self.record))
        self.assertIsNone(w.connector_identity(status(),{**self.record,'mode':'standard'}))

    def test_connector_only_sales_preparation_is_narrowly_allowed(self):
        p={**self.payload,'states':['GA'],'alternate_names':[]}
        with patch.object(w,'call',return_value={'id':self.record['id']}) as call:
            w.prepare(c,p,self.owner)
            request=call.call_args.args[1]
        self.assertEqual(request['states'],[])
        self.assertEqual(normalize_submission(request,c.SUPPORTED_STATES)['external_state_slots'],1)
        for changes in [{'mode':'standard'},{'external_state_slots':0},{'alternate_names':['Reviewed']}]:
            with self.assertRaises(ValueError):normalize_submission({**request,**changes},c.SUPPORTED_STATES)

    def test_tokens_bound_to_owner_release_and_expiration(self):
        token=w.pack(c,self.record)
        self.assertEqual(w.unpack(c,token,self.owner),self.record)
        for owner in [['someone-else','device-control'],[self.owner[0],'another-device']]:
            with self.assertRaises(ValueError):w.unpack(c,token,owner)
        with patch.object(c,'APP_VERSION','next-staging'):
            with self.assertRaises(ValueError):w.unpack(c,token,self.owner)
        with patch.object(w.time,'time',return_value=self.record['expires']):
            with self.assertRaises(ValueError):w.unpack(c,token,self.owner)
        with self.assertRaises(ValueError):w.unpack(c,token[:-1]+'x',self.owner)

    def test_authentication_precedes_submission(self):
        body=json.dumps({'action':'start','email':self.owner[0],'admin_passcode':'wrong',**self.payload}).encode()
        handler=Mock(headers={'Content-Length':str(len(body))},rfile=io.BytesIO(body))
        with patch.object(c,'staging_access_error',return_value='denied'),patch.object(w,'call') as call:
            w.handle(c,handler)
        self.assertEqual(handler._send_json.call_args.args[0],403);call.assert_not_called()

    def test_selection_aliases_concurrency_and_idempotency_preserved(self):
        with patch.object(w,'call',return_value={'id':self.record['id']}) as call:
            answer=w.prepare(c,self.payload,self.owner);request=call.call_args.args
            self.assertEqual(request[1]['states'],['PA'])
            self.assertEqual(request[1]['alternate_names'],['Former Control'])
            self.assertEqual(request[1]['state_concurrency'],20)
            self.assertEqual(request[1]['external_state_slots'],2)
            w.prepare(c,self.payload,self.owner);self.assertEqual(call.call_args.args[2],request[2])
            w.prepare(c,{**self.payload,'mode':'standard'},self.owner)
            self.assertEqual(call.call_args.args[1]['state_concurrency'],15)
        self.assertEqual(answer['external_states'],['GA','IL'])

    def test_reserved_connector_slots_count_against_same_limit(self):
        for mode,limit in [('standard',15),('sales',20)]:
            p=normalize_submission({k:v for k,v in {**self.payload,'states':['PA'], 'mode':mode,
                'state_concurrency':limit,'external_state_slots':2}.items() if k!='request_id'},c.SUPPORTED_STATES)
            self.assertEqual(workflow_state_limit({'payload':p}),limit-2)
            p['external_state_slots']=0;self.assertEqual(workflow_state_limit({'payload':p}),limit)
        for value in [-1,3,True,'2']:
            with self.assertRaises(ValueError):normalize_submission({'organization_name':'Control','ein':'123456789',
                'states':['PA'],'external_state_slots':value},c.SUPPORTED_STATES)

    def test_results_validate_ein_state_and_version_without_status_changes(self):
        result={'ein':'123456789','state':'PA','status':'Delinquent','success':True,
            'app_version':'2026.09.28.5-performance-lab','matched_registry_identifier':'101',
            'initial_registration_date':'2020-01-01','comments':'Loaded blank filing fields.', 'lab_task_metrics':{}}
        actual=w.public_result(c,{'result':result,'state':'PA','phase':'done'},self.record)
        for key in ['status','success','matched_registry_identifier','initial_registration_date','comments']:
            self.assertEqual(actual[key],result[key])
        self.assertNotIn('lab_task_metrics',actual);self.assertEqual(actual['app_version'],c.APP_VERSION)
        for changes in [{'ein':'987654321'},{'state':'CT'},{'app_version':'old-performance-lab'}]:
            with self.assertRaises(ValueError):w.public_result(c,{'result':{**result,**changes},'state':'PA','phase':'done'},self.record)

    def test_retry_intermediate_response_is_not_published(self):
        for phase in ['queued','running']:
            self.assertIsNone(w.public_result(c,{'phase':phase,'state':'PA',
                'result':{'status':'Site Not Reachable','success':False}},self.record))

    def test_incomplete_jobs_never_become_definitive_negatives(self):
        for phase in ['queued','running','done']:
            value=w.public_result(c,{'result':None,'state':'PA','phase':phase},self.record)
            if phase!='done':self.assertIsNone(value)
            else:self.assertFalse(value['success']);self.assertEqual(value['status'],'Unable to Confirm')

    def test_staging_review_signing_branch_is_byte_equivalent_ast(self):
        old=subprocess.check_output(['git','show','a59c2d8:registry_snapshot_server.py']).decode('utf-8')
        new=Path(c.__file__).read_text(encoding='utf-8')
        find=lambda text:next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='attach_identity_review')
        from testing.performance_origin_audit import RestoreApprovedOrigin
        original,merged=find(old),RestoreApprovedOrigin().visit(find(new))
        del merged.body[1] # only addition: private worker export before unchanged staging branch
        self.assertEqual(ast.dump(merged),ast.dump(original))

    def test_worker_review_context_is_not_accepted_from_browser_payload(self):
        result={'ein':'123456789','state':'WI','app_version':'2026.09.28.5-performance-lab',
            'status':'Needs Review','_worker_identity_review':{'records':[]}}
        with patch.object(c,'attach_identity_review') as attach:
            value=w.public_result(c,{'result':result,'state':'WI','phase':'done'},self.record)
            attach.assert_called_once_with(value,{'records':[]})
        self.assertNotIn('_worker_identity_review',value)

    def test_every_nonconflicting_master_function_preserves_selected_parent(self):
        from testing.performance_origin_audit import RestoreApprovedOrigin
        def functions(ref):
            text=subprocess.check_output(['git','show',ref+':registry_snapshot_server.py']).decode('utf-8')
            return {n.name:ast.dump(n) for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)}
        base,aurora,lab=functions('35e61ae'),functions('a59c2d8'),functions('90ed42d')
        tree=RestoreApprovedOrigin().visit(ast.parse(Path(c.__file__).read_text(encoding='utf-8')))
        # Post-validation exposed a nameless NM detail shell classified as NR.
        # Remove only the separately behavior-tested confirmation hook; the
        # entire original adapter function must still match its selected parent.
        nm=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='search_wa_nm_state')
        hooks=[n for n in nm.body if isinstance(n,ast.If) and any(isinstance(x,ast.Call)
            and isinstance(x.func,ast.Name) and x.func.id=='nm_confirm_empty_detail' for x in ast.walk(n))]
        self.assertEqual(len(hooks),1)
        self.assertEqual(ast.unparse(hooks[0].body[0]),'return nm_confirm_empty_detail(org, module, copied)')
        nm.body.remove(hooks[0])
        merged={n.name:ast.dump(n) for n in tree.body if isinstance(n,ast.FunctionDef)}
        for name in sorted(set(aurora)|set(lab)):
            if name=='attach_identity_review':continue # separate full-branch equivalence test above
            # September 29 deliberately changes bounded literal query priority.
            # run_license_dash_guardrails checks this planner and preserves all
            # other existing master functions against the deployed predecessor.
            if name=='licensed_charity_names':continue
            a,l,b=aurora.get(name),lab.get(name),base.get(name)
            if a!=b and l!=b and a!=l:continue # thirteen explicitly reviewed overlaps
            expected=a if a!=b else l
            with self.subTest(function=name):self.assertEqual(merged.get(name),expected)

if __name__=='__main__':unittest.main(verbosity=2)
