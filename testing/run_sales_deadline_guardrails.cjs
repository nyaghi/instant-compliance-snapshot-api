const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),cp=require('node:child_process'),path=require('node:path');
const {setup}=require('./sales_test_dom.cjs');
const root=path.resolve(__dirname,'..'),tick=()=>new Promise(setImmediate);
function fixture(){
 let now=0,n=0;const timers=new Map();
 const c=setup({clock:{performance:{now:()=>now},setTimeout:(f,ms)=>{timers.set(++n,{f,at:now+ms});return n;},clearTimeout:id=>timers.delete(id),setInterval:()=>0,clearInterval:()=>{}}});
 c.advance=async ms=>{now+=ms;for(const [id,t] of [...timers])if(t.at<=now){timers.delete(id);t.f();}await tick();};
 c.shift=ms=>{now+=ms;};c.elements.ccSalesMode.onclick();c.elements.ccSalesSelectAll.onclick();return c;
}
test('one overall deadline preserves early results and closes running AND queued states exactly once',async()=>{
 const c=fixture(),run=c.submit();c.finish('AK',{state:'AK',status:'Current',comments:'Confirmed EIN control'});await tick();
 await c.advance(59999);assert.equal(c.events.length,0);await c.advance(1);await run;
 const d=c.events[0].detail;assert.equal(d.seconds,60);assert.equal(d.results.length,32);assert.equal(new Set(d.results.map(r=>r.state)).size,32);
 assert.equal(d.results.find(r=>r.state==='AK').status,'Current');assert.equal(d.results.filter(r=>r.result.status_reason==='SALES_TIME_LIMIT').length,31);
 assert(c.calls.every(args=>args[7].signal.aborted));assert.equal(c.elements.ccSalesRun.disabled,false);assert.equal(c.calls.length,16);
 await c.drain();assert.equal(c.events.length,1);assert.equal(d.results.length,32);assert.equal(c.calls.length,16);
});
test('late response cannot overwrite deadline results or a new organization run',async()=>{
 const c=fixture();let run=c.submit();await c.advance(60000);await run;
 c.elements.ccSalesClear.onclick();c.inputs.find(x=>x.value==='WV').checked=true;c.elements.ccSalesName.value='Second organization';
 run=c.submit();c.finish('AK',{state:'AK',status:'Current'});await tick();assert.equal(c.elements.ccSalesRows.children.length,1);assert.equal(c.events.length,1);
 c.finish('WV',{state:'WV',status:'Not Registered'});await run;assert.equal(c.events[1].detail.results[0].status,'Not Found');await c.drain();
 assert.equal(c.events.length,2);assert.equal(c.elements.ccSalesRows.children[0].dataset.state,'WV');
});
test('late timer delivery cannot accept a result after the elapsed deadline',async()=>{
 const c=fixture(),run=c.submit();c.shift(61000);c.finish('AK',{state:'AK',status:'Current'});await run;
 assert(c.events[0].detail.results.every(r=>r.status==='Unable to Confirm'));await c.drain();
});
test('fast run finishes early, ambiguity remains unconfirmed and deadline is cleaned up',async()=>{
 const c=fixture(),run=c.submit();c.finish('NY',{status:'Needs Review',comments:'Two equally matching records'});await c.drain();await run;
 assert.equal(c.events[0].detail.time_limit_reached,false);assert.equal(c.events[0].detail.results.find(r=>r.state==='NY').status,'Unable to Confirm');
 await c.advance(60000);assert.equal(c.events.length,1);
});
test('32-lane experiment uses all states at once with same deadline and classification',async()=>{
 const source=fs.readFileSync(path.join(root,'web-staging/sales-mode.js'),'utf8').replace('const STATE_CONCURRENCY = 15;','const STATE_CONCURRENCY = 32;');
 const c=setup({source});c.elements.ccSalesMode.onclick();c.elements.ccSalesSelectAll.onclick();const run=c.submit();assert.equal(c.calls.length,32);await c.drain();await run;assert.equal(c.peak,32);
});
test('Standard transport retains its five-minute timeout; optional Sales abort is forwarded and listener removed',async()=>{
 const html=fs.readFileSync(path.join(root,'web-staging/index.html'),'utf8'),fn=html.slice(html.indexOf('    async function requestSingleState('),html.indexOf('    function stateLaneBases('));
 let duration,transportSignal;const c=vm.createContext({AbortController,setTimeout:(f,ms)=>{duration=ms;return 1;},clearTimeout:()=>{},window:{location:{origin:'https://staging.compliance-express.com',href:'https://staging.compliance-express.com/'}},adminPasscode:{value:'fixture'},getDeviceId:()=>'',document:{referrer:''},navigator:{userAgent:'test'},attribution:{},runAlternateNames:[],fetch:async(u,o)=>{transportSignal=o.signal;return {ok:true,text:async()=>JSON.stringify({results:[{state:'CO',status:'Current'}]})};},fallbackResult:()=>({})});
 vm.runInContext(fn,c);assert.equal((await c.requestSingleState('https://fixture','123456789','fixture','CO','Control')).status,'Current');assert.equal(duration,300000);assert.equal(transportSignal.aborted,false);
 const ctrl=new AbortController();c.fetch=(u,o)=>new Promise((res,rej)=>{transportSignal=o.signal;o.signal.addEventListener('abort',()=>rej(o.signal.reason),{once:true});});
 const pending=c.requestSingleState('https://fixture','123456789','fixture','ME','Control',false,[],{signal:ctrl.signal});ctrl.abort();await assert.rejects(pending,{name:'AbortError'});assert.equal(transportSignal.aborted,true);
 let lookedUp=false;c.window.CCNYConnector={lookup:async input=>{lookedUp=true;assert.equal(input.signal,ctrl.signal);return {};}};
 await assert.rejects(c.requestSingleState('https://fixture','123456789','fixture','NY','Control',false,[],{signal:ctrl.signal}),{name:'AbortError'});assert.equal(lookedUp,false);
});
test('discovery and shared checker match baseline; NY transport has separate scoped controls',()=>{
 for(const file of ['Charity_Checker_Script for 13_states.py','web-staging/organization-identity.js']){
  const old=cp.execFileSync('git',['show','fb193e6:'+file],{cwd:root,maxBuffer:20*1024*1024});assert.deepEqual(fs.readFileSync(path.join(root,file)).toString().replaceAll('\r\n','\n'),old.toString().replaceAll('\r\n','\n'),file);
 }
});
