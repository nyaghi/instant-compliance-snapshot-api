const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('node:assert/strict');
const {spawnSync}=require('node:child_process');const root=path.resolve(__dirname,'..');
const loaded=spawnSync('python',['-m','testing.dc_period_frontend_cases'],{cwd:root,encoding:'utf8'});assert.equal(loaded.status,0,loaded.stderr);
const cases=JSON.parse(loaded.stdout),source=fs.readFileSync(path.join(root,'deployment/staging_connector/dc-boss-source.js'),'utf8');
const api=require('../deployment/staging_connector/dc-boss-source.js');
function fields(input){const d=input.base.desktop_evidence_request,p=input.update.dc_source_reconciliation;
 return {Licensee:p.source_name,'Trade Name':'N/A','License Category':'Charitable Services','License Activity':'Charitable Solicitation',
  'License Number':d.identifier,'Premise Address':'Modeled corroborated office','License Status':'Active','Issue Date':'10/30/2026','Expiration Date':'10/31/2028'};
}
const text=f=>'License Information\n'+Object.entries(f).map(([k,v])=>k+'\n'+v).join('\n')+'\nLicensee Information\n';
async function transport(input,mode){
 let now=Date.now(),step=0;const calls=[],removed=[],detached=[],d={...input.base.desktop_evidence_request},f=fields(input),url='https://boss.dc.gov/licensing/license-details';
 if(mode==='expired')d.expires_at=now/1000-1;
 const chrome={windows:{create:async options=>{assert.equal(options.url,d.url);calls.push('create');return{id:70,tabs:[{id:80}]};},remove:async id=>removed.push(id)},debugger:{attach:async()=>{},detach:async target=>detached.push(target.tabId),sendCommand:async(target,method,params)=>{
  calls.push(method);
  if(method==='Runtime.evaluate'){
   if(mode==='verification')return {result:{value:JSON.stringify({error:'source_verification_required'})}};
   if(step<6)return {result:{value:JSON.stringify({next:['option','fill','submit','licensing','row','metadata'][step++]})}};
   const shown=mode==='changed'&&calls.includes('Page.captureScreenshot')?{...f,'Expiration Date':'10/31/2030'}:f;
   return {result:{value:JSON.stringify({url,ready:'complete',text:text(shown),position:{x:0,y:0,width:1280,content:[]}})}};
  }
  if(method==='Page.getLayoutMetrics')return {cssContentSize:{width:1280,height:1000}};
  if(method==='Page.captureScreenshot')return {data:'bW9kZWxlZC1waXhlbHM='};
  return {};
 }}};
 class Clock extends Date{static now(){return now;}}
 const ctx={module:{exports:{}},chrome,Date:Clock,URL,console,
  CCSourceRail:{acquire:async()=>null,create:async(_,options)=>chrome.windows.create(options),release:async()=>{}},
  setTimeout:(fn,ms)=>ms===100?setTimeout(()=>{now+=100;fn();},1):setTimeout(fn,ms),clearTimeout};
 vm.runInNewContext(source,ctx);const result=await ctx.module.exports.capture(d);
 if(mode==='good'){assert.equal(result.ok,true,JSON.stringify(result));assert.deepEqual(JSON.parse(JSON.stringify(result.source_fields)),f);}
 else{assert.equal(result.ok,false);if(mode==='changed')assert.equal(result.reason,'selected_detail_changed');}
 if(mode==='expired')assert.equal(calls.includes('create'),false);
 else{assert.deepEqual(removed,[70]);assert.deepEqual(detached,[80]);}
 return result;
}
(async()=>{
 const count={contexts:cases.length,field_pairs:0,field_rejections:0,transport_recoveries:0,transport_rejections:0,owned_cleanups:0,live_queries:0};
 for(const item of cases){
  const d=item.base.desktop_evidence_request,f=fields(item);assert.equal(api.valid(d),true);
  assert.deepEqual(api.fields('https://boss.dc.gov/licensing/license-details',text(f),d),f);count.field_pairs++;
  for(const [key,value]of [['Licensee','Other Foundation'],['License Number','999999'],['License Status','Revoked'],['License Activity','Charitable Exempt'],['Expiration Date','10/31/2025'],['Expiration Date','02/30/2028'],['Issue Date','10/30/2030']]){
   assert.equal(api.fields('https://boss.dc.gov/licensing/license-details',text({...f,[key]:value}),d),null,key);count.field_rejections++;
  }
  for(const mode of ['good','changed','verification','expired']){
   await transport(item,mode);if(mode==='good')count.transport_recoveries++;else count.transport_rejections++;
   if(mode!=='expired')count.owned_cleanups++;
  }
 }
 console.log(JSON.stringify(count));
})().catch(error=>{console.error(error);process.exitCode=1});
