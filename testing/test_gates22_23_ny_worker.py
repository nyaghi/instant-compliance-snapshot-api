"""Execute the actual candidate worker query loop with fake Chrome transport."""
import os,json,subprocess,tempfile,unittest
from pathlib import Path

class WorkerRecovery(unittest.TestCase):
    def test_one_fresh_owned_page_for_later_http400_with_original_deadline(self):
        root=Path(os.environ['CC_CANDIDATE_CONNECTOR'])
        source=(root/'worker.js').read_text(encoding='utf-8')
        function=source[source.index('async function performSearch('):source.index('async function performRefresh(')]
        script=r'''const assert=require('node:assert/strict');
let clock=10000;const Date={now:()=>clock};
const P={TRIAL_ORIGIN:true,NY:'https://charities-search.ag.ny.gov',sameQuery:(a,b)=>JSON.stringify(a)===JSON.stringify(b),nyDiagnostics:x=>x||[]};
const wfAwait=async(j,s,f)=>f(),wfReturn=(j,s,v)=>v;
const saveRuntime=async()=>{},awaitSnapshotCleanup=async()=>{},ready=async()=>{},prepareNySearchForm=async()=>{},openDetail=async()=>{};
const isActive=j=>!j.closed,post=(j,r)=>j.posts.push(r),diagnostic=()=>{},rejected=()=>false;
const collectNyDiagnostics=(j,r)=>{j.nyDiagnostics=r?.ny_diagnostics||[]};
const repair={phase:'idle',nextAllowedAt:0};
let sent=[],removed=[],replies=[];
const nap=async ms=>{clock+=ms};
const lookupTab=async j=>{if(j.tab===null)j.tab=22};
const removeOwned=async id=>removed.push(id);
const close=j=>{j.closed=true};
const chrome={tabs:{get:async()=>({url:P.NY+'/RegistrySearch'}),sendMessage:async(tab,request)=>{
 sent.push({tab,request});return replies.shift();
}}};
'''+function+r'''
const query={orgName:'Example Foundation'};
const failure=status=>({ok:false,reason:'NY_CONNECTOR_SEARCH_HTTP_ERROR',verificationRetryUsed:true,
 ny_diagnostics:[{stage:'search',event:'response',http_status:status}]});
const success={ok:true,evidence:{query,rows:[]}};
const make=()=>({registryState:'NY',tab:11,generation:4,rateRetries:0,timeoutRetries:0,
 activeExpiresAt:110000,verificationRetryUsed:false,nyLastSearchQuery:{ein:'123456789'},posts:[]});
async function run(job,answers,q=query){sent=[];removed=[];replies=answers;await performSearch(job,q,'command-2');return job;}
(async()=>{
 let j=make();const expiry=j.activeExpiresAt;
 await run(j,[failure(400),success]);
 assert.equal(sent.length,2);assert.deepEqual(sent[0].request.query,sent[1].request.query);
 assert.deepEqual(removed,[11]);assert.deepEqual(sent.map(x=>x.tab),[11,22]);
 assert.equal(j.timeoutRetries,1);assert.equal(j.generation,5);assert.equal(j.activeExpiresAt,expiry);
 assert.equal(sent[1].request.verificationRetryUsed,true);assert.equal(j.lastResponse.ok,true);
 j=make();await run(j,[failure(400),failure(400),success]);
 assert.equal(sent.length,2);assert.equal(j.lastResponse.reason,'NY_CONNECTOR_SEARCH_HTTP_ERROR');assert.equal(j.closed,true);
 for(const [status,changes] of [[400,{nyLastSearchQuery:null}],[400,{timeoutRetries:1}],
          [400,{activeExpiresAt:clock+15000}],[403,{}],[500,{}]]){
  j=Object.assign(make(),changes);await run(j,[failure(status),success]);assert.equal(sent.length,1);assert.deepEqual(removed,[]);
 }
 j=make();await run(j,[failure(400)],{orgID:'12-34-56'});assert.equal(sent.length,1);assert.deepEqual(removed,[]);
 j=make();j.closed=true;await run(j,[failure(400),success]);assert.equal(sent.length,0);
 console.log('Actual NY worker recovery controls passed');
})().catch(e=>{console.error(e);process.exitCode=1});'''
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'worker-test.js';target.write_text(script,encoding='utf-8')
            result=subprocess.run(['node',str(target)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
