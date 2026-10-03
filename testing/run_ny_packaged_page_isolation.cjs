/* Both connectors run in the state's MAIN world; test the actual manifest. */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const base=path.join(__dirname,'..','browser-connector');
const trial=process.env.CC_TEST_TRIAL_DIR;
if(!trial)throw Error('CC_TEST_TRIAL_DIR must identify the actual packaged connector');
const manifest=JSON.parse(fs.readFileSync(path.join(trial,'manifest.json'),'utf8'));
const scripts=manifest.content_scripts.filter(s=>s.world==='MAIN'&&s.matches.some(m=>m.startsWith('https://charities-search.ag.ny.gov/'))).flatMap(s=>s.js);
function page(){
 const listeners=[],replies=[];
 class XHR {open(){}send(){}}
 const window={addEventListener:(event,fn)=>{if(event==='message')listeners.push(fn);},postMessage:msg=>replies.push(msg),fetch:async()=>({status:401,clone:()=>({json:async()=>({})})})};window.top=window;
 return {context:vm.createContext({URL,window,location:{origin:'https://charities-search.ag.ny.gov',pathname:'/RegistrySearch/45-64-20'},XMLHttpRequest:XHR,setTimeout,clearTimeout}),listeners,replies};
}
function install(context,folder,files){for(const name of files)vm.runInContext(fs.readFileSync(path.join(folder,name),'utf8'),context,{filename:name});}
test('trial MAIN-world installation leaves the mature protocol object unchanged',()=>{
 const {context}=page();install(context,base,['protocol.js']);const mature=context.CCNYProtocol;
 install(context,trial,scripts);
 assert.equal(context.CCNYProtocol,mature,'The trial must not replace the mature connector page protocol');
 assert.equal(context.CCNYProtocol.TRIAL_ORIGIN,'');
});
test('trial page captures its own protocol even when the mature protocol loads later',async()=>{
 const {context,listeners,replies}=page();install(context,trial,scripts);install(context,base,['protocol.js']);
 await context.window.fetch('https://charities-search-api.ag.ny.gov/api/FileNet/RegistryDetail?orgID=45-64-20');
 await new Promise(r=>setTimeout(r,0));
 await listeners[0]({source:context.window,origin:'https://charities-search.ag.ny.gov',data:{channel:'cc-final-four-ny-page-v1',direction:'request',id:'12345678-1234-4234-9234-123456789012',query:{orgID:'45-64-20'}}});
 assert.equal(replies.at(-1)?.reason,'NY_CONNECTOR_DETAIL_UNAUTHORIZED');
 assert.equal(context.CCNYProtocol.TRIAL_ORIGIN,'');
});

test('interleaved mature and trial adapters retain separate response rules',async()=>{
 const {context,listeners,replies}=page();
 install(context,base,['protocol.js']);
 install(context,trial,scripts);
 install(context,base,['ny-main.js']);
 await context.window.fetch('https://charities-search-api.ag.ny.gov/api/FileNet/RegistryDetail?orgID=45-64-20');
 await new Promise(r=>setTimeout(r,0));
 for(const channel of ['cc-final-four-ny-page-v1','cc-ny-page-v1']){
  for(const listener of listeners) await listener({source:context.window,origin:'https://charities-search.ag.ny.gov',data:{channel,direction:'request',id:'12345678-1234-4234-9234-123456789012',query:{orgID:'45-64-20'}}});
 }
 assert.equal(replies.find(r=>r.channel==='cc-final-four-ny-page-v1')?.reason,'NY_CONNECTOR_DETAIL_UNAUTHORIZED');
 assert.equal(replies.find(r=>r.channel==='cc-ny-page-v1')?.reason,'NY_CONNECTOR_DETAIL_INCOMPLETE');
});
