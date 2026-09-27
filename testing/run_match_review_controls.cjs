const fs=require('node:fs'),vm=require('node:vm'),test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web-staging/identity-review.js'),'utf8');
class Element {constructor(tag){this.tag=tag;this.children=[];this.events={};this.disabled=false;}appendChild(el){this.children.push(el);}setAttribute(k,v){this[k]=v;}addEventListener(k,v){this.events[k]=v;}}
function setup(decisions=[''],handler=async()=>{}){
 const root=new Element('div'),window={};const calls=[];
 vm.runInNewContext(source,{window,document:{createElement:t=>new Element(t)},URL});
 const result={state:'DC',status:'Needs Review',identity_review:{candidates:decisions.map((decision,i)=>({id:String(i),name:'Example '+i,source_url:'https://example.gov',decision}))}};
 const decide=async(id,action)=>{calls.push({id,action});await handler(id,action);};
 window.CCIdentityReview.render(root,result,decide,async()=>{});
 const walk=n=>[n,...n.children.flatMap(walk)],buttons=()=>walk(root).filter(n=>n.tag==='button');
 return {root,buttons,calls,by:label=>buttons().filter(b=>b.textContent===label)};
}
for(const selected of ['accept','reject'])test(selected+' remains disabled, opposite action and undo stay enabled',async()=>{
 const s=setup([selected]);assert.equal(s.buttons().length,3);
 const current=s.by(selected==='accept'?'Accept match':'Reject match')[0];assert.equal(current.disabled,true);assert.equal(current['aria-pressed'],'true');
 await current.events.click();assert.equal(s.calls.length,0);
 for(const b of s.buttons().filter(b=>b!==current))assert.equal(b.disabled,false);
 await s.by('Undo match')[0].events.click();assert.deepEqual(s.calls,[{id:'0',action:'clear'}]);assert.equal(current.disabled,true);
});
test('new candidate allows both decisions and no undo',()=>{const s=setup();assert.equal(s.by('Accept match')[0].disabled,false);assert.equal(s.by('Reject match')[0].disabled,false);assert.equal(s.by('Undo match').length,0);});
test('pending request locks all controls and cannot submit twice',async()=>{let resolve;const s=setup(['accept'],()=>new Promise(r=>resolve=r));const pending=s.by('Reject match')[0].events.click();assert.ok(s.buttons().every(b=>b.disabled));await s.by('Undo match')[0].events.click();assert.equal(s.calls.length,1);resolve();await pending;assert.equal(s.by('Accept match')[0].disabled,true);assert.equal(s.by('Reject match')[0].disabled,false);});
test('failed request preserves selected disabled action and enables alternatives',async()=>{const s=setup(['reject'],async()=>{throw Error('source unavailable')});await s.by('Accept match')[0].events.click();assert.equal(s.by('Reject match')[0].disabled,true);assert.equal(s.by('Accept match')[0].disabled,false);assert.equal(s.by('Undo match')[0].disabled,false);});
test('candidate decisions do not disable another candidate',()=>{const s=setup(['accept','reject','']);assert.deepEqual(s.by('Accept match').map(b=>b.disabled),[true,false,false]);assert.deepEqual(s.by('Reject match').map(b=>b.disabled),[false,true,false]);});
