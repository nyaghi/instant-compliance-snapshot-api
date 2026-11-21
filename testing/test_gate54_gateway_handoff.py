"""Saved-evidence gateway recovery: 70 recorded inputs per browser state."""
import json,os,subprocess,sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from deployment import performance_lab as lab

class GatewayHandoff(unittest.TestCase):
    def test_70_inputs_each_state_reuses_body_and_original_timeout(self):
        origin='https://fixture-final-four.onrender.com'
        with patch.object(lab,'trial_identity',return_value={'origin':origin}),patch.object(lab,'LAB_ORIGIN',origin):
            source=lab.final_four_asset('ny-connector.js',(ROOT/'web-staging/ny-connector.js').read_text(encoding='utf-8'))
        start=source.index('    async function api(fields, cleanup = false) {')
        end=source.index('\n    try {\n      ',source.index('\n    }',start))+1
        api=source[start:end]
        cases=json.loads((ROOT/'testing/fixtures/gate54-state-controls.json').read_text())['cases']
        program=r'''
const assert=require('node:assert/strict');
const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
let timeoutSignal={aborted:false},timeoutCalls=0;
const AbortSignal={timeout:ms=>{assert.equal(ms,45000);timeoutCalls++;return timeoutSignal;},any:signals=>signals.at(-1)};
const API='https://fixture.invalid',credentials={email:'offline',device_id:'device'},finalFour=true,admin_passcode='offline-fixture';
let registryState='TN',label='Tennessee',signal=null,alEvidenceDeadline=0,extensionRefresh=null,alertLease=null;
const onProgress=()=>{},trace=()=>{};
let statuses=[],requests=[];
const fetch=async(url,options)=>{requests.push({url,...options});const status=statuses.shift();return {status,ok:status===200,json:async()=>{if(status!==200)throw new SyntaxError('gateway');return {phase:'complete',result:{state:registryState,status:'Current'}}}}};
API_FUNCTION
(async()=>{
let contexts=0;
for(const state of ['NY','IL','GA','AL','NC','NV','TN','NM','MS'])for(const org of input.cases){
 registryState=state;label=state;
 const fields={action:'advance',check_token:'local-signed-continuation',query_id:'same-query',evidence:{name:org.name,ein:org.ein,rows:[]}};
 for(const status of [502,503,504,520,522,524]){
  statuses=[status,200];requests=[];timeoutCalls=0;timeoutSignal={aborted:false};signal=null;
  const result=await api(fields);
  assert.equal(result.phase,'complete');assert.equal(requests.length,2);assert.equal(timeoutCalls,1);
  assert.equal(requests[0].body,requests[1].body);assert.equal(requests[0].signal,requests[1].signal);
  assert.equal(requests[0].url,requests[1].url);assert.deepEqual(requests[0].headers,requests[1].headers);
 }
 for(const [action,status,cleanup] of [['start',520,false],['advance',403,false],['advance',429,false],['advance',400,false],['advance',520,true]]){
  statuses=[status,200];requests=[];timeoutSignal={aborted:false};
  await assert.rejects(api({...fields,action},cleanup));assert.equal(requests.length,1);
 }
 statuses=[520,520,200];requests=[];timeoutSignal={aborted:false};
 await assert.rejects(api(fields));assert.equal(requests.length,2);
 statuses=[520,200];requests=[];timeoutSignal={aborted:true};
 await assert.rejects(api(fields));assert.equal(requests.length,1);
 statuses=[520,200];requests=[];timeoutSignal={aborted:false};signal={aborted:true};
 await assert.rejects(api(fields));assert.equal(requests.length,1);signal=null;
 statuses=[200];requests=[];timeoutSignal={aborted:false};
 await api(fields);assert.equal(requests.length,1);
 contexts++;
}
console.log(JSON.stringify({passed:true,recorded_organizations_per_state:70,states:9,contexts,scope:'Synthetic transport responses; same saved evidence, no browser search or live state calls.'}));
})().catch(e=>{console.error(e);process.exitCode=1;});
'''.replace('API_FUNCTION',api)
        node=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
        result=subprocess.run([str(node),'-e',program],input=json.dumps({'cases':cases}),text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        out=Path(os.environ.get('CC_GATE54_TEST_OUTPUT',str(ROOT)));out.mkdir(exist_ok=True,parents=True)
        (out/'GATEWAY-70-EACH-STATE.json').write_text(json.dumps(json.loads(result.stdout),indent=2))

if __name__=='__main__':unittest.main()
