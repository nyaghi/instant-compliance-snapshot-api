const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
test('count comes from durable acknowledgement; lost reply repeats the same run ID',async()=>{
 const ledger=new Set(),requests=[],digits={children:[],replaceChildren(...v){this.children=v},setAttribute(k,v){this[k]=v}},label={};
 const root={hidden:true,querySelector:s=>s==='.check-digits'?digits:label};
 const window={},document={getElementById:()=>root,createElement:()=>({classList:{add(){}},textContent:''})};let lose=true;
 const fetch=async(_,options)=>{const p=JSON.parse(options.body);requests.push(p);if(p.action==='complete'){ledger.add(p.check_id);if(lose){lose=false;throw Error('lost acknowledgement');}}
  return {ok:true,json:async()=>({count:1100+ledger.size})};};
 vm.runInNewContext(fs.readFileSync(__dirname+'/../web-staging/checks-completed.js','utf8'),{window,document,fetch,AbortSignal});
 const options={apiBase:'https://local.invalid',credentials:{},id:'11111111-1111-4111-8111-111111111111',states:['CA'],ein:'123456789'};
 await window.CCCompletedChecks.load(options);assert.equal(ledger.size,0);assert.equal(digits.children.map(x=>x.textContent).join(''),'1100');
 window.CCCompletedChecks.completed(options);await new Promise(r=>setImmediate(r));assert.equal(ledger.size,1);
 assert.deepEqual(requests.filter(x=>x.action==='complete').map(x=>x.check_id),[options.id,options.id]);
 assert.equal(digits.children.map(x=>x.textContent).join(''),'1101');
 await window.CCCompletedChecks.load(options);assert.equal(ledger.size,1);
 window.CCCompletedChecks.completed({...options,id:'22222222-2222-4222-8222-222222222222'});await new Promise(r=>setImmediate(r));assert.equal(ledger.size,2);
});
