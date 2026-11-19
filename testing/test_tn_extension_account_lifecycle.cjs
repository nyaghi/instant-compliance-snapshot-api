// Deterministic Chrome transport simulation; no actual tabs or account traffic.
const vm=require('node:vm'),{readFileSync}=require('node:fs'),assert=require('node:assert/strict');
const code=readFileSync('deployment/staging_connector/tn-extension-account-worker.js','utf8');
async function run(mode){
 let clock=0,next=100,listener;const tabs=new Map(),created=[],closed=[],attached=[],detached=[],commands=[];
 const chrome={runtime:{onMessage:{addListener:f=>listener=f}},tabs:{
   create:async options=>{assert.equal(options.active,false);assert(['https://tncab.tnsos.gov/portal/my-filings','https://tncab.tnsos.gov/portal/my-filings-complete'].includes(options.url));const tab={id:next++,url:options.url,status:'complete',page:0};tabs.set(tab.id,tab);created.push(tab.id);return tab;},
   get:async id=>({...tabs.get(id),...(mode==='navigation-changed'?{url:'https://example.org/'}:{})}),remove:async id=>{assert(tabs.has(id));closed.push(id);tabs.delete(id);}},
 debugger:{attach:async target=>{if(mode==='debugger-busy')throw new Error('Another debugger');attached.push(target.tabId);},detach:async target=>detached.push(target.tabId),
 sendCommand:async(target,method,args)=>{assert.equal(method,'Runtime.evaluate');assert(args.expression.startsWith('(function snapshotPage('));commands.push(method);const tab=tabs.get(target.tabId);
   if(mode==='signed-out')return {result:{value:{state:'sign_in_required'}}};
   if(mode==='source-error')throw new Error('Unavailable');
   if(args.expression.endsWith('(true)')){if(mode!=='pager-stuck')tab.page++;return {result:{value:{state:'advanced'}}};}
   const pending=tab.url.endsWith('/my-filings'),pager=mode==='pager'||mode==='pager-stuck';
   const headers=pending?['','Tracking Number','Registration Number','Description','Fee','Filing Type','Filing Status','Updated']:['','Id','Tracking Number','Filing Status','Description','Filing Type','Updated'];
   const rows=pending&&mode!=='empty'?[['',String(9000001000+tab.page),'CO901','First Extension Request for GLOBAL IMPACT','$0.00','Extension Request','Rejected','Test timestamp']]:[];
   return {result:{value:{state:'ready',headers,rows,hasNext:pending&&pager&&tab.page===0}}};
 }}};
 const context={chrome,URL,Date:{now:()=>clock},CCNYProtocol:{TRIAL_ORIGIN:'https://staging.example'},allJobs:()=>mode==='busy'?[{closed:false}]:[],allowedSender:s=>s.id==='extension'&&s.frameId===0,
   setTimeout:(f,ms)=>{clock+=ms;queueMicrotask(f);return 1;}};
 vm.runInNewContext(code,context);
 const sender={id:'extension',frameId:0,tab:{id:5},url:'https://staging.example/'};
 const message={type:'cc-tn-extension-account-v1',coid:'CO901',names:['Global Impact'],nonce:'b'.repeat(48),url:'https://evil.invalid/ignored'};
 const reply=await new Promise(resolve=>listener(message,sender,resolve));
 assert.deepEqual([...created].sort(),[...closed].sort(),'only owned tabs close, including failure paths');assert.equal(tabs.size,0);
 assert.deepEqual([...attached].sort(),[...detached].sort(),'owned debugger sessions released');
 const expected={healthy:'checked',empty:'checked',pager:'checked','pager-stuck':'partial','signed-out':'sign_in_required','source-error':'partial','navigation-changed':'unavailable','debugger-busy':'unavailable',busy:'busy'}[mode];
 assert.equal(reply.state,expected,mode);if(mode==='healthy')assert.equal(reply.records[0].status,'Rejected');if(mode==='pager')assert.equal(reply.records.length,2);if(mode==='busy')assert.equal(created.length,0);
 let invalidResponded=false;const before=created.length;assert.equal(listener(message,{...sender,id:'other'},()=>invalidResponded=true),false);assert.equal(created.length,before);assert(!invalidResponded);
 return {mode,state:reply.state,owned_tabs:created.length,all_closed:true,focus_changes:0};
}
(async()=>{const results=[];for(const mode of ['healthy','empty','pager','pager-stuck','signed-out','source-error','navigation-changed','debugger-busy','busy'])results.push(await run(mode));if(process.env.CC_TN_LIFECYCLE_RESULTS)require('node:fs').writeFileSync(process.env.CC_TN_LIFECYCLE_RESULTS,JSON.stringify(results,null,2));console.log('PASS: account read-only lifecycle, signed-out/partial/busy failures, safe pager, no focus, owned-tab/debugger cleanup.');})().catch(e=>{console.error(e);process.exitCode=1;});
