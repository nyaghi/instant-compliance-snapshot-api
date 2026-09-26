const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.events={};}
 appendChild(el){this.children.push(el);return el;}
 setAttribute(k,v){this[k]=v;} addEventListener(k,v){this.events[k]=v;}
}
function setup(result,decide=async()=>{},retry=async()=>{}){
 const window={},parent=new Element('td');
 vm.runInNewContext(fs.readFileSync(__dirname+'/../web-staging/identity-review.js','utf8'),{window,URL,document:{createElement:t=>new Element(t)}});
 window.CCIdentityReview.render(parent,result,decide,retry);
 const flat=e=>[e,...e.children.flatMap(flat)];return flat(parent);
}
const candidate={id:'verified-candidate',name:'<script>unsafe</script>',identifier:'REG123',location:'Boston, MA',source_url:'https://registry.example/123',raw_status:'Exempt'};
const result={state:'GA',status:'Needs Review',identity_review:{candidates:[candidate]}};
test('comments expose evidence and explicit identity actions without HTML injection',()=>{
 const els=setup(result);assert.ok(els.some(e=>e.textContent===candidate.name));assert.ok(els.some(e=>e.textContent==='Accept match'));
 assert.ok(els.some(e=>e.textContent==='Reject match'));assert.ok(!els.some(e=>e.innerHTML));
 assert.equal(els.find(e=>e.tag==='a').rel,'noopener noreferrer');
});
test('accept sends only candidate identity and action; status stays server-owned',async()=>{
 let args;const els=setup(result,async(...a)=>{args=a;});await els.find(e=>e.textContent==='Accept match').events.click();
 assert.deepEqual(args,['verified-candidate','accept']);
});
test('a failed submission preserves controls and shows a useful error',async()=>{
 const els=setup(result,async()=>{throw Error('The review expired. Rerun the state.');});
 await els.find(e=>e.textContent==='Reject match').events.click();
 assert.ok(els.some(e=>e.textContent==='The review expired. Rerun the state.'));assert.ok(els.filter(e=>e.tag==='button').every(e=>!e.disabled));
});
test('incomplete registry access offers retry, never an identity acceptance without a candidate',async()=>{
 let retried=false;const els=setup({state:'NY',status:'Site Not Reachable'},null,async()=>{retried=true;});
 assert.equal(els.filter(e=>e.tag==='button').length,1);await els.find(e=>e.textContent==='Retry NY').events.click();assert.equal(retried,true);
});
test('undo stays available after a completed identity decision',()=>{
 const els=setup({...result,status:'Exempt',identity_review:{candidates:[{...candidate,decision:'accept'}]}});
 assert.ok(els.some(e=>e.textContent==='Undo decision'));
});
test('script URLs are not rendered as source links',()=>{
 assert.ok(!setup({...result,identity_review:{candidates:[{...candidate,source_url:'javascript:alert(1)'}]}}).some(e=>e.tag==='a'));
});
