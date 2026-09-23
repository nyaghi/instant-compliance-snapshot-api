const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process');
const {setup}=require('./sales_test_dom.cjs');
const root=path.resolve(__dirname,'..');
test('32 states, zero defaults, no preset dropdown; explicit select all and clear',()=>{
 const c=setup();assert.equal(c.inputs.length,32);assert(c.inputs.some(x=>x.value==='DC'));assert(c.inputs.some(x=>x.value==='RI'));
 assert(c.inputs.every(x=>!x.checked));c.elements.ccSalesMode.onclick();assert(c.inputs.every(x=>!x.checked));
 assert(!c.elements.ccSalesPanel.innerHTML.includes('<select'));assert(c.elements.ccSalesMode.parentElement.innerHTML.includes('fill="#FFD54F"'));
 c.elements.ccSalesSelectAll.onclick();assert(c.inputs.every(x=>x.checked));c.elements.ccSalesClear.onclick();assert(c.inputs.every(x=>!x.checked));
});
test('switching preserves manual subset and Standard selections',()=>{
 const c=setup();c.inputs[4].checked=true;c.elements.ccSalesMode.onclick();c.elements.ccStandardMode.onclick();c.elements.ccSalesMode.onclick();
 assert.deepEqual(c.inputs.filter(x=>x.checked).map(x=>x.value),['CT']);assert.equal(c.standard[0].hidden,true);c.elements.ccStandardMode.onclick();assert.equal(c.standard[0].hidden,false);
});
test('no selection and locked staging cannot send checks',async()=>{
 const c=setup();c.elements.ccSalesMode.onclick();await c.submit();assert.match(c.elements.ccSalesError.textContent,/Select at least/);assert.equal(c.calls.length,0);
 c.inputs[0].checked=true;c.context.internalUnlocked=false;await c.submit();assert.match(c.elements.ccSalesError.textContent,/Unlock staging/);assert.equal(c.calls.length,0);
});
test('all 32 use exactly 15 total lanes including NY and render progressively',async()=>{
 const c=setup();c.elements.ccSalesMode.onclick();c.elements.ccSalesSelectAll.onclick();const run=c.submit();
 assert.equal(c.calls.length,15);assert.equal(c.calls[0][3],'NY');assert.equal(c.elements.ccSalesStates.disabled,true);assert.equal(c.elements.ccStandardMode.disabled,true);
 await c.submit();assert.equal(c.calls.length,15);c.elements.ccSalesClear.onclick();assert(c.inputs.every(x=>x.checked));
 c.finish('AK',{state:'AK',status:'Current'});await new Promise(setImmediate);
 assert.equal(c.calls.length,16);assert.equal(c.elements.ccSalesRows.children.find(x=>x.dataset.state==='AK').children[1].children[0].textContent,'Current');assert.match(c.elements.ccSalesProgress.textContent,/1 of 32/);
 await c.drain();await run;assert.equal(c.peak,15);assert.equal(c.elements.ccSalesPanel.dataset.peakConcurrency,'15');assert.equal(c.calls.length,32);assert.equal(c.events[0].detail.results.length,32);assert.equal(c.elements.ccSalesRun.disabled,false);
 assert(c.calls.every(args=>args[5]===false&&args[6].length===0));
});
test('chosen DC RI subset only; rejection cannot become Not Found; next run clean',async()=>{
 const c=setup();c.elements.ccSalesMode.onclick();for(const i of c.inputs)i.checked=['DC','RI'].includes(i.value);
 let run=c.submit();assert.equal(c.calls.length,2);c.finish('DC',new Error('Timeout'));c.finish('RI',{status:'Current',comments:'Control'});await run;
 assert.equal(c.events[0].detail.results.find(r=>r.state==='DC').status,'Unable to Confirm');assert.equal(c.elements.ccSalesRows.children.length,2);
 c.elements.ccSalesClear.onclick();c.inputs[0].checked=true;run=c.submit();await c.drain();await run;assert.equal(c.elements.ccSalesRows.children.length,1);assert.equal(c.events[1].detail.results.length,1);
});
test('Standard inline scripts, master, discovery and connector unchanged from pre-restoration release',()=>{
 const previous=file=>cp.execFileSync('git',['show','e069ad6:'+file],{cwd:root,encoding:'utf8',maxBuffer:20*1024*1024}).replaceAll('\r\n','\n');
 const current=file=>fs.readFileSync(path.join(root,file),'utf8').replaceAll('\r\n','\n');
 const scripts=t=>[...t.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)].map(x=>x[1]).filter(x=>x.trim()).join('\n');
 assert.equal(scripts(current('web-staging/index.html')),scripts(previous('web-staging/index.html')));
 for(const file of ['registry_snapshot_server.py','web-staging/organization-identity.js','web-staging/ny-connector.js'])assert.equal(current(file)===previous(file),true,file);
});
