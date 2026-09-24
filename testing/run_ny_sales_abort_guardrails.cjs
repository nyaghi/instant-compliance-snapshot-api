const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web-staging/ny-connector.js'),'utf8'),tick=()=>new Promise(setImmediate);
function fixture(hold){
 let listener;const messages=[],api=[],timers=new Set(),origin='https://staging.compliance-express.com';
 const capabilities=JSON.parse(source.match(/response\?\.ok && (\[[^\]]+\])/)[1]);
 const w={addEventListener:(type,fn)=>{listener=fn;},postMessage:m=>{messages.push(m);if(m.action===hold)return;queueMicrotask(()=>listener({source:w,origin,data:{channel:m.channel,direction:'response',id:m.id,ok:true,version:'0.4.0',capabilities,evidence:{rows:[]}}}));}};
 const c={window:w,location:{origin},document:{querySelector:()=>null,getElementById:()=>null},AbortSignal,crypto:require('node:crypto').webcrypto,setTimeout:(f,ms)=>{const t=setTimeout(f,ms);timers.add(t);return t;},clearTimeout:t=>{clearTimeout(t);timers.delete(t);},fetch:async(u,o)=>{
  const p=JSON.parse(o.body);api.push(p.action);
  if(p.action===hold)return new Promise((res,rej)=>{if(o.signal.aborted)rej(o.signal.reason);else o.signal.addEventListener('abort',()=>rej(o.signal.reason),{once:true});});
  return {ok:true,json:async()=>p.action==='start'?{phase:'search',check_token:'fixture',query:{ein:'123456789'},query_id:'1'}:p.action==='advance'?{phase:'complete',result:{state:'NY',status:'Current',success:true}}:{}};
 }};vm.runInNewContext(source,c);return {lookup:c.window.CCNYConnector.lookup,messages,api,timers};
}
const input={organization_name:'Control',ein:'123456789',email:'test@example.test',admin_passcode:'fixture',device_id:'fixture'};
test('Standard without Sales signal completes normal signed flow and cleanup',async()=>{
 const c=fixture();assert.equal((await c.lookup(input)).status,'Current');await tick();assert.deepEqual(c.messages.map(m=>m.action),['ping','acquire','search','finish']);assert.deepEqual(c.api,['start','advance','cancel']);assert.equal(c.timers.size,0);
});
for(const phase of ['ping','acquire','search','start','advance'])test('Sales abort during '+phase+' releases only its job and leaves no bridge timer',async()=>{
 const c=fixture(phase),ctrl=new AbortController();const p=c.lookup({...input,signal:ctrl.signal});await tick();ctrl.abort();await assert.rejects(p,{name:'AbortError'});await tick();
 assert.equal(c.timers.size,0);if(phase!=='ping')assert.equal(c.messages.at(-1).action,'finish');
 if(['search','advance'].includes(phase))assert.equal(c.api.at(-1),'cancel');
});
test('already canceled queued lookup never acquires a slot or starts a registry query',async()=>{
 const c=fixture('search'),first=new AbortController(),second=new AbortController();const p1=c.lookup({...input,signal:first.signal});const p2=c.lookup({...input,signal:second.signal});
 const rejected1=assert.rejects(p1,{name:'AbortError'}),rejected2=assert.rejects(p2,{name:'AbortError'});await tick();second.abort();first.abort();await Promise.all([rejected1,rejected2]);
 assert.equal(c.messages.filter(m=>m.action==='acquire').length,1);assert.equal(c.messages.filter(m=>m.action==='finish').length,1);assert.equal(c.timers.size,0);
});
