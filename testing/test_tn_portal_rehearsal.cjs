const vm=require('node:vm'),assert=require('node:assert/strict'),{readFileSync}=require('node:fs');
let fetched=[],events=[],clicks=0;
class File {constructor(parts,name,o){this.name=name;this.size=parts.reduce((n,p)=>n+p.size,0);this.type=o.type;}}
class DataTransfer {constructor(){this.files=[];this.items={add:f=>this.files.push(f)};}}
const field={dispatchEvent:e=>events.push(e.type)},input={dispatchEvent:e=>events.push(e.type)};
const root={dataset:{demoOnly:'true'},querySelector:s=>s==='#tnPortalCO'?field:input};
const c={window:{},location:{origin:'https://charityclarity-final-four-29-2.onrender.com'},URL,File,DataTransfer,Event,AbortSignal,fetch:async url=>{fetched.push(url);return {ok:true,headers:{get:()=> 'application/pdf'},blob:async()=>({size:86432})};}};
vm.runInNewContext(readFileSync('web-staging/tn-extension-portal-rehearsal.js','utf8'),c);
(async()=>{
 const populate=c.window.CCTennesseePortalRehearsal.populate;
 for(const url of ['https://tncab.tnsos.gov/upload','https://evil.example/file.pdf','/api/tn-extension-demo/documents/notvalid','/api/tn-extension-demo/documents/'+ 'a'.repeat(32)+'?redirect=evil'])await assert.rejects(populate(root,'CO901',url));
 assert.equal(fetched.length,0,'invalid targets must be rejected before fetch');
 const out=await populate(root,'CO901','/api/tn-extension-demo/documents/'+'a'.repeat(32));
 assert.equal(field.value,'CO901');assert.equal(input.files.length,1);assert.equal(out.bytes,86432);assert.deepEqual(events,['input','change','change']);assert.equal(clicks,0);
 c.location.origin='https://tncab.tnsos.gov';await assert.rejects(populate(root,'CO901','/api/tn-extension-demo/documents/'+'a'.repeat(32)));
 assert.equal(fetched.length,1,'adapter cannot run against live Tennessee');
 console.log('PASS: exact owned staging destination, automatic CO and file input, no Submit click, live Tennessee rejected.');
})().catch(e=>{console.error(e);process.exitCode=1;});
