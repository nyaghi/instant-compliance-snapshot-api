const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const source=fs.readFileSync(path.join(root,'web-staging/connector/review.js'),'utf8');
const protocol=fs.readFileSync(path.join(root,'browser-connector/protocol.js'),'utf8');
const tick=()=>new Promise(r=>setImmediate(r));
test('review page blocks site-wide analytics and has no credential inputs',()=>{const html=fs.readFileSync(path.join(root,'web-staging/connector/review.html'),'utf8');assert.match(html,/script-src 'self'/);assert.match(html,/connect-src 'none'/);assert.doesNotMatch(html,/<input[^>]+type=["']password/);assert.doesNotMatch(html,/admin_passcode/)});
function harness(options={}){
 const requests=[],timers=new Map(),listeners={},elements=new Map();let timerId=0,seq=0;
 function element(){return {textContent:'',value:'12-3456789',hidden:false,disabled:false,children:[],handlers:{},append(x){this.children.push(x)},replaceChildren(...items){this.children=items},addEventListener(name,handler){this.handlers[name]=handler}};}
 for(const name of ['ein','lookup','search','refresh','check','connection','status','results','evidence','elapsed','details'])elements.set(name,element());
 elements.get('details').hidden=true;
 const window={top:null,addEventListener(name,handler){listeners[name]=handler},postMessage(request,target){
  requests.push(request);assert.equal(target,'https://www.compliance-express.com');
  const common={channel:request.channel,direction:'response',id:request.id};
  const payload=options.reply?.(request)??(request.action==='ping'?{ok:true,version:'0.4.0',capabilities:['queue-v1','connection-recovery-v1','resume-v1']}:{ok:true});
  if(payload.hold)return;
  queueMicrotask(()=>listeners.message({source:window,origin:target,data:{...common,...payload}}));
 }};window.top=window;
 const context=vm.createContext({window,location:{origin:options.origin||'https://www.compliance-express.com'},document:{getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id)},createElement:element},crypto:{randomUUID:()=>String(++seq).padStart(32,'0')},performance:{now:()=>0},setTimeout(fn){timers.set(++timerId,fn);return timerId},clearTimeout(id){timers.delete(id)},Map,console});
 vm.runInContext(protocol,context);vm.runInContext(source,context);
 return {requests,timers,elements,window,listeners,element:id=>elements.get(id),async search(ein='12-3456789'){this.element('ein').value=ein;this.element('lookup').handlers.submit({preventDefault(){}});await tick();}};
}
// ny-main removes its internal `kind` before the evidence crosses the bridge.
const evidence=()=>({query:{ein:'123456789'},http_status:200,success:true,statusCode:200,rows:[{orgID:'12-34-56',orgName:'Example Organization',ein:'12-3456789'}]});
test('real evidence is shown and job cleaned without classifying compliance',async()=>{const h=harness({reply:r=>r.action==='search'?{ok:true,evidence:evidence()}:undefined});await tick();await h.search();assert.match(h.element('status').textContent,/Live registry response received: 1/);assert.match(h.element('status').textContent,/No compliance status/);assert.deepEqual(h.requests.map(r=>r.action),['ping','ping','acquire','search','finish']);assert.equal(h.element('search').disabled,false)});
test('incomplete or wrong-organization evidence never renders a result',async()=>{for(const change of [e=>{e.query.ein='987654321'},e=>{e.http_status=500},e=>{e.rows[0].ein='bad'},e=>{delete e.rows}]){const e=evidence();change(e);const h=harness({reply:r=>r.action==='search'?{ok:true,evidence:e}:undefined});await tick();await h.search();assert.match(h.element('status').textContent,/No registration conclusion/);assert.equal(h.element('details').hidden,true);assert.equal(h.requests.at(-1).action,'finish')}});
test('empty completed response remains evidence, not Not Registered',async()=>{const e=evidence();e.rows=[];const h=harness({reply:r=>r.action==='search'?{ok:true,evidence:e}:undefined});await tick();await h.search();assert.match(h.element('status').textContent,/returned zero rows/);assert.doesNotMatch(h.element('status').textContent,/Not Registered/)});
test('network failure stays explicit and still finishes',async()=>{const h=harness({reply:r=>r.action==='search'?{ok:false,reason:'NY_CONNECTOR_SEARCH_NETWORK_ERROR'}:undefined});await tick();await h.search();assert.match(h.element('status').textContent,/NY_CONNECTOR_SEARCH_NETWORK_ERROR/);assert.equal(h.requests.at(-1).action,'finish')});
test('untrusted origins and unknown response ids cannot complete a request',async()=>{const h=harness({reply:r=>r.action==='search'?{hold:true}:undefined});await tick();await h.search();const req=h.requests.at(-1);const reply={channel:req.channel,direction:'response',id:req.id,ok:true,evidence:evidence()};for(const ev of [{source:{},origin:'https://www.compliance-express.com',data:reply},{source:h.window,origin:'https://other.example',data:reply},{source:h.window,origin:'https://www.compliance-express.com',data:{...reply,id:'unrelated'}}])h.listeners.message(ev);await tick();assert.equal(h.element('details').hidden,true);assert.equal(h.element('search').disabled,true);h.listeners.message({source:h.window,origin:'https://www.compliance-express.com',data:reply});await tick();assert.equal(h.element('details').hidden,false)});
test('missing connector and invalid input do not open a search',async()=>{const h=harness({reply:r=>r.action==='ping'?{ok:false}:undefined});await tick();await h.search();assert.equal(h.requests.some(r=>r.action==='acquire'),false);assert.equal(h.element('search').disabled,false);await h.search('abc123456789');assert.match(h.element('status').textContent,/valid nine-digit/)});
test('rapid duplicate clicks cannot start a second active job',async()=>{const h=harness({reply:r=>r.action==='search'?{hold:true}:undefined});await tick();await h.search();await h.search();assert.equal(h.requests.filter(r=>r.action==='acquire').length,1)});
test('foreign host cannot use the test client',()=>{const h=harness({origin:'https://other.example'});assert.equal(h.requests.length,0)});
test('recovery explicitly uses the existing refresh lifecycle',async()=>{const h=harness();await tick();h.element('refresh').handlers.click();await tick();const acquire=h.requests.find(r=>r.action==='acquire');assert.equal(acquire.intent,'refresh');assert.equal(h.requests.some(r=>r.action==='search'),false);assert.equal(h.requests.some(r=>r.action==='refresh'),true);assert.equal(h.requests.at(-1).action,'finish')});
test('state-controlled HTML stays literal text',async()=>{const e=evidence();e.rows[0].orgName='<img src=x onerror=alert(1)>';const h=harness({reply:r=>r.action==='search'?{ok:true,evidence:e}:undefined});await tick();await h.search();assert.equal(h.element('results').children[0].children[1].children[1].textContent,e.rows[0].orgName);assert.doesNotMatch(source,/innerHTML|insertAdjacentHTML|fetch\(/)});
