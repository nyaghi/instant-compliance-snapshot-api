const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

test('Sales-format export uses only settled Standard rows and no lookup',()=>{
  const events={},created=[];
  const element=()=>({classList:{hidden:true,toggle(name,value){if(name==='hidden')this.hidden=value;}},
    after(){},setAttribute(){},addEventListener(name,fn){this[name]=fn;},remove(){},click(){this.clicked=true;}});
  const insight=element();
  const document={getElementById:id=>id==='generateReportButton'?insight:null,
    createElement:()=>{const item=element();created.push(item);return item;},body:{appendChild(){} }};
  let html='',downloads=0,searches=0;
  const context={document,location:{origin:'https://charityclarity-final-four-29-2.onrender.com'},
    window:{addEventListener(name,fn){events[name]=fn;},CCSales:{displayStatus:r=>r.status==='Not Registered'?'Not Found':r.status}},
    performance:{now:()=>5},Blob:class {constructor(parts){html=parts.join('');}},
    URL:{createObjectURL:()=> 'blob:trial',revokeObjectURL(){},},
    setTimeout(){},Date,fetch(){searches++;throw Error('No network allowed');}};
  context.URL=Object.assign(URL,{createObjectURL:context.URL.createObjectURL,revokeObjectURL:context.URL.revokeObjectURL});
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../deployment/insight/sales-extract.js'),'utf8'),context);
  const button=created[0];
  assert.equal(button.classList.hidden,true);
  events['cc-standard-results']({detail:{results:[
    {organization_name:'Generic Aid',ein:'12-3456789',state:'NC',status:'Current',comments:'SECRET COMMENT',renewal_date:'SECRET DATE'},
    {organization_name:'Generic Aid',ein:'12-3456789',state:'NJ',status:'Not Registered'}]}});
  assert.equal(button.classList.hidden,false);
  button.click();
  assert.equal(searches,0);
  assert.match(html,/<th>Organization<\/th><th>EIN<\/th><th>State<\/th><th>Status<\/th>/);
  assert.match(html,/<td>Not Found<\/td>/);
  assert.doesNotMatch(html,/SECRET COMMENT|SECRET DATE|Renewal Date|Initial Registration Date/);
  assert.equal(created.at(-1).clicked,true);
});
