/* No live challenges: fixture pixels exercise binding and non-persistence. */
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.join(__dirname,'..');
const content=fs.readFileSync(path.join(process.env.CC_TEST_TRIAL_DIR||path.join(root,'browser-connector'),'registry-content.js'),'utf8')
 .replace('  async function handle(m) {','  globalThis.alTest={alImagePixels,alVerificationRequest,alApplyVerification,registryDocumentReady,handle};\n  async function handle(m) {');
function harness(){
 let pixels='data:image/png;base64,fixture',clockOffset=0,draws=0;
 class Input{get value(){return this.v||'';}set value(v){this.v=v;}dispatchEvent(){}}
 const input=new Input(),button={disabled:false,getClientRects:()=>[{}]};
 const image={tagName:'IMG',complete:true,naturalWidth:125,naturalHeight:80,
  src:'https://ago.igovsolution.net/online/Captcha.aspx',
  getAttribute:n=>n==='alt'?'Verification Code image':n==='aria-label'?'Captcha':null};
 const win={};win.top=win;
 const context=vm.createContext({window:win,location:{origin:'https://ago.igovsolution.net',pathname:'/online/Lookups/Business.aspx',href:'https://ago.igovsolution.net/online/Lookups/Business.aspx'},
  URL,Date:{now:()=>Date.now()+clockOffset},setTimeout,crypto:{randomUUID:()=> 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'},
  HTMLInputElement:Input,HTMLSelectElement:class{},Event:class{},
  document:{readyState:'complete',getElementById:id=>id==='imgcap'?image:id==='ctl00_cntbdy_btn_search'?button:
    ['ctl00_cntbdy_txt_verify','ctl00_cntbdy_txt_businessname'].includes(id)?input:null,
   querySelector:()=>null,createElement:()=>({getContext:()=>({drawImage:()=>draws++}),toDataURL:()=>pixels})},
  chrome:{runtime:{id:'fixture',onMessage:{addListener(){}}}}});
 vm.runInContext(content,context);
 const api={...context.alTest,alVerificationRequest:(query,deadline=Date.now()+clockOffset+5000)=>
  context.alTest.alVerificationRequest(query,deadline)};
 return {api,input,image,document:context.document,setPixels:v=>pixels=v,advance:n=>clockOffset+=n,draws:()=>draws};
}
const q={state:'AL',operation:'search',name:'Fixture Charity'};
test('verification request is explicitly incomplete and does not enter any code',async()=>{
 const h=harness(),r=await h.api.alVerificationRequest(q);
 assert.equal(r.complete,false);assert.equal(r.verification_pending,true);assert.equal(r.rows,undefined);
 assert.equal(h.input.value,'');assert.equal(h.draws(),1);
});
test('only a matching answer for the same current image can be entered once',async()=>{
 const h=harness(),r=await h.api.alVerificationRequest(q),answer={id:r.verification_id,code:'ABC123'};
 h.api.alApplyVerification({...q,verification:answer});assert.equal(h.input.value,'ABC123');
 assert.throws(()=>h.api.alApplyVerification({...q,verification:answer}),/VERIFICATION_REQUIRED/);
});
test('a five-character public code remains image-bound and one-use',async()=>{
 const h=harness(),r=await h.api.alVerificationRequest(q),answer={id:r.verification_id,code:'AB123'};
 h.api.alApplyVerification({...q,verification:answer});assert.equal(h.input.value,'AB123');
 assert.throws(()=>h.api.alApplyVerification({...q,verification:answer}),/VERIFICATION_REQUIRED/);
});
test('changed image, name, expired answer and wrong identifier cannot submit',async()=>{
 for(const cause of ['pixels','name','age','id','code']){
  const h=harness(),r=await h.api.alVerificationRequest(q),request={...q,verification:{id:r.verification_id,code:'ABC123'}};
  if(cause==='pixels')h.setPixels('data:image/png;base64,changed');
  if(cause==='name')request.name='Different Charity';
  if(cause==='age')h.advance(45001);
  if(cause==='id')request.verification.id='other';
  if(cause==='code')request.verification.code='bad code';
  assert.throws(()=>h.api.alApplyVerification(request),/VERIFICATION_REQUIRED/);assert.equal(h.input.value,'');
 }
});
test('live image alt text and accessible name are not interchangeable identity fields',async()=>{
 for(const label of ['Verification Code image','Captcha','']){
  const h=harness();h.image.getAttribute=n=>n==='alt'?label:null;
  assert.equal((await h.api.alVerificationRequest(q)).verification_pending,true);
 }
});

test('actual AL content handler captures the observed fresh form instead of terminating verification',async()=>{
 const h=harness(),r=await h.api.handle({action:'registry-al',query:q,automaticVerification:true});
 assert.equal(r.ok,true);assert.equal(r.evidence.verification_pending,true);
 assert.equal(r.evidence.complete,false);assert.equal(h.input.value,'');
 await assert.rejects(h.api.handle({action:'registry-al',query:q,automaticVerification:false}),/VERIFICATION_REQUIRED/);
});
test('AL waits for a delayed verification image within the same command deadline',async()=>{
 const h=harness();h.image.complete=false;
 assert.equal(h.api.registryDocumentReady(),false);
 setTimeout(()=>{h.image.complete=true;},60);
 const first=await h.api.handle({action:'registry-al',query:q,automaticVerification:true,budgetMs:1000});
 assert.equal(first.evidence.verification_pending,true);
 assert.equal(h.draws(),1);
});
test('AL readiness requires the completed form and image',()=>{
 const h=harness();
 h.document.readyState='loading';assert.equal(h.api.registryDocumentReady(),false);
 h.document.readyState='interactive';assert.equal(h.api.registryDocumentReady(),false);
 h.document.readyState='complete';assert.equal(h.api.registryDocumentReady(),true);
 h.image.complete=false;assert.equal(h.api.registryDocumentReady(),false);
});

test('image must be loaded, small and from the exact same-origin verification endpoint',async()=>{
 for(const change of [{naturalWidth:601},{naturalHeight:301},{src:'https://example.com/image.png'},
  {src:'https://ago.igovsolution.net/online/logo.png'},
  {currentSrc:'https://example.com/Captcha.aspx'},
  {currentSrc:'https://ago.igovsolution.net/online/logo.png'}]){
  const h=harness();Object.assign(h.image,change);await assert.rejects(h.api.alVerificationRequest(q));
 }
 const h=harness();h.setPixels('data:image/png;base64,'+'a'.repeat(180001));await assert.rejects(h.api.alVerificationRequest(q));
 const pending=harness();pending.image.complete=false;
 await assert.rejects(pending.api.alVerificationRequest(q,Date.now()+70),/VERIFICATION_REQUIRED/);
});
test('production protocol refuses the added verification command; trial AL only accepts its exact schema',()=>{
 const source=fs.readFileSync(path.join(root,'browser-connector/protocol.js'),'utf8');
 for(const trial of [false,true]){
  const context=vm.createContext({URL});vm.runInContext(trial?source.replace('const TRIAL_ORIGIN = "";','const TRIAL_ORIGIN = "https://fixture.onrender.com";'):source,context);
  const query={...q,verification:{id:'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',code:'ABC123'}};
  assert.equal(context.CCNYProtocol.validQuery(query),trial);
  assert.equal(context.CCNYProtocol.validQuery({...query,verification:{...query.verification,code:'AB123'}}),trial);
  assert.equal(context.CCNYProtocol.validQuery({...query,state:'NV'}),false);
  assert.equal(context.CCNYProtocol.validQuery({...query,verification:{...query.verification,extra:true}}),false);
  if(trial)assert.equal(context.CCNYProtocol.sameQuery(JSON.parse(JSON.stringify(query)),query),true);
 }
});
test('AL image and answer are omitted from saved worker command and result state',()=>{
 const worker=fs.readFileSync(path.join(root,'browser-connector/worker.js'),'utf8');
 const expression=worker.match(/const runtimeState = \(\) => ([^\n]+);/)[1];
 const active={lookupId:'fixture',registryState:'AL',sender:{tab:{id:1}},command:{query:{verification:{code:'PRIVATE'}}},lastResponse:{verification_image:'PRIVATE'}};
 const result=vm.runInNewContext(expression,{P:{TRIAL_ORIGIN:'https://fixture.onrender.com',nyDiagnostics:()=>[]},nextStart:0,laneStarts:new Map(),owned:new Set(),diagnostics:[],allJobs:()=>[active],isActive:j=>j===active});
 assert.equal(result.queue[0].command,null);assert.equal(result.queue[0].lastResponse,null);
 assert.ok(!JSON.stringify(result).includes('PRIVATE'));
});
