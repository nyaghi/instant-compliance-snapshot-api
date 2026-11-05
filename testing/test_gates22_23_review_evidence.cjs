const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element {
  constructor(tag){this.tag=tag;this.children=[];}
  appendChild(e){this.children.push(e);return e;}
}
function render(result){
  const window={},parent=new Element('td');
  vm.runInNewContext(fs.readFileSync(__dirname+'/../web-staging/identity-review.js','utf8'),
    {window,URL,document:{createElement:tag=>new Element(tag)}});
  window.CCIdentityReview.renderEvidence(parent,result);
  return parent.children;
}
const pdf='/state-snapshots/'+'a'.repeat(64)+'.pdf';
test('all bound candidate originals are recognized without accepting identity',()=>{
  for(const state of ['CA','MA','MD','MI','OR','VA','WA','RI','NC']) {
    const candidates=[{name:'Example Research Center',evidence_url:pdf,decision:''}];
    const result={state,status:'Needs Review',evidence_capture:'unavailable',identity_review:{candidates}};
    const before=JSON.stringify(result),els=render(result);
    assert.ok(els.some(e=>e.textContent==='View the state snapshots in the candidate records below.'));
    assert.ok(!els.some(e=>(e.textContent||'').includes('unavailable')));
    assert.equal(JSON.stringify(result),before);
  }
});
test('one missing or foreign candidate PDF cannot masquerade as complete evidence',()=>{
  for(const missing of ['', 'https://unrelated.example/doc.pdf']) {
    const els=render({state:'MA',status:'Needs Review',evidence_capture:'unavailable',
      identity_review:{candidates:[{evidence_url:pdf},{evidence_url:missing}]}});
    assert.ok(els.some(e=>e.textContent==='State snapshot unavailable for this check.'));
  }
});
test('rejected candidate does not regain a snapshot and negative keeps query history',()=>{
  const els=render({state:'MA',status:'Not Registered',success:true,identity_review_evidence_final:true,
    evidence_url:pdf,search_history_url:'/state-evidence/'+'b'.repeat(64)+'/search-history.pdf',
    identity_review:{candidates:[{evidence_url:pdf,decision:'reject'}]}});
  assert.equal(els.filter(e=>e.tag==='a').length,1);
  assert.equal(els[0].textContent,'View Names Searched (PDF)');
});
