// Run the real assembled report handler in a DOM fixture, without browser I/O.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),cp=require('node:child_process'),path=require('node:path');
const root=path.resolve(__dirname,'..');
const script="from unittest.mock import patch; from deployment import performance_lab as l; c=patch.object(l,'trial_identity',return_value={'origin':'https://charityclarity-final-four-29-2.onrender.com'}); d=patch.object(l,'LAB_ORIGIN','https://charityclarity-final-four-29-2.onrender.com'); c.start(); d.start(); print(l.lab_asset('/')[0].decode('utf-8'))";
const html=cp.execFileSync('py',['-c',script],{cwd:root,encoding:'utf8',maxBuffer:1024*1024});
const source=html.slice(html.indexOf('    async function generateReport()'),html.indexOf('    function downloadExcel()'));
const packet=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/connected-hospital/report-payload.json'),'utf8'));
function setup({headStart=true,mismatch=false,invalidType=false,cacheFailure=false}={}){
  const calls=[],downloads=[],button={disabled:false},message={textContent:''};let saves=0;
  const context={latestResults:structuredClone(packet.results),generateReportButton:button,reportMessage:message,submitButton:{disabled:true},email:{value:'fixture@example.test'},adminPasscode:{value:'fixture-not-a-real-credential'},API_BASE:'https://charityclarity-final-four-29-2.onrender.com',AbortController,setTimeout:()=>1,clearTimeout(){},URL:{createObjectURL:()=> 'blob:fixture',revokeObjectURL(){}},document:{body:{appendChild(){}},createElement:()=>({click(){downloads.push(this.download);},remove(){}})},fetch:async(url,options)=>{calls.push({url,headers:options.headers,body:JSON.parse(options.body)});return {ok:true,headers:{get:()=>invalidType?'text/html':'application/pdf'},blob:async()=>({type:'application/pdf'})};},window:{CCHeadStart:headStart?{save:async()=>{saves++;if(cacheFailure)throw Error('Cache unavailable');},forResults:()=>{if(mismatch)throw Error('Head Start and Aurora must use the same organization and EIN.');return structuredClone(packet.head_start);}}:undefined}};
  vm.createContext(context);vm.runInContext(source+'\nthis.run=generateReport;',context);
  return {context,button,message,calls,downloads,get saves(){return saves;}};
}
test('Connect to Insight sends the complete snapshot and downloads the combined filename',async()=>{
  const c=setup();await c.context.run();assert.equal(c.saves,1);assert.equal(c.calls.length,1);assert.equal(c.calls[0].url,c.context.API_BASE+'/api/report');assert.equal(c.calls[0].body.head_start.requirements.length,51);assert.equal(c.calls[0].body.results.length,8);assert.equal(c.calls[0].headers.Authorization,'Bearer fixture-not-a-real-credential');assert.match(c.downloads[0],/^CharityClarity Insight-012345678-/);assert.match(c.message.textContent,/PDF downloaded/);assert.equal(c.button.disabled,false);
  await c.context.run();assert.equal(c.downloads.length,2,'A disabled Standard name-review button cannot block repeat Sales downloads');
});
test('identity mismatch remains visible and cannot create a mixed report',async()=>{
  const c=setup({mismatch:true});await c.context.run();assert.equal(c.calls.length,0);assert.equal(c.downloads.length,0);assert.match(c.message.textContent,/same organization/);assert.equal(c.context.latestResults.length,8);
});
test('unexpected HTML cannot be presented as a downloaded PDF',async()=>{
  const c=setup({invalidType:true});await c.context.run();assert.equal(c.downloads.length,0);assert.match(c.message.textContent,/did not return a PDF/);assert.equal(c.button.disabled,false);
});
test('standalone Aurora reports retain their original input and filename',async()=>{
  const c=setup({headStart:false});await c.context.run();assert.equal(c.calls[0].body.head_start,undefined);assert.match(c.downloads[0],/^CharityClarity Aurora-/);assert.equal(c.context.latestResults.length,8);
});
test('an optional assessment cache failure cannot block a valid Insight download',async()=>{
  const c=setup({cacheFailure:true});await c.context.run();assert.equal(c.downloads.length,1);assert.equal(c.calls[0].body.head_start.requirements.length,51);assert.equal(c.context.latestResults.length,8);
});
