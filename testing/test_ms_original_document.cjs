const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const roster=require('./fixtures/gate55/LOCAL-70.json');
const js=fs.readFileSync(path.join(__dirname,'../deployment/staging_connector/ms-original-document.js'),'utf8');
const base='https://charities.sos.ms.gov/online/portal/ch/page/charities-search/';
const url=base+'~/ViewXSLTFileByName.aspx?providerName=CH_EntityBasedFilingDetails&FilingId=f8f6506f-5e86-446a-96a1-1ff7408d992d';
const image='/9j/'+Buffer.alloc(120,1).toString('base64');
async function check(org,mode) {
  const q={state:'MS',operation:'detail',identifier:org.ein.replace(/\D/g,'')};
  const binding=JSON.stringify([org.name,'Filing Number:',q.identifier,'Filing Status:','Current','Initial Date Filed:','','Expiration Date:','05/15/2027']);
  const meta={url:base+'Portal.aspx',source_ms_detail_ready:true,source_ms_binding:binding,source_ms_document_url:url,document_id:'doc',public_text:org.name};
  const job={activeExpiresAt:Date.now()+30000,tab:3,generation:1,pending:'a',command:{id:'a',query:q},msSnapshotSpentMs:400,requiredCaptureSpentByState:{MS:400}};
  let created=0,closed=0,reads=0,captures=0,detached=0;
  const ctx={Date,JSON,Math,Promise,setTimeout,clearTimeout,P:{TRIAL_ORIGIN:true,sameQuery:(a,b)=>a===b},isActive:()=>true,owned:new Set([3]),
    saveRuntime:async()=>{},removeOwned:async id=>{assert.equal(id,4);ctx.owned.delete(id);closed++;},diagnostic(){},
    chrome:{tabs:{get:async id=>id===3?{url:meta.url,windowId:1}:{status:'complete',url:mode==='redirect'?'https://example.org':url},
      create:async opts=>{assert.deepEqual({...opts},{windowId:1,url,active:false});created++;return {id:4};},
      sendMessage:async()=>mode==='wrong endpoint'?{...meta,source_ms_document_url:url+'&other=1'}:
        mode==='source changed'&&reads>1?{...meta,document_id:'new'}:meta},
      debugger:{attach:async()=>{},detach:async()=>{detached++},sendCommand:async({tabId},op)=>{
        assert.equal(tabId,4);
        if(op==='Page.captureScreenshot'){captures++;if(mode==='lost job')job.closed=true;return {data:image};}
        if(op==='Runtime.evaluate'){reads++;return {result:{value:{url,binding:mode==='wrong filing'?'other':binding,
          width:1294,height:mode==='moved'&&reads===2?425:439}}};}
        throw Error(op);
      }}}};
  if(mode==='no time')job.msSnapshotSpentMs=19900;
  const helper=vm.runInNewContext(js+'\nCCMsOriginalDocument',ctx);
  const result=await helper.capture(job,q,'a',{tab:3,generation:1});
  assert.equal(result?.image||null,mode==='success'?image:null,org.name+' '+mode);
  assert.equal(closed,created);assert.equal(created,['wrong endpoint','no time'].includes(mode)?0:1);
  if(mode==='success'){assert.equal(captures,1);assert.equal(detached,1);assert.equal(job.snapshotCaptures,1);}
}
test('Original Mississippi filing capture, 70 organizations, with exact source, identity, geometry, expiry and cleanup controls',async()=>{
  assert.equal(new Set(roster.map(x=>x.ein)).size,70);
  for(const org of roster)for(const mode of ['success','wrong endpoint','redirect','wrong filing','moved','source changed','lost job','no time'])await check(org,mode);
});
