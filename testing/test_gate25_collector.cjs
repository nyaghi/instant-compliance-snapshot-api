/* Actual packaged capture state machine, observed text and mocked Chrome only. */
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict'),path=require('path');
const source=fs.readFileSync(path.join(__dirname,'../deployment/staging_connector/dc-boss-source.js'),'utf8');
const api=require('../deployment/staging_connector/dc-boss-source.js');
const license=fs.readFileSync(path.join(__dirname,'fixtures/gate25/dc-license.txt'),'utf8');
const corporate=fs.readFileSync(path.join(__dirname,'fixtures/gate25/dc-corporate.txt'),'utf8');
async function run(mode){
 const now=Date.now()/1000,q={state:'DC',operation:'detail',url:'https://boss.dc.gov/business/business-license-search',ein:'870361394',run_id:'a'.repeat(32),deadline_schema:1,issued_at:now-1,expires_at:now+60,name:'SUNDANCE INSTITUTE',identifier:'400212000168',raw_status:'Expired - Enforcement',expiration:'2020-02-29',corporate_continuity_schema:2,corporate_continuity_candidate:{identifier:'400222000224',name:'SUNDANCE',raw_status:'Active',expiration:'2028-02-28'},corporate_link_proof:{names:['Sundance Institute'],addresses:[{street:'PO BOX 684429',region:'UT',postal:'84068'}]}};
 let removed=0,detached=0,shots=0,linked=false;
 const chrome={windows:{remove:async()=>removed++},debugger:{attach:async()=>{},detach:async()=>detached++,sendCommand:async(_,method,p)=>{
  if(method==='Runtime.evaluate'){
   const arg=JSON.parse(p.expression.slice(p.expression.lastIndexOf(')(')+2,-2));
   if(arg.phase==='corporate_open'){linked=true;return {result:{value:JSON.stringify(mode==='no-link'?{error:'corporate_link_not_unique'}:{next:'corporate_metadata'})}};}
   const isCorporate=arg.phase.startsWith('corporate_');
   const observed=isCorporate?{url:'https://boss.dc.gov/business/info',ready:'complete',text:mode==='wrong-name'?corporate.replace('SUNDANCE INSTITUTE','OTHER INSTITUTE'):corporate,fit:mode!=='clipped'}:
    {url:'https://boss.dc.gov/licensing/license-details',ready:'complete',text:license,capture_fit:{ok:true},position:{x:0,y:0,width:1280,content:[]}};
   if(mode==='changed'&&isCorporate&&shots===2)observed.text=observed.text.replace('SUNDANCE INSTITUTE','OTHER INSTITUTE');
   return {result:{value:JSON.stringify(arg.phase==='type'?{next:'metadata'}:observed)}};
  }
  if(method==='Page.getLayoutMetrics')return {cssContentSize:{width:1280,height:1600}};
  if(method==='Page.captureScreenshot'){shots++;return {data:'bW9kZWxlZA=='};}
  return {};
 }}};
 const context={module:{exports:{}},chrome,Date,URL,setTimeout,clearTimeout,CCSourceRail:{acquire:async()=>null,create:async()=>({id:1,tabs:[{id:2}]}),release:async()=>{}}};
 vm.runInNewContext(source,context);const result=await context.module.exports.capture(q);
 assert.equal(result.ok,mode==='good',JSON.stringify(result));assert.equal(removed,1);assert.equal(detached,1);assert.equal(linked,true);
 if(mode==='good'){assert.equal(shots,2);assert.equal(result.current_license.request.identifier,'400222000224');assert.equal(result.request.identifier,'400212000168');assert.equal(result.corporate_detail.linked_identifier,'N0000001384');}
}
(async()=>{for(const mode of ['good','wrong-name','no-link','clipped','changed'])await run(mode);assert.equal(api.corporateFields('https://other.example/',corporate),null);console.log('5 linked capture/cleanup cases and wrong-route guard passed; no live queries');})().catch(e=>{console.error(e);process.exitCode=1});
