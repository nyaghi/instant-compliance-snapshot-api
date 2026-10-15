/* Public request observer controls: no live browser, registry or credentials. */
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=process.env.CC_TEST_TRIAL_DIR||path.join(__dirname,'../browser-connector');
const source=fs.readFileSync(path.join(root,'registry-tn-main.js'),'utf8');
const origin='https://tncab.tnsos.gov',channel='cc-final-four-tn-phase-v1',id='12345678-1234-1234-1234-123456789abc';
function fixture({duplicates=false,missing=false,offsite=false,subframe=false}={}){
 let now=1000;const messages=[],listeners=[],calls=[];
 class XHR{
  constructor(){this.events={};this.status=200;}
  open(...args){calls.push({method:'open',args});return 'opened';}
  send(...args){calls.push({method:'send',args});return 'sent';}
  addEventListener(type,fn){this.events[type]=fn;}
  finish(status=200){this.status=status;this.events.loadend?.();}
  get responseText(){throw Error('response bodies must never be read');}
 }
 const oldOpen=XHR.prototype.open,oldSend=XHR.prototype.send;
 const headers=['(command)','(summary-mobile)','Id','FileNumber','DisplayName'].map(key=>({getAttribute:k=>k==='data-colkey'?key:null}));
 const row={children:['Details','summary','39953','CO50375','EXAMPLE CLINIC, INC.'].map(innerText=>({innerText}))};
 const table={querySelectorAll:s=>s==='thead th'?headers:s==='tbody > tr'?(missing?[]:duplicates?[row,row]:[row]):[]};
 const window={addEventListener:(type,fn)=>{if(type==='message')listeners.push(fn);},postMessage:(m,target)=>messages.push({m,target})};window.top=subframe?{}:window;
 const location={origin:offsite?'https://example.org':origin,pathname:'/portal/registered-charities-search',href:origin+'/portal/registered-charities-search'};
 const context={window,document:{querySelectorAll:s=>s==='[id^="SearchResults_"] table[role="grid"]'?[table]:[]},location,XMLHttpRequest:XHR,URL,Date:{now:()=>now}};
 vm.createContext(context);vm.runInContext(source,context);
 const command=(extra={},event={})=>listeners.forEach(fn=>fn({source:window,origin,data:{channel,direction:'request',id,operation:'watch',identifier:'CO50375',budget_ms:25000,...extra},...event}));
 const request=(url=origin+'/portal/RegistrationSearch/Details?id=39953&widgetConfig=SECRET',method='POST')=>{const xhr=new XHR();assert.equal(xhr.open(method,url,true),'opened');assert.equal(xhr.send('UNCHANGED BODY'),'sent');return xhr;};
 return{XHR,oldOpen,oldSend,messages,calls,command,request,advance:ms=>{now+=ms;}};
}
test('observer reports only ready/start/end status and passes native request arguments unchanged',()=>{
 const f=fixture();f.command();const xhr=f.request();xhr.finish();
 assert.deepEqual(f.messages.map(e=>e.m.phase),['ready','started','finished']);assert.equal(f.messages[2].m.http_status,200);
 assert.equal(f.calls.length,2);assert.equal(f.calls[0].args[0],'POST');assert.equal(f.calls[1].args[0],'UNCHANGED BODY');
 for(const value of ['SECRET','UNCHANGED BODY','39953','CO50375','EXAMPLE'])assert.ok(!JSON.stringify(f.messages).includes(value));
});
test('observer ignores other identities, methods, endpoints and origins without blocking those requests',()=>{
 const f=fixture();f.command();
 f.request(origin+'/portal/RegistrationSearch/Details?id=123');
 f.request(origin+'/portal/RegistrationSearch/Details?id=39953','GET');
 f.request(origin+'/portal/Other?id=39953');
 f.request('https://example.org/portal/RegistrationSearch/Details?id=39953');
 assert.deepEqual(f.messages.map(e=>e.m.phase),['ready']);assert.equal(f.calls.length,8);
});
test('watch requires exactly one observed public CO row and its numeric grid identifier',()=>{
 for(const options of [{duplicates:true},{missing:true}]){const f=fixture(options);f.command();assert.deepEqual(f.messages.map(e=>e.m.phase),['unavailable']);f.request().finish();assert.equal(f.messages.length,1);}
});
test('foreign-frame, foreign-origin and malformed watch messages cannot observe a request',()=>{
 const f=fixture();f.command({}, {source:{}});f.command({}, {origin:'https://example.org'});f.command({id:'bad'});f.command({identifier:'OTHER'});f.command({budget_ms:0});
 f.request().finish();assert.equal(f.messages.length,0);
});
test('stop and original expiry discard late completion without altering the native request',()=>{
 for(const stop of [true,false]){const f=fixture();f.command();const xhr=f.request();if(stop)f.command({operation:'stop'});else f.advance(25001);xhr.finish();assert.deepEqual(f.messages.map(e=>e.m.phase),['ready','started']);}
});
test('an overlapping watch cannot replace the first bound request observation',()=>{
 const f=fixture();f.command();f.command({id:'22345678-1234-1234-1234-123456789abc'});const xhr=f.request();xhr.finish(503);
 assert.deepEqual(f.messages.map(e=>e.m.phase),['ready','unavailable','started','finished']);assert.equal(f.messages.at(-1).m.id,id);assert.equal(f.messages.at(-1).m.http_status,503);
});
test('observer follows only the first bound request and does not submit or replay another request',()=>{
 const f=fixture();f.command();const first=f.request(),second=f.request();second.finish();first.finish();
 assert.deepEqual(f.messages.map(e=>e.m.phase),['ready','started','finished']);assert.equal(f.calls.length,4);
});
test('non-Tennessee pages and subframes retain the original XMLHttpRequest methods',()=>{
 for(const options of [{offsite:true},{subframe:true}]){const f=fixture(options);assert.equal(f.XHR.prototype.open,f.oldOpen);assert.equal(f.XHR.prototype.send,f.oldSend);assert.equal(f.messages.length,0);}
});
