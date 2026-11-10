const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const text=fs.readFileSync(path.join(__dirname,'..','deployment','staging_connector','dc-boss-source.js'),'utf8');

function replay({selected=true,id='65000167',name='ARMY EMERGENCY RELIEF',loading=false,duplicates=0}={}){
 let tabClicks=0,recordClicks=0;
 const shown={getClientRects:()=>[{}]};
 const tab={...shown,innerText:'Licensing Results',getAttribute:()=>selected?'true':'false',click:()=>tabClicks++};
 const credential={...shown,innerText:id};
 const cells={'.mat-column-licenseNumber':credential,'.mat-column-licenseeName':{innerText:name},
  '.mat-column-licenseActivity':{innerText:'Charitable Solicitation'},
  '.mat-column-licenseeName a':{...shown,click:()=>recordClicks++},
  'td.mat-column-licenseNumber':credential};
 const row={...shown,querySelector:key=>cells[key]};
 const document={body:{innerText:''},querySelectorAll(key){
  if(key==='[role="tab"]')return [tab];
  if(key==='[role="progressbar"]')return loading?[shown]:[];
  if(key==='.mat-column-licenseNumber')return [credential];
  if(key==='table[aria-label="grid-table"] tr')return Array(1+duplicates).fill(row);
  return [];
 }};
 const context=vm.createContext({module:{exports:{}},document,getComputedStyle:()=>({visibility:'visible',display:'block'}),
  location:{href:'https://boss.dc.gov/business/business-license-search'}});
 vm.runInContext(text,context);
 const result=context.module.exports.pageStep({phase:'licensing',d:{identifier:'65000167',name:'ARMY EMERGENCY RELIEF'}});
 return {result,tabClicks,recordClicks};
}
test('selected licensing tab opens the exact record in the same observation',()=>{
 const {result,tabClicks,recordClicks}=replay();
 assert.equal(result.next,'metadata');assert.equal(tabClicks,0);assert.equal(recordClicks,1);
});
test('D.C. rejects conflicting rows and waits for loading before selecting',()=>{
 for(const fixture of [{id:'99999999'},{name:'OTHER ENTITY'},{duplicates:1}]){
  const {result,recordClicks}=replay(fixture);
  assert.equal(result.error,'selected_license_not_unique_or_absent');assert.equal(recordClicks,0);
 }
 const waiting=replay({loading:true});assert.equal(waiting.result.waiting,true);assert.equal(waiting.recordClicks,0);
 const switchTab=replay({selected:false});assert.equal(switchTab.result.next,'row');
 assert.equal(switchTab.tabClicks,1);assert.equal(switchTab.recordClicks,0);
});
