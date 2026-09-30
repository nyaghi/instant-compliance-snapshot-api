/* No live challenges: fixture pixels exercise binding and non-persistence. */
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.join(__dirname,'..');
const content=fs.readFileSync(path.join(process.env.CC_TEST_TRIAL_DIR||path.join(root,'browser-connector'),'registry-content.js'),'utf8')
 .replace('  async function handle(m) {','  globalThis.alTest={alImagePixels,alVerificationRequest,alApplyVerification,handle};\n  async function handle(m) {');
function harness(){
 let pixels='data:image/png;base64,fixture',clock=1000,draws=0;
 class Input{get value(){return this.v||'';}set value(v){this.v=v;}dispatchEvent(){}}
 const input=new Input(),image={tagName:'IMG',complete:true,naturalWidth:125,naturalHeight:80,
  src:'https://ago.igovsolution.net/online/Captcha.aspx',
  getAttribute:n=>n==='alt'?'Verification Code image':n==='aria-label'?'Captcha':null};
 const win={};win.top=win;
 const context=vm.createContext({window:win,location:{origin:'https://ago.igovsolution.net',pathname:'/online/Lookups/Business.aspx',href:'https://ago.igovsolution.net/online/Lookups/Business.aspx'},
  URL,Date:{now:()=>clock},crypto:{randomUUID:()=> 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'},
  HTMLInputElement:Input,HTMLSelectElement:class{},Event:class{},
  document:{getElementById:id=>id==='imgcap'?image:id==='ctl00_cntbdy_txt_verify'?input:null,
   querySelector:()=>null,createElement:()=>({getContext:()=>({drawImage:()=>draws++}),toDataURL:()=>pixels})},
  chrome:{runtime:{id:'fixture',onMessage:{addListener(){}}}}});
 vm.runInContext(content,context);
 return {api:context.alTest,input,image,setPixels:v=>pixels=v,advance:n=>clock+=n,draws:()=>draws};
}
const q={state:'AL',operation:'search',name:'Fixture Charity'};
test('verification request is explicitly incomplete and does not enter any code',()=>{
 const h=harness(),r=h.api.alVerificationRequest(q);
 assert.equal(r.complete,false);assert.equal(r.verification_pending,true);assert.equal(r.rows,undefined);
 assert.equal(h.input.value,'');assert.equal(h.draws(),1);
});
test('only a matching answer for the same current image can be entered once',()=>{
 const h=harness(),r=h.api.alVerificationRequest(q),answer={id:r.verification_id,code:'ABC123'};
 h.api.alApplyVerification({...q,verification:answer});assert.equal(h.input.value,'ABC123');
 assert.throws(()=>h.api.alApplyVerification({...q,verification:answer}),/VERIFICATION_REQUIRED/);
});
test('changed image, name, expired answer and wrong identifier cannot submit',()=>{
 for(const cause of ['pixels','name','age','id','code']){
  const h=harness(),r=h.api.alVerificationRequest(q),request={...q,verification:{id:r.verification_id,code:'ABC123'}};
  if(cause==='pixels')h.setPixels('data:image/png;base64,changed');
  if(cause==='name')request.name='Different Charity';
  if(cause==='age')h.advance(45001);
  if(cause==='id')request.verification.id='other';
  if(cause==='code')request.verification.code='bad code';
  assert.throws(()=>h.api.alApplyVerification(request),/VERIFICATION_REQUIRED/);assert.equal(h.input.value,'');
 }
});
test('live image alt text and accessible name are not interchangeable identity fields',()=>{
 for(const label of ['Verification Code image','Captcha','']){
  const h=harness();h.image.getAttribute=n=>n==='alt'?label:null;
  assert.equal(h.api.alVerificationRequest(q).verification_pending,true);
 }
});

test('actual AL content handler captures the observed fresh form instead of terminating verification',async()=>{
 const h=harness(),r=await h.api.handle({action:'registry-al',query:q,automaticVerification:true});
 assert.equal(r.ok,true);assert.equal(r.evidence.verification_pending,true);
 assert.equal(r.evidence.complete,false);assert.equal(h.input.value,'');
 await assert.rejects(h.api.handle({action:'registry-al',query:q,automaticVerification:false}),/VERIFICATION_REQUIRED/);
});

test('image must be loaded, small and from the exact same-origin verification endpoint',()=>{
 for(const change of [{complete:false},{naturalWidth:601},{naturalHeight:301},{src:'https://example.com/image.png'},
  {src:'https://ago.igovsolution.net/online/logo.png'},
  {currentSrc:'https://example.com/Captcha.aspx'},
  {currentSrc:'https://ago.igovsolution.net/online/logo.png'}]){
  const h=harness();Object.assign(h.image,change);assert.throws(()=>h.api.alVerificationRequest(q));
 }
 const h=harness();h.setPixels('data:image/png;base64,'+'a'.repeat(180001));assert.throws(()=>h.api.alVerificationRequest(q));
});
test('production protocol refuses the added verification command; trial AL only accepts its exact schema',()=>{
 const source=fs.readFileSync(path.join(root,'browser-connector/protocol.js'),'utf8');
 for(const trial of [false,true]){
  const context=vm.createContext({URL});vm.runInContext(trial?source.replace('const TRIAL_ORIGIN = "";','const TRIAL_ORIGIN = "https://fixture.onrender.com";'):source,context);
  const query={...q,verification:{id:'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',code:'ABC123'}};
  assert.equal(context.CCNYProtocol.validQuery(query),trial);
  assert.equal(context.CCNYProtocol.validQuery({...query,state:'NV'}),false);
  assert.equal(context.CCNYProtocol.validQuery({...query,verification:{...query.verification,extra:true}}),false);
  if(trial)assert.equal(context.CCNYProtocol.sameQuery(JSON.parse(JSON.stringify(query)),query),true);
 }
});
test('AL image and answer are omitted from saved worker command and result state',()=>{
 const worker=fs.readFileSync(path.join(root,'browser-connector/worker.js'),'utf8');
 const expression=worker.match(/const runtimeState = \(\) => ([^\n]+);/)[1];
 const active={lookupId:'fixture',registryState:'AL',sender:{tab:{id:1}},command:{query:{verification:{code:'PRIVATE'}}},lastResponse:{verification_image:'PRIVATE'}};
 const result=vm.runInNewContext(expression,{nextStart:0,owned:new Set(),diagnostics:[],active,queue:[]});
 assert.equal(result.queue[0].command,null);assert.equal(result.queue[0].lastResponse,null);
 assert.ok(!JSON.stringify(result).includes('PRIVATE'));
});
