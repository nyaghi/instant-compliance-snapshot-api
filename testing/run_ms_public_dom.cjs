const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const content=fs.readFileSync(path.join(process.env.CC_TEST_TRIAL_DIR||path.join(__dirname,'..','browser-connector'),'registry-content.js'),'utf8')
  .replace('  function registryDocumentReady() {','  globalThis.msTest={msGrid};\n  function registryDocumentReady() {');
function gridFixture(pager, data){
  const name='Fixture Charity';
  const row={querySelectorAll:()=>data.map(v=>({innerText:v})),querySelector:sel=>sel==='a.k-grid-Details'?{}:null};
  const grid={getClientRects:()=>[{}],getAttribute:()=>null,
    querySelector:sel=>sel==='.k-pager-info'?{innerText:pager}:null,
    querySelectorAll:sel=>sel==='tbody tr[role="row"]'&&data.length?[row]:[]};
  const window={};window.top=window;
  const document={querySelector:sel=>sel.startsWith('#ContentPlaceHolder1_')?{value:name}:sel==='#kendoSearchResults'?grid:null};
  const context=vm.createContext({window,document,location:{origin:'https://charities.sos.ms.gov'},
    crypto:{randomUUID:()=> 'test'},chrome:{runtime:{id:'fixture',onMessage:{addListener(){}}}}});
  vm.runInContext(content,context);
  return context.msTest.msGrid({name});
}
test('completed public Mississippi no-match message yields zero rows',()=>{
  const found=gridFixture('No Matches Found.',[]);
  assert.equal(found.total,0);assert.equal(found.rows.length,0);
});
test('matched public result retains identifier and raw status',()=>{
  const found=gridFixture('1 - 1 of 1 items',['Fixture Charity','100000800','Current - Registered','Details']);
  assert.equal(found.total,1);assert.equal(found.rows[0].identifier,'100000800');
  assert.equal(found.rows[0].raw_status,'Current - Registered');
});
test('truncated public result page cannot certify a negative',()=>{
  assert.throws(()=>gridFixture('1 - 1 of 2 items',['Fixture Charity','100000800','Current - Registered','Details']),/REGISTRY_RESPONSE_INCOMPLETE/);
});
