const fs = require('fs'), vm = require('vm'), assert = require('assert');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '../web-staging/index.html'), 'utf8');
function section(name, next) { return html.slice(html.indexOf('    function '+name+'('), html.indexOf('    function '+next+'(')); }
const rows = [];
let exported = '';
const panel = () => ({ classList: {toggle(){},remove(){}}, scrollIntoView(){} });
const context = {latestResults: [], internalUnlocked:false, resultRows:{appendChild(row){rows.push(row.innerHTML)}},
  generateReportButton:panel(), reportMessage:{}, resultTimestamp:{}, resultPanel:panel(), downloadExcelButton:panel(), downloadLeadLogButton:panel(), fullPictureCta:panel(),
  document:{createElement(){return {click(){}}}}, Blob: class {constructor(parts){exported=parts.join('')}}, URL:{createObjectURL(){return 'blob:test'},revokeObjectURL(){}},
  formatEin:x=>x,statusClass:()=>'',boldStatuses:x=>x,commentsWithRegistryFooter:r=>r.comments || ''};
vm.createContext(context);
vm.runInContext(section('escapeHtml','commentsWithRegistryFooter')+section('renderResults','downloadLeadLog')+section('downloadExcel','fallbackResult'), context);
const states='AK AR CA CO CT DC FL HI KS KY LA MA MD ME MI MN MS ND NH NJ NM NY OH OK OR PA RI SC VA WA WI WV'.split(' ');
context.input=states.map(state=>({state,organization_name:'Example Foundation',ein:'012345678',status:'Current',comments:'Control'}));
vm.runInContext('renderResults(input, true); downloadExcel();', context);
assert.equal(rows.length,32);
for(const row of rows){const cells=[...row.matchAll(/<td\b[^>]*>([\s\S]*?)<\/td>/g)].map(m=>m[1]);assert.equal(cells.length,7);assert.equal(cells[4].replace(/<[^>]*>/g,''),'');assert.equal(cells[5].replace(/<[^>]*>/g,''),'');}
assert(!exported.includes('Unavailable'));assert(!exported.includes('Not available'));
assert(exported.includes('Initial Registration Date'));assert(exported.includes('Last Renewal / Filed Year'));
for(const row of [...exported.matchAll(/<tr>(.*?)<\/tr>/g)].slice(1)){const cells=[...row[1].matchAll(/<td>(.*?)<\/td>/g)].map(m=>m[1]);assert.equal(cells[6],'');assert.equal(cells[7],'');}
context.input=[{...context.input[0],registration_date:'2010-02-03',registration_date_source_label:'Initial Issue Date',renewal_date:'2026-06-01',renewal_date_source_label:'Issue Date'}];
vm.runInContext('renderResults(input, true); downloadExcel();',context);
assert(exported.includes('2010-02-03'));assert(exported.includes('2026-06-01'));assert(rows.at(-1).includes('Initial Issue Date'));assert(rows.at(-1).includes('Issue Date'));
for(const [value,label] of [['2024','Filed year'],['2025-06-30','Filed period ending'],['2026-06-01','Renewal filed']]){
 context.input=[{...context.input[0],renewal_filing_value:value,renewal_filing_label:label,renewal_filing_note:'State source',renewal_filing_source_url:'https://registry.example/selected'}];
 vm.runInContext('renderResults(input, true); downloadExcel();',context);
 const cells=[...rows.at(-1).matchAll(/<td\b[^>]*>([\s\S]*?)<\/td>/g)].map(m=>m[1]);
 assert.equal(cells.length,7);assert(cells[5].includes(value));assert(cells[5].includes(label));
 assert(cells[5].includes('class="whitespace-nowrap"'));
 assert(cells[5].indexOf(value)<cells[5].indexOf(label));assert(exported.includes(value));assert(exported.includes(label));
 if(value==='2024')assert(!exported.includes('2024-12-31'));
}
assert(!html.includes('Initial / Original Registration Date'));assert(!html.includes('<th>Last Renewal Date</th>'));
for(const script of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)){if(script[1].trim())new vm.Script(script[1]);}
console.log('PASS: 32-state blank cells; two populated date columns; Excel labels/values; inline JavaScript syntax');
