"""Assembled NY transport: same signed request, bounded retry, no extra search."""
import json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from deployment import performance_lab as lab

class Handoff(unittest.TestCase):
    def test_replaying_signed_advance_keeps_original_expiry_and_never_requeries_source(self):
        import copy
        import registry_snapshot_server as m
        from testing.run_ny_connector_guardrails import ConnectorTests,ROW,DETAIL
        harness=ConnectorTests('runTest');harness.setUp();self.addCleanup(harness.doCleanups)
        code,state=harness.request(action='start',organization_name=ROW['orgName'],ein=ROW['ein'],connector_version='0.5.10')
        self.assertEqual(code,200)
        original=m.ny_connector_unpack(state['check_token'],harness.auth['email'],harness.auth['device_id'])
        def submit(saved,rows):
            return harness.request(action='advance',check_token=saved['check_token'],query_id=saved['query_id'],
                evidence={'query':saved['query'],'http_status':200,'success':True,'statusCode':200,
                          ('detail' if 'orgID' in saved['query'] else 'rows'):copy.deepcopy(rows)})
        replies=[submit(state,[ROW]) for _ in range(2)]
        for code,response in replies:
            self.assertEqual(code,200);self.assertEqual(response['query'],{'orgID':ROW['orgID']})
            decoded=m.ny_connector_unpack(response['check_token'],harness.auth['email'],harness.auth['device_id'])
            self.assertEqual(decoded['issued'],original['issued']);self.assertEqual(decoded['expires'],original['expires'])
            self.assertEqual(len(decoded['completed']),1)
        detail_state=replies[-1][1]
        for _ in range(2):
            code,response=submit(detail_state,DETAIL)
            self.assertEqual(code,200);self.assertEqual(response['phase'],'complete')
            self.assertEqual(response['result']['status'],'Current')
        harness.session.get.assert_not_called()

    def test_assembled_assets_and_signed_advance_gateway_recovery(self):
        with patch.object(lab,'trial_identity',return_value={'origin':'https://fixture-final-four.onrender.com'}),patch.object(lab,'LAB_ORIGIN','https://fixture-final-four.onrender.com'):
            source=lab.lab_asset('/ny-connector.js')[0].decode('utf-8').replace('\r\n','\n')
            pages=[lab.lab_asset(path)[0].decode('utf-8') for path in ['/','/instant-compliance-snapshot']]
        start=source.index('    async function api(fields, cleanup = false) {')
        # The next outer try is after api's closing brace and precedes readiness.
        end=source.index('\n    try {\n      ',source.index('\n    }',start))+1
        api=source[start:end]
        script='''const assert=require('node:assert/strict');
const timeoutSignal={aborted:false};let timeoutCalls=0;
const AbortSignal={timeout:ms=>{assert.equal(ms,45000);timeoutCalls++;return timeoutSignal;},any:signals=>signals[signals.length-1]};
const API='https://fixture.invalid',credentials={email:'test',device_id:'device'},label='New York',finalFour=false,admin_passcode='offline-fixture';
let registryState='NY',signal=null,alEvidenceDeadline=0;
const onProgress=()=>{},trace=()=>{};
let statuses=[],requests=[];
const fetch=async(url,options)=>{requests.push({url,...options});const status=statuses.shift();return {status,ok:status===200,json:async()=>{if(status!==200)throw new SyntaxError('gateway');return {phase:'complete',result:{state:'NY'}}}}};
'''+api+'''
(async()=>{
 for(const first of [502,503,504,520,522,524]){
   statuses=[first,200];requests=[];timeoutCalls=0;timeoutSignal.aborted=false;
   const result=await api({action:'advance',check_token:'signed-test',query_id:'same-query',evidence:{rows:[]}});
   assert.equal(result.phase,'complete');assert.equal(requests.length,2);assert.equal(timeoutCalls,1);
   assert.equal(requests[0].body,requests[1].body);assert.equal(requests[0].signal,requests[1].signal);
   assert.deepEqual(requests[0].headers,requests[1].headers);assert.equal(requests[1].headers.Authorization,'Bearer offline-fixture');
 }
 for(const [state,action,first] of [['NY','start',520],['NC','advance',520],['NY','advance',403],['NY','advance',429]]){
   registryState=state;statuses=[first,200];requests=[];
   await assert.rejects(api({action,query_id:'q'}));assert.equal(requests.length,1);
 }
 registryState='NY';statuses=[520,520,200];requests=[];
 let failure;try{await api({action:'advance',query_id:'q'})}catch(e){failure=e}
 assert.equal(requests.length,2);assert.equal(failure.ccRegistryHandoffFailed,true);
 timeoutSignal.aborted=true;statuses=[520,200];requests=[];
 await assert.rejects(api({action:'advance',query_id:'q'}));assert.equal(requests.length,1);
 console.log('NY signed handoff controls passed');
})().catch(e=>{console.error(e);process.exitCode=1});'''
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'test.js';p.write_text(script,encoding='utf-8')
            completed=subprocess.run(['node',str(p)],capture_output=True,text=True)
        self.assertEqual(completed.returncode,0,completed.stderr)
        for page in pages:
            self.assertIn('NY_RESULT_SUBMISSION_FAILED',page)
            self.assertIn('reviewed_alternate_names = [...alternateNames]',page)

if __name__=='__main__':unittest.main()
