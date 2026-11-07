const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element {constructor(tag){this.tag=tag;this.children=[];}appendChild(e){this.children.push(e);return e;}}
function render(result){const window={},parent=new Element('td');vm.runInNewContext(fs.readFileSync(__dirname+'/../web-staging/identity-review.js','utf8'),{window,URL,document:{createElement:tag=>new Element(tag)}});window.CCIdentityReview.renderEvidence(parent,result);return parent.children;}
const pdf='/state-snapshots/'+'a'.repeat(64)+'.pdf',history='/state-evidence/'+'b'.repeat(64)+'/search-history.pdf';
const record={state:'CA',status:'Not Registered',success:true,matched_registry_name:'Example Museum',matched_registry_identifier:'12345',raw_status_text:'Entity Status: Withdrawn | Registration Type: Charitable Organization | Registration Status: Not Registered',evidence_url:pdf};
test('ND source timeout is not presented as an identity-review problem',()=>{
  const window={};vm.runInNewContext(fs.readFileSync(__dirname+'/../web-staging/identity-review.js','utf8'),{window});
  const result={state:'ND',status:'Site Not Reachable',success:false,reason_code:'RUNNER_TIMEOUT'};
  assert.equal(window.CCIdentityReview.statusLabel(result),'Site Not Reachable');
  assert.equal(window.CCIdentityReview.statusLabel({...result,identity_review:{candidates:[{}]}}),'Confirm match');
  assert.equal(window.CCIdentityReview.statusLabel({...result,status:'Unable to Confirm'}),'Review required');
});

test('CO bounded timeout keeps its explicit source failure label and identity guards',()=>{
  const window={};vm.runInNewContext(fs.readFileSync(__dirname+'/../web-staging/identity-review.js','utf8'),{window});
  const result={state:'CO',status:'Site Not Reachable',success:false,reason_code:'RUNNER_TIMEOUT'};
  assert.equal(window.CCIdentityReview.statusLabel(result),'Site Not Reachable');
  assert.equal(window.CCIdentityReview.statusLabel({...result,identity_review:{candidates:[{}]}}),'Confirm match');
  assert.equal(window.CCIdentityReview.statusLabel({...result,status:'Unable to Confirm'}),'Review required');
  assert.equal(window.CCIdentityReview.statusLabel({...result,state:'NJ'}),'Review required');
});
test('selected explicit CA nonregistration retains its original source link',()=>{
  const out=render(record);assert.ok(out.some(e=>e.tag==='a'&&e.textContent==='View State Snapshot (PDF)'));
  assert.ok(!out.some(e=>/unavailable/.test(e.textContent||'')));
});
test('ordinary empty searches and rejected candidates keep history only',()=>{
  for(const changed of [{state:'MD'},{matched_registry_identifier:''},{matched_registry_name:''},{raw_status_text:'No records found'},
      {identity_review_evidence_final:true,identity_review:{candidates:[{decision:'reject'}]}}]){
    const out=render({...record,...changed,search_history_url:history});
    assert.ok(!out.some(e=>e.tag==='a'&&e.textContent==='View State Snapshot (PDF)'));
    assert.ok(out.some(e=>e.tag==='a'&&e.textContent==='View Names Searched (PDF)'));
  }
});
