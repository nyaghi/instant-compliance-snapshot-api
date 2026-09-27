const {test}=require('node:test'),assert=require('node:assert/strict');
const {setup}=require('./sales_test_dom.cjs');
test('original Sales grouping preserves failures and source objects',()=>{
 const {context}=setup();
 const cases={'Current':'Current','Upcoming Filing':'Current','Delinquent':'Delinquent','Not Registered':'Not Found','Exempt':'Exempt','Pending':'Pending','Revoked':'Inactive','Suspended':'Inactive','Closed / Withdrawn / Canceled':'Inactive','Site Not Reachable':'Unable to Confirm','Needs Review':'Unable to Confirm','Unknown':'Unable to Confirm'};
 for(const [status,want] of Object.entries(cases)){const r={status,comments:'Evidence'};assert.equal(context.window.CCSales.displayStatus(r),want);assert.deepEqual(r,{status,comments:'Evidence'});assert.equal(context.window.CCSales.displayStatus({...r,success:false}),'Unable to Confirm');}
});
test('Sales is staging only',()=>{const c=setup({origin:'https://www.compliance-express.com'});assert.equal(c.context.window.CCSales,undefined);});

test('all 34 displayed state names and completed results stay alphabetical',async()=>{
 const c=setup();c.elements.ccSalesMode.onclick();c.elements.ccSalesSelectAll.onclick();const run=c.submit();
 const expected=['AK','AR','CA','CO','CT','DC','FL','GA','HI','IL','KS','KY','LA','ME','MD','MA','MI','MN','MS','NH','NJ','NM','NY','ND','OH','OK','OR','PA','RI','SC','VA','WA','WV','WI'];
 assert.deepEqual(c.inputs.map(x=>x.value),expected);
 assert.deepEqual(c.elements.ccSalesRows.children.map(x=>x.dataset.state),expected);
 assert.equal(c.calls[0][3],'NY'); // Scheduling priority must not determine display order.
 c.finish('NY',{state:'NY',status:'Current'});await new Promise(setImmediate);
 assert.deepEqual(c.elements.ccSalesRows.children.map(x=>x.dataset.state),expected);
 await c.drain();await run;
 assert.deepEqual(Array.from(c.events[0].detail.results,r=>r.state),expected);
});
