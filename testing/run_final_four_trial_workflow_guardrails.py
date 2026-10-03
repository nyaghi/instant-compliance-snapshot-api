"""Isolated UI and queue integration; approved 29.1 defaults are controls."""
import json
import io
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch, Mock

import registry_snapshot_server as cc
from deployment import performance_lab as lab, staging_workflows as workflows, durable_queue
from deployment.package_final_four_connector import build

ROOT = Path(__file__).resolve().parents[1]
NODE = Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
TRIAL = {'origin': 'https://fixture-final-four.onrender.com'}


class TrialWorkflowControls(unittest.TestCase):
    def test_real_ui_failure_preserves_aliases_for_retry(self):
        with patch.object(lab,'trial_identity',return_value=TRIAL):
            source=lab.final_four_asset('index.html',(ROOT/'web-staging/index.html').read_text(encoding='utf-8'))
        start=source.index('    async function requestSingleState(')
        end=source.index('    function stateLaneBases(',start)
        # Execute the ordinary UI's error path, including a bridge that fails
        # before the master can return a signed continuation/result.
        program='''const vm=require('node:vm'), assert=require('node:assert/strict');
const source=SOURCE;
(async()=>{for(const state of ['AL','NC','NV','TN']) {
 const aliases=['Reviewed Former Name','Distinct Acronym'];
 const context={window:{location:{origin:'https://staging.compliance-express.com'},
   CCNYConnector:{lookup:async()=>{throw Error('bridge unavailable');}}},
   internalUnlocked:true,runAlternateNames:[],adminPasscode:{value:'fixture'},
   getDeviceId:()=> 'fixture-device',fallbackResult:(state,ein,comment,name)=>({state,ein,comment,name})};
 vm.createContext(context);vm.runInContext(source,context);
 const failed=await context.requestSingleState('fixture','123456789','test@example.org',state,'Example Charity',false,aliases);
 assert.equal(failed.status,'Unable to Confirm');
 assert.deepEqual(Array.from(failed.reviewed_alternate_names),aliases);
 assert.notEqual(failed.reviewed_alternate_names,aliases);
 let received;
 context.window.CCNYConnector.lookup=async input=>{received=input;return {status:'fixture'};};
 await context.requestSingleState('fixture','123456789','test@example.org',state,'Example Charity',true,failed.reviewed_alternate_names);
 assert.deepEqual(Array.from(received.alternate_names),aliases);
}})().catch(e=>{console.error(e);process.exitCode=1;});'''.replace('SOURCE',json.dumps(source[start:end]))
        result=subprocess.run([str(NODE),'-e',program],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)

    def test_trial_frontend_nc_recovery_runs_existing_cleanup_and_deadline_controls(self):
        with patch.object(lab,'trial_identity',return_value=TRIAL), tempfile.TemporaryDirectory() as tmp:
            source=lab.final_four_asset('ny-connector.js',(ROOT/'web-staging/ny-connector.js').read_text(encoding='utf-8'))
            path=Path(tmp)/'trial-connector.js';path.write_text(source,encoding='utf-8')
            result=subprocess.run([str(NODE),'--test',str(ROOT/'testing/run_connector_frontend.cjs')],
                                  env={**os.environ,'CC_TEST_CONNECTOR_SOURCE':str(path),'CC_TEST_RECOVERY_STATE':'NC'},
                                  capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)

    def test_packaged_trial_version_starts_both_mature_registry_routes(self):
        # Exercise the actual start endpoint. Testing IL recovery alone missed
        # a second version list that rejected 0.6.11 before any registry call.
        with tempfile.TemporaryDirectory() as tmp:
            version = build(TRIAL['origin'], Path(tmp)/'trial')['version']
        payload = {'action':'start', 'email':'test@compliance-express.com',
                   'admin_passcode':'fixture', 'device_id':'fixture-device',
                   'organization_name':'Example Charity', 'ein':'123456789',
                   'connector_version':version}
        with patch.object(cc, 'is_verified_internal_passcode', return_value=True), \
                patch.object(cc, 'ny_connector_origin_allowed', return_value=True), \
                patch.object(cc, 'NY_CONNECTOR_SIGNING_KEY', 'fixture-'*8), \
                patch.object(cc, 'ny_connector_advance', return_value={'phase':'complete','result':{}}) as advance:
            for state in ['IL', 'GA']:
                with self.subTest(state=state), patch.object(cc, 'trial_identity', return_value=TRIAL):
                    code, result = cc.ny_connector_request({**payload, 'state':state}, TRIAL['origin'])
                    self.assertEqual(code, 200, result)
                    self.assertEqual(advance.call_args.args[0]['connector_version'], version)
                    self.assertEqual(advance.call_args.args[0]['state'], state)
            for version_value in [version, '9.9.9']:
                with patch.object(cc, 'trial_identity', return_value=None):
                    code, result = cc.ny_connector_request({**payload, 'state':'IL', 'connector_version':version_value}, cc.NY_CONNECTOR_ORIGIN)
                    self.assertEqual(code, 400, result)
            with patch.object(cc, 'trial_identity', return_value=TRIAL):
                code, result = cc.ny_connector_request({**payload, 'state':'GA', 'connector_version':'9.9.9'}, TRIAL['origin'])
                self.assertEqual(code, 400, result)

    def test_trial_connector_retains_approved_il_recovery_without_resetting_budget(self):
        record={'state':'IL','purpose':'registration','recovery_protocol':'il-fresh-page-v1',
                'connector_version':'0.6.8','issued':1000,'expires':1360,
                'completed':[{'query':{'ein':'123456789'},'rows':[]}],
                'pending':{'query_id':'old-query','query':{'orgName':'Example Charity'}}}
        payload={'reason':'NY_CONNECTOR_IL_VERIFICATION_PENDING','query_id':'old-query'}
        with patch.object(cc,'trial_identity',return_value=TRIAL):
            response=cc.il_verification_recovery(record,payload,1060)
            self.assertIsNotNone(response)
            self.assertEqual(response['query'],{'orgName':'Example Charity'})
            self.assertNotEqual(response['query_id'],'old-query')
            self.assertEqual(record['issued'],1000);self.assertEqual(record['expires'],1360)
            self.assertEqual(len(record['completed']),1)
            payload['query_id']=response['query_id']
            self.assertIsNone(cc.il_verification_recovery(record,payload,1080))

    def test_trial_il_recovery_does_not_enable_unknown_clients_or_weaken_guards(self):
        base={'state':'IL','purpose':'registration','recovery_protocol':'il-fresh-page-v1',
              'connector_version':'0.6.8','issued':1000,'expires':1360,
              'pending':{'query_id':'query','query':{'orgName':'Example Charity'}}}
        payload={'reason':'NY_CONNECTOR_IL_VERIFICATION_PENDING','query_id':'query'}
        with patch.object(cc,'trial_identity',return_value=None):
            self.assertIsNone(cc.il_verification_recovery(dict(base),payload,1060))
        with patch.object(cc,'trial_identity',return_value=TRIAL):
            for change in [{'connector_version':'0.6.3'},{'connector_version':'9.9.9'},
                           {'state':'GA'},{'purpose':'identity'},{'recovery_protocol':''}]:
                self.assertIsNone(cc.il_verification_recovery({**base,**change},payload,1060))
            self.assertIsNone(cc.il_verification_recovery(dict(base),payload,1180))
            self.assertIsNone(cc.il_verification_recovery(dict(base),{**payload,'query_id':'wrong'},1060))
            self.assertIsNone(cc.il_verification_recovery(dict(base),{**payload,'reason':'NY_CONNECTOR_IL_RESPONSE_TIMEOUT'},1060))

    def payload(self):
        return {'organization_name':'Example National Foundation','ein':'123456789','states':['IL','GA','AL','NC','NV','TN','MA'],
                'mode':'standard','alternate_names':['Example Foundation'],'request_id':'11111111-1111-1111-1111-111111111111'}

    def test_approved_templates_are_unmodified_without_active_trial(self):
        with patch.object(lab,'trial_identity',return_value=None):
            for name in ['index.html','sales-mode.js','optimized-workflows.js','ny-connector.js']:
                text=(ROOT/'web-staging'/name).read_text(encoding='utf-8')
                self.assertEqual(lab.final_four_asset(name,text),text)

    def test_trial_has_38_checkboxes_and_generated_javascript_compiles(self):
        import re
        with patch.object(lab,'trial_identity',return_value=TRIAL), tempfile.TemporaryDirectory() as tmp:
            for name in ['index.html','sales-mode.js','optimized-workflows.js','ny-connector.js']:
                text=lab.final_four_asset(name,(ROOT/'web-staging'/name).read_text(encoding='utf-8'))
                if name=='index.html':
                    states=re.findall(r'name="states" value="([A-Z]{2})"',text)
                    self.assertEqual(len(states),38);self.assertEqual(len(set(states)),38)
                    self.assertIn('v2026.09.29.2',text)
                    code='\n'.join(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>',text,re.S))
                else: code=text
                p=Path(tmp)/(name+'.js');p.write_text(code,encoding='utf-8')
                result=subprocess.run([str(NODE),'--check',str(p)],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)

    def test_template_drift_stops_assembly_instead_of_silently_skipping_routing(self):
        with patch.object(lab,'trial_identity',return_value=TRIAL):
            with self.assertRaises(RuntimeError): lab.final_four_asset('index.html','unrecognized replacement UI')
            with self.assertRaises(RuntimeError): lab.final_four_asset('ny-connector.js','unrecognized connector')

    def test_validation_shell_has_no_credential_and_script_compiles(self):
        import re
        text=(ROOT/'deployment/final-four-validation.html').read_text()
        self.assertIn('window.CCOptimized.run',text);self.assertIn('window.CCNYConnector.lookup',text)
        self.assertIn("mode==='sales'?cutoff*1000:900000",text)
        self.assertIn("row.sales_cutoff_seconds??60",text)
        self.assertNotIn('value="fixture',text)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'validation.js';p.write_text('\n'.join(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>',text,re.S)))
            result=subprocess.run([str(NODE),'--check',str(p)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_public_trial_test_shell_does_not_expose_api_or_old_pool_assets(self):
        class Base: pass
        master=types.SimpleNamespace(RegistrySnapshotHandler=Base)
        queue=Mock();handler_type=lab.build_handler(master,'fixture',durable=queue)
        for active in (TRIAL,None):
            with patch.object(lab,'trial_identity',return_value=active):
                for path in ['/connector/final-four-validation.html','/ny-connector.js','/api/lab/trial-export','/api/lab/metrics','/index.html']:
                    h=handler_type.__new__(handler_type);h.path=path;h.authorized=Mock(return_value=False)
                    h.send_response=Mock();h.send_header=Mock();h.end_headers=Mock();h.wfile=io.BytesIO()
                    h._get(True)
                    public=active and path in ['/connector/final-four-validation.html','/ny-connector.js']
                    if public:
                        h.authorized.assert_not_called();h.send_response.assert_called_once_with(200)
                        self.assertGreater(len(h.wfile.getvalue()),0)
                    else:
                        h.authorized.assert_called_once();h.send_response.assert_not_called()
        queue.transaction.assert_not_called();queue.metrics.assert_not_called()

    def test_trial_reserves_one_actual_browser_lane_without_reducing_other_state_capacity(self):
        payload={k:v for k,v in self.payload().items() if k!='request_id'}
        payload['external_state_slots']=1
        result=durable_queue.normalize_submission(payload,payload['states'])
        self.assertEqual(durable_queue.workflow_state_limit({'payload':result}),14)
        with self.assertRaises(ValueError):durable_queue.normalize_submission({**payload,'external_state_slots':6},payload['states'])

    def test_trial_submission_uses_supplied_queue_and_sends_no_browser_jobs_to_workers(self):
        master=types.SimpleNamespace(SUPPORTED_STATES=self.payload()['states'],APP_VERSION='fixture-performance-lab',
                                    NY_CONNECTOR_SIGNING_KEY='fixture-secret-'*4,canonical_ein_digits=cc.canonical_ein_digits)
        seen=[]
        def transport(path,payload,key):
            seen.append((path,payload,key));return {'id':'11111111-1111-1111-1111-111111111111'}
        with patch.object(workflows,'call',side_effect=AssertionError('Never use protected staging queue')):
            result=workflows.prepare(master,self.payload(),['fixture','device'],transport=transport,
                                     external_states={'IL','GA','AL','NC','NV','TN'},external_slots=1)
        self.assertEqual(result['external_states'],['AL','GA','IL','NC','NV','TN'])
        self.assertEqual(seen[0][1]['states'],['MA']);self.assertEqual(seen[0][1]['external_state_slots'],1)
        self.assertEqual(seen[0][1]['alternate_names'],['Example Foundation'])
        self.assertEqual(result['state_concurrency'],15)

    def test_original_submission_defaults_remain_two_browser_states(self):
        master=types.SimpleNamespace(SUPPORTED_STATES=['IL','GA','MA'],APP_VERSION='fixture-staging',
                                    NY_CONNECTOR_SIGNING_KEY='fixture-secret-'*4,canonical_ein_digits=cc.canonical_ein_digits)
        payload={**self.payload(),'states':['IL','GA','MA']}
        with patch.object(workflows,'call',return_value={'id':'11111111-1111-1111-1111-111111111111'}) as submit:
            result=workflows.prepare(master,payload,['fixture','device'])
        self.assertEqual(result['external_states'],['GA','IL']);self.assertEqual(submit.call_args.args[1]['external_state_slots'],2)

    def test_trial_connector_origin_never_falls_back_to_production(self):
        with patch.dict(cc.os.environ,{'CE_FINAL_FOUR_TRIAL':'1'}),patch.object(cc,'trial_identity',return_value=TRIAL):
            self.assertTrue(cc.ny_connector_origin_allowed(TRIAL['origin']))
            self.assertFalse(cc.ny_connector_origin_allowed('https://www.compliance-express.com'))
            self.assertFalse(cc.ny_connector_origin_allowed('https://staging.compliance-express.com'))
        with patch.dict(cc.os.environ,{'CE_FINAL_FOUR_TRIAL':'1'}),patch.object(cc,'trial_identity',return_value=None):
            self.assertFalse(cc.ny_connector_origin_allowed(TRIAL['origin']))

    def test_trial_routes_preserve_request_body_for_master_and_do_not_bypass_auth(self):
        class Base:
            def do_POST(self):
                return ('master',self.path,self.rfile.read())
        master=types.SimpleNamespace(RegistrySnapshotHandler=Base)
        handler_type=lab.build_handler(master,'fixture',durable=Mock())
        with patch.object(lab,'trial_identity',return_value=TRIAL):
            for path in ['/api/final-four-connector','/api/ny-connector','/api/discover-names','/api/identity-review','/api/report']:
                h=handler_type.__new__(handler_type);h.path=path;h.rfile=io.BytesIO(b'{"fixture":true}')
                h.authorized=lambda:True
                self.assertEqual(h.do_POST(),('master',path,b'{"fixture":true}'))
                h.rfile=io.BytesIO(b'{"fixture":true}');h.authorized=lambda:False
                self.assertIsNone(h.do_POST());self.assertEqual(h.rfile.tell(),0)

    def test_trial_public_review_is_signed_without_leaking_worker_context(self):
        row={'name':'Example Foundation','identifier':'X1','ein':'','location':'Boston MA','url':'https://example.test/X1',
             'raw_status':'Current','expiration':'2027-12-31','initial':'','_identity_outcome':'conflict'}
        data={'ein':'123456789','state':'ME','organization_name':'Example Foundation','comments':'Review location',
              'status':'Needs Review','app_version':'fixture-performance-lab'}
        with patch.object(cc,'trial_identity',return_value=TRIAL),patch.object(cc,'performance_origin_enabled',return_value=True), \
                patch.object(cc,'APP_VERSION','fixture-performance-lab'),patch.object(cc,'NY_CONNECTOR_SIGNING_KEY','fixture-'*8), \
                patch.dict(cc.os.environ,{'CE_AURORA_STAGING_BRIDGE':'1','CE_FINAL_FOUR_CHILD':''}):
            cc.attach_identity_review(data,{'records':[row],'search_complete':True})
            self.assertIn('identity_review',data);self.assertNotIn('_worker_identity_review',data)
            with patch.dict(cc.os.environ,{'CE_FINAL_FOUR_CHILD':'1'}):
                child={};cc.attach_identity_review(child,{'records':[row]})
                self.assertIn('_worker_identity_review',child);self.assertNotIn('identity_review',child)

    def test_trial_package_keeps_app_isolation_and_grants_only_the_reviewed_recovery_permissions(self):
        before=(ROOT/'browser-connector/manifest.json').read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'trial'
            result=build(TRIAL['origin'],output)
            manifest=json.loads((output/'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['version'],'0.6.68')
            self.assertEqual(manifest['permissions'],['storage','browsingData','cookies'])
            text=json.dumps(manifest)
            for banned in ['staging.compliance-express.com','www.compliance-express.com','<all_urls>']:
                self.assertNotIn(banned,text)
            self.assertIn('https://charities-search.ag.ny.gov/RegistrySearch*',manifest['host_permissions'])
            recovery=(output/'recovery.js').read_text(encoding='utf-8')
            self.assertIn('origins: [ORIGIN]',recovery)
            self.assertIn('cookie.hostOnly === true',recovery)
            self.assertEqual(next(c['matches'] for c in manifest['content_scripts'] if 'staging-bridge.js' in c['js']),[TRIAL['origin']+'/*'])
            self.assertTrue(Path(result['zip']).is_file())
            for file in output.glob('*.js'):
                r=subprocess.run([str(NODE),'--check',str(file)],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stderr)
            # Exercise the packaged channel and protocol together, not only
            # the collector in isolation. Reservation details cross both.
            r=subprocess.run([str(NODE),'--test',str(ROOT/'testing/run_ny_bridge_resume.cjs')],
                env={**os.environ,'CC_TEST_TRIAL_DIR':str(output),'CC_TEST_TRIAL_ORIGIN':TRIAL['origin']},
                capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            with self.assertRaises(ValueError):build(TRIAL['origin'],output)
        self.assertEqual((ROOT/'browser-connector/manifest.json').read_bytes(),before)

    def test_packager_rejects_approved_origins_and_non_https_destinations(self):
        with tempfile.TemporaryDirectory() as tmp:
            for origin in ['https://staging.compliance-express.com','https://instant-compliance-snapshot-api-hn4v.onrender.com',
                           'http://fixture.onrender.com','https://fixture.onrender.com.evil.test','https://fixture.onrender.com/path']:
                with self.assertRaises(ValueError):build(origin,Path(tmp)/'rejected')


if __name__=='__main__':unittest.main(verbosity=2)
