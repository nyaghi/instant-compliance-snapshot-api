const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const os=require('node:os');
const vm=require('node:vm');const {execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'cc-prod-web-'));
const python=process.env.CC_TEST_PYTHON||'C:/Users/nyagh/.codex/worktrees/charityclarity-refresh-20260913/.venv/Scripts/python.exe';
execFileSync(python,[path.join(root,'deployment/prepare_web_release.py'),'--environment','production','--out',temp],{stdio:'ignore'});
const html=fs.readFileSync(path.join(temp,'instant-compliance-snapshot.html'),'utf8');
const fn=html.slice(html.indexOf('async function requestSingleState('),html.indexOf('function stateLaneBases('));
test('production overlay preserves 20.6 scope and marketing homepage',()=>{
  assert.equal(fs.existsSync(path.join(temp,'index.html')),false);
  assert.ok(html.includes('CharityClarity v2026.09.20.6'));
  for(const forbidden of ['$49','buy.stripe.com','&middot; Staging','sales-mode.js','registration_date','https://staging.compliance-express.com','https://instant-compliance-snapshot-api-staging'])assert.equal(html.includes(forbidden),false,forbidden);
  assert.ok(html.includes('info@compliance-express.com'));
});
for(const origin of ['https://www.compliance-express.com','https://compliance-express.com'])test('production page routes NY through the existing connector at '+origin,async()=>{
  const calls=[];const context=vm.createContext({window:{location:{origin},CCNYConnector:{lookup:async input=>{calls.push(input);return {status:'Current'};}}},lastNyInput:null,adminPasscode:{value:'test-only'},getDeviceId:()=> 'test-device',runAlternateNames:['Verified Former Name'],fallbackResult:()=>({}),fetch:()=>{throw Error('NY must use connector');}});
  vm.runInContext(fn,context);
  const result=await context.requestSingleState('https://instant-compliance-snapshot-api-public.onrender.com','123456789','test@example.com','NY','Example Organization');
  assert.equal(result.status,'Current');assert.equal(calls.length,1);assert.equal(calls[0].ein,'123456789');assert.deepEqual(Array.from(calls[0].alternate_names),['Verified Former Name']);
});
test('ordinary production state request retains evidence and production attribution',async()=>{
  let payload;const context=vm.createContext({window:{location:{origin:'https://www.compliance-express.com',href:'https://www.compliance-express.com/instant-compliance-snapshot.html'}},document:{referrer:''},navigator:{userAgent:'test'},adminPasscode:{value:'test-only'},getDeviceId:()=> 'test-device',runAlternateNames:['Verified Former Name'],attribution:{},AbortController,setTimeout,clearTimeout,fetch:async(url,options)=>{payload=JSON.parse(options.body);return{ok:true,text:async()=>JSON.stringify({results:[{status:'Upcoming Filing',comments:'Original evidence'}]})};}});
  vm.runInContext(fn,context);const result=await context.requestSingleState('https://instant-compliance-snapshot-api-public.onrender.com','123456789','test@example.com','CO','Example Organization');
  assert.equal(payload.environment,'production');assert.deepEqual(payload.alternate_names,['Verified Former Name']);assert.equal(result.status,'Upcoming Filing');assert.equal(result.comments,'Original evidence');
});
process.on('exit',()=>{const absolute=path.resolve(temp);if(path.dirname(absolute)===path.resolve(os.tmpdir())&&path.basename(absolute).startsWith('cc-prod-web-'))fs.rmSync(absolute,{recursive:true,force:true});});
