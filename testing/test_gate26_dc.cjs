const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require.resolve('../deployment/staging_connector/dc-boss-source.js'),'utf8');
async function run(mode){
 const now=Date.now()/1000,d={state:'DC',operation:'detail',url:'https://boss.dc.gov/business/business-license-search',ein:'133377893',run_id:'b'.repeat(32),deadline_schema:1,issued_at:now-1,expires_at:now+60,name:'RAINFOREST ALLIANCE INC',identifier:'40003378',raw_status:mode==='undated-active'?'Active':'Expired',expiration:''};
 const fields={'Licensee':d.name,'Trade Name':'N/A','License Category':'Charitable Services','License Activity':'Charitable Solicitation','License Number':d.identifier,'Premise Address':'N/A','License Status':'Expired','Issue Date':'10/05/2010','Expiration Date':'N/A'};
 let shots=0,removed=0,detached=0;
 const chrome={windows:{remove:async()=>removed++},debugger:{attach:async()=>{},detach:async()=>detached++,sendCommand:async(_,method,p)=>{
  if(method==='Runtime.evaluate'){
   const arg=JSON.parse(p.expression.slice(p.expression.lastIndexOf(')(')+2,-2));
   if(arg.phase==='type')return {result:{value:JSON.stringify({next:'metadata'})}};
   const f={...fields};if(mode==='wrong-id'||mode==='changed'&&shots)f['License Number']='99999999';
   if(mode==='wrong-status')f['License Status']='Active';
   const text='License Information\n'+Object.entries(f).map(([k,v])=>k+'\n'+v).join('\n')+'\nLicensee Information\n';
   return {result:{value:JSON.stringify({url:'https://boss.dc.gov/licensing/license-details',ready:'complete',text,capture_fit:{ok:mode!=='clipped'},position:{x:0,y:0,width:1280,content:[]}})}};
  }
  if(method==='Page.getLayoutMetrics')return {cssContentSize:{width:1280,height:1000}};
  if(method==='Page.captureScreenshot'){shots++;return {data:'bW9kZWxlZA=='};}return {};
 }}};
 let clock=Date.now();class Clock extends Date{static now(){return clock;}}
 const context={module:{exports:{}},chrome,Date:Clock,URL,setTimeout:(fn,ms)=>ms===100?setTimeout(()=>{clock+=100;fn();},1):setTimeout(fn,ms),clearTimeout,CCSourceRail:{acquire:async()=>null,create:async()=>({id:1,tabs:[{id:2}]}),release:async()=>{}}};
 vm.runInNewContext(source,context);const result=await context.module.exports.capture(d);
 assert.equal(result.ok,mode==='good',JSON.stringify(result));
 assert.equal(removed,mode==='undated-active'?0:1);assert.equal(detached,mode==='undated-active'?0:1);
 if(mode==='good'){assert.equal(shots,1);assert.equal(result.source_fields['Expiration Date'],'N/A');assert.equal(result.source_fields['License Status'],'Expired');}
}
(async()=>{for(const mode of ['good','undated-active','wrong-id','wrong-status','changed','clipped'])await run(mode);console.log('6 undated-expiry capture and rejection controls passed; no live queries');})().catch(e=>{console.error(e);process.exitCode=1});
