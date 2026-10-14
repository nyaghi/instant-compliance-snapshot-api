const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path'),{test}=require('node:test');
const root=path.resolve(__dirname,'..');
function element(tag){return {tag,children:[],textContent:'',appendChild(e){this.children.push(e)},setAttribute(){},addEventListener(){}};}
function labels(el){return [el.tag==='button'?el.textContent:null,...el.children.flatMap(labels)].filter(Boolean);}
function rendered(state,complete,decision,status='Unable to Confirm'){const ctx={document:{createElement:element},window:{},URL};vm.runInNewContext(fs.readFileSync(path.join(root,'web-staging/identity-review.js'),'utf8'),ctx);const el=element('div');ctx.window.CCIdentityReview.render(el,{state,status,identity_review:{search_complete:complete,candidates:[{id:'c1',name:'Specific Charity',identifier:'SOURCE123',decision}]}},()=>{},()=>{});return labels(el);}
test('incomplete NC rejection retains Retry and Undo',()=>{const buttons=rendered('NC',false,'reject');assert(buttons.includes('Retry NC'));assert(buttons.includes('Undo match'));});
test('completed rejected search remains conclusive without Retry',()=>{assert(!rendered('NC',true,'reject','Not Registered').includes('Retry NC'));});
test('ordinary unresolved states keep Retry and existing decisions stay unchanged',()=>{assert(rendered('NV',false,undefined).includes('Retry NV'));assert(!rendered('WI',false,'reject').includes('Retry WI'));assert(!rendered('NC',false,'accept').includes('Retry NC'));});
for(const file of ['index.html','instant-compliance-snapshot.html'])test(file+' NC Retry performs a registry lookup with the signed identity token',async()=>{
 const src=fs.readFileSync(path.join(root,'web-staging',file),'utf8'),start=src.indexOf('    async function retryStateResult(original)'),end=src.indexOf('    function renderResults(',start);assert(start>0&&end>start);
 let reviews=0,payload=null;const ctx={window:{CCNYConnector:{lookup:async p=>{payload=p;return {status:'Unable to Confirm'};}}},reviewIdentity:async()=>{reviews++;},latestResults:[],email:{value:'reviewer@example.test'},adminPasscode:{value:'test-only'},getDeviceId:()=> 'test-device',renderResults(){}};
 vm.runInNewContext(src.slice(start,end),ctx);const original={state:'NC',ein:'123456789',organization_name:'Specific Charity - North Branch',reviewed_alternate_names:['Authorized Name'],identity_review:{search_complete:false,token:'signed-server-token',candidates:[{id:'c1',decision:'reject'}]}};
 await ctx.retryStateResult(original);assert.equal(reviews,0);assert.equal(payload.identity_review_token,'signed-server-token');assert.equal(payload.state,'NC');assert.deepEqual(Array.from(payload.alternate_names),['Authorized Name']);
});
