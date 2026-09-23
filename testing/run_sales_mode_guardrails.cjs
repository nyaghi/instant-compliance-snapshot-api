const {test}=require('node:test'),assert=require('node:assert/strict');
const {setup}=require('./sales_test_dom.cjs');
test('original Sales grouping preserves failures and source objects',()=>{
 const {context}=setup();
 const cases={'Current':'Current','Upcoming Filing':'Current','Delinquent':'Delinquent','Not Registered':'Not Found','Exempt':'Exempt','Pending':'Pending','Revoked':'Inactive','Suspended':'Inactive','Closed / Withdrawn / Canceled':'Inactive','Site Not Reachable':'Unable to Confirm','Needs Review':'Unable to Confirm','Unknown':'Unable to Confirm'};
 for(const [status,want] of Object.entries(cases)){const r={status,comments:'Evidence'};assert.equal(context.window.CCSales.displayStatus(r),want);assert.deepEqual(r,{status,comments:'Evidence'});assert.equal(context.window.CCSales.displayStatus({...r,success:false}),'Unable to Confirm');}
});
test('Sales is staging only',()=>{const c=setup({origin:'https://www.compliance-express.com'});assert.equal(c.context.window.CCSales,undefined);});
