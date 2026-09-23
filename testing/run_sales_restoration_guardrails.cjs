const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm'), cp = require('node:child_process');
const root = path.join(__dirname,'..');
const html = fs.readFileSync(path.join(root,'web-staging/index.html'),'utf8');
const sales = require('../web-staging/sales-mode.js');
const allStates = [...html.matchAll(/name="states"\s+value="([A-Z]{2})"/g)].map(m=>m[1]);
function setup() {
  const elements = {};
  const get = id => elements[id] ||= {value: id==='salesScope' ? 'sales-ein' : '', events:{}, classList:{toggle(){}}, setAttribute(k,v){this[k]=v}, addEventListener(k,fn){this.events[k]=fn}};
  const boxes = allStates.map(value=>({value,checked:['MA','DC','RI'].includes(value)}));
  const context = {window:{CCSales:sales,CCIdentity:{ready:()=>false}}, document:{getElementById:get},
    stateCheckboxes:boxes, internalUnlocked:true, STAGING_ACCESS_REQUIRED:true, email:{value:'test@example.test'},
    isComplianceExpressEmail:()=>true, selectedStates:()=>boxes.filter(b=>b.checked).map(b=>b.value),
    selectAllStatesButton:get('all'),clearStatesButton:get('clear'),submitButton:get('submit')};
  vm.createContext(context);
  vm.runInContext(html.slice(html.indexOf('    let workflowRunning ='),html.indexOf('    window.CCIdentityConfig ='))+html.match(/    function namesRequired\(\).*\n/)[0],context);
  return {context,elements,boxes,run:code=>vm.runInContext(code,context)};
}
test('Standard defaults to reviewed names; Sales chooses 16 EIN states; returning restores the exact Standard selection',()=>{
  assert.equal(allStates.length,32);
  const c=setup();c.run('updateWorkflowMode()');assert.equal(c.elements.standardMode['aria-pressed'],'true');assert.equal(c.elements.submit.disabled,true);
  c.elements.salesMode.events.click();assert.equal(c.boxes.filter(b=>b.checked).length,16);assert.equal(c.elements.organizationIdentity.hidden,true);
  assert.equal(c.elements.submit.disabled,false);assert.equal(c.elements.salesMode['aria-pressed'],'true');
  assert(!c.boxes.find(b=>b.value==='DC').checked);assert(!c.boxes.find(b=>b.value==='RI').checked);
  c.elements.standardMode.events.click();assert.deepEqual(c.boxes.filter(b=>b.checked).map(b=>b.value),['DC','MA','RI']);assert.equal(c.elements.submit.disabled,true);
});
test('all-state Sales includes DC and RI and still requires alternate-name review',()=>{
  const c=setup();c.elements.salesScope.value='sales-all';c.elements.salesMode.events.click();
  assert.equal(c.boxes.filter(b=>b.checked).length,32);assert.equal(c.elements.organizationIdentity.hidden,false);assert.equal(c.elements.submit.disabled,true);
  assert.match(sales.scopeText(allStates,allStates,32),/All 32 supported/);
});
test('in-flight checks cannot change mode or enable a second submission',()=>{
  const c=setup();c.elements.salesMode.events.click();c.run('workflowRunning=true;updateWorkflowMode()');
  assert.equal(c.elements.standardMode.disabled,true);assert.equal(c.elements.salesScope.disabled,true);assert.equal(c.elements.submit.disabled,true);
  c.elements.standardMode.events.click();assert.equal(c.run('selectedMode()'),'sales-ein');
});
test('Sales cannot bypass the existing access gate',()=>{
  const c=setup();c.context.internalUnlocked=false;c.elements.salesMode.events.click();c.run('updateWorkflowMode()');
  assert.equal(c.run('selectedMode()'),'detailed');assert.equal(c.elements.workflowOptions.hidden,true);
});
test('actual UI scheduler retains sequential Standard checks and restored three-lane Sales, with independent NY',async()=>{
  for(const mode of ['detailed','sales-all','sales-ein']) {
    let active=0,peak=0;const calls=[];
    const context={window:{CCSales:sales},activeResultMode:mode,progressCount:{},progressBar:{style:{}},renderResults(){},stateLaneBases:()=>[],
      checkSingleState:async(b,e,m,state)=>{calls.push(state);if(state!=='NY')peak=Math.max(peak,++active);await new Promise(r=>setTimeout(r,3));if(state!=='NY')active--;return {state,organization_name:'Control',status:'Current'}}};
    vm.createContext(context);const start=html.indexOf('    async function runStateChecks(');
    vm.runInContext(html.slice(start,html.indexOf('\n    stateCheckboxes.forEach',start)),context);
    const result=await context.runStateChecks(['AK','CA','CO','DC','RI','NY'],'123456789','test@example.test','Control');
    assert.equal(peak,mode==='detailed'?1:3);assert.equal(calls[0],'NY');assert.deepEqual(Array.from(result,r=>r.state),['AK','CA','CO','DC','RI','NY']);
  }
});
test('master, discovery, connector, identity request payload and date/report metadata are preserved',()=>{
  const previous=cp.execFileSync('git',['show','e069ad6:web-staging/index.html'],{cwd:root,encoding:'utf8'}).replaceAll('\r\n','\n');
  const clean=html.replaceAll('\r\n','\n');
  for(const [start,end] of [['    async function requestSingleState(','    async function runStateChecks('],['    async function generateReport(','    function downloadExcel(']]) {
    const section=t=>t.slice(t.indexOf(start),t.indexOf(end));assert.equal(section(clean),section(previous));
  }
  for(const file of ['registry_snapshot_server.py','web-staging/organization-identity.js','web-staging/ny-connector.js']) {
    const old=cp.execFileSync('git',['show','e069ad6:'+file],{cwd:root,encoding:'utf8',maxBuffer:20*1024*1024}).replaceAll('\r\n','\n');
    assert.equal(fs.readFileSync(path.join(root,file),'utf8').replaceAll('\r\n','\n')===old,true,file);
  }
});
