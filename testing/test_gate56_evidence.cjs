const {test}=require('node:test');
const assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm'), path=require('node:path');
const dir=path.join(__dirname,'../deployment/staging_connector');
const roster=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/gate55/LOCAL-70.json')));
function clock() {
  let now=100000, next=0;
  const timers=new Map();
  const env={Date:{now:()=>now},setTimeout(fn,ms){timers.set(++next,{at:now+ms,fn});return next;},clearTimeout:id=>timers.delete(id)};
  async function finish(p) {
    let done=false,value,error;
    p.then(v=>{value=v;done=true;},e=>{error=e;done=true;});
    for(let n=0;n<200&&!done;n++){
      await new Promise(setImmediate);
      if(done)break;
      const item=[...timers].sort((a,b)=>a[1].at-b[1].at)[0];
      assert.ok(item,'pending operation needs a clock event');
      timers.delete(item[0]);now=item[1].at;item[1].fn();
    }
    assert.ok(done);if(error)throw error;return value;
  }
  return {env,finish,delay:(ms,v)=>new Promise(resolve=>env.setTimeout(()=>resolve(v),ms))};
}
const source=name=>fs.readFileSync(path.join(dir,name),'utf8');
async function northCarolina(org,delay,mismatch=false) {
  const c=clock(),url='https://www.sosnc.gov/online_services/search/charities_profile/123456';
  const query={state:'NC',operation:'detail',identifier:'EX002565',url};
  const job={registryState:'NC',tab:1,generation:1,pending:'query',command:{id:'query',query},activeExpiresAt:130000,ncSnapshotSpentMs:3007};
  let height=500,captured=false;
  const meta=()=>({url,public_text:org.name+' EX002565',source_detail:true,source_binding:'EX002565',
    document_id:captured&&mismatch?'changed':'original',source_viewport_width:900,source_page_fits:true});
  const ctx={...c.env,URL,Promise,owned:new Set([1]),isActive:()=>true,registryOrigin:()=>new URL(url).origin,
    P:{TRIAL_ORIGIN:'https://staging.invalid',sameQuery:(a,b)=>a===b},
    wfAwait:(_j,_site,fn)=>fn(),wfReturn:(_j,_site,x)=>x,wfEvent(){},
    chrome:{tabs:{get:async()=>({url}),sendMessage:async()=>meta()},debugger:{attach:async()=>{},detach:async()=>{},
      sendCommand:async(_id,method,params)=>{
        if(method==='Emulation.setDeviceMetricsOverride'){height=params.height;return c.delay(delay,{});}
        if(method==='Page.getLayoutMetrics')return {cssContentSize:{width:900,height:1000},cssLayoutViewport:{clientWidth:900,clientHeight:height,pageX:0,pageY:0}};
        if(method==='Page.captureScreenshot'){captured=true;return {data:'AA=='};}
        return {};
      }}}};
  vm.createContext(ctx);vm.runInContext(source('state-snapshot-worker.js'),ctx);
  return c.finish(ctx.captureStateSnapshot(job,query,'query'));
}
async function wisconsin(org,delay) {
  const c=clock(),url='https://apps.dfi.wi.gov/ice/berg/Registration/CredSummaryDetails.aspx?chid=9&h=8';
  const d={operation:'detail',state:'WI',url,ein:org.ein,name:org.name,identifier:'99-800',raw_status:'Current',issued_at:100,expires_at:175,deadline_schema:1};
  let attaches=0,closed=false;
  const metadata={url,ready:'complete',viewport_bound:true,viewport_width:900,text:'Credential Summary CHARITABLE ORGANIZATION (800) '+org.name+' 99-800 Current'};
  const ctx={...c.env,URL,AbortController,Promise,auroraBackgroundTrial:()=>true,
    CCSourceRail:{acquire:async()=>({job:{}}),release:async()=>{}},
    chrome:{runtime:{onMessage:{addListener(){}}},tabs:{create:()=>c.delay(5317,{id:19}),remove:async()=>{closed=true;}},
      debugger:{attach:()=>{attaches++;return c.delay(delay,{});},detach:async()=>{},sendCommand:async(_t,m)=>m==='Runtime.evaluate'?{result:{value:JSON.stringify(metadata)}}:m==='Page.captureScreenshot'?{data:'AA=='}:{}}}};
  vm.createContext(ctx);vm.runInContext(source('desktop-source-worker.js').replace("if(typeof module!=='undefined')module.exports={valid,bound};","globalThis.testCapture=capture;"),ctx);
  const result=await c.finish(ctx.testCapture(d,{tab:{id:3,windowId:2}},new AbortController().signal));
  assert.equal(attaches,1);assert.ok(closed);return result;
}
test('70 recorded identities, bounded NC detail completion and original document binding',async()=>{
  for(const org of roster){
    const image=await northCarolina(org,9600);
    assert.ok(image?.image,org.name);assert.equal(image.public_text,org.name+' EX002565');
    assert.equal(await northCarolina(org,9600,true),null);
    assert.equal(await northCarolina(org,18000),null);
  }
});
test('70 recorded identities, WI original slow attach resolves once and checks its own page',async()=>{
  for(const org of roster){
    const result=await wisconsin(org,3547);assert.equal(result.ok,true,JSON.stringify(result));assert.ok(result.public_text.includes(org.name));
    const late=await wisconsin(org,7000);assert.equal(late.ok,false);assert.equal(late.reason,'timeout:attach');
  }
});

for (const state of ['NY','GA']) test(state+' selected-detail capture on 70 recorded organizations',async()=>{
  assert.equal(new Set(roster.map(org=>org.ein)).size,70);
  for(const org of roster) for(const scenario of ['fresh','stale','fallback']){
    const c=clock(), ny=state==='NY';
    const origin=ny?'https://charities-search.ag.ny.gov':'https://verify.sos.ga.gov';
    const query=ny?{orgID:'12-34-56'}:{identifier:'CH12345',record_name:org.name};
    const url=origin+(ny?'/RegistrySearch/12-34-56':'/verification/Details.aspx');
    const job={registryState:state,tab:7,generation:1,pending:'q',command:{id:'q',query},activeExpiresAt:130000};
    let captured=false,direct=0,frames=0,height=600;
    const meta=()=>({url,public_text:org.name+' '+(ny?query.orgID:query.identifier),
      document_id:captured&&scenario==='stale'?'replacement':'original',source_binding:org.ein,
      source_viewport_width:1024,source_page_fits:true,source_ga_primary_ready:true,
      source_ga_primary_fits:true,source_ga_primary_bottom:900});
    const ctx={...c.env,URL,Promise,owned:new Set([7]),isActive:()=>true,registryOrigin:()=>origin,
      P:{TRIAL_ORIGIN:'https://staging.invalid',NY:origin,sameQuery:(a,b)=>a===b},
      wfAwait:(_j,_s,fn)=>fn(),wfEvent(){},wfReturn:(_j,_s,v)=>v,
      CCOwnedSourcePixels:{capture:async(tab,opts,scope)=>{
        assert.equal(tab,7);assert.ok(scope.alive());frames++;
        if(scenario==='fallback')throw Error('no fresh frame');
        captured=true;return {data:'AQ=='};
      }},
      chrome:{tabs:{get:async()=>({url}),sendMessage:async()=>meta()},debugger:{attach:async()=>{},detach:async()=>{},
        sendCommand:async(_t,cmd,options)=>{
          if(cmd==='Emulation.setDeviceMetricsOverride')height=options.height;
          if(cmd==='Page.getLayoutMetrics')return {cssContentSize:{width:1024,height:900},cssLayoutViewport:{clientWidth:1024,clientHeight:height,pageX:0,pageY:0}};
          if(cmd==='Page.captureScreenshot'){direct++;captured=true;return {data:'AA=='};}
          return {};
        }}}};
    vm.createContext(ctx);vm.runInContext(source('state-snapshot-worker.js'),ctx);
    const out=await c.finish(ctx.captureStateSnapshot(job,query,'q'));
    assert.equal(frames,1);assert.equal(direct,scenario==='fallback'?1:0);
    assert.equal(out?.image,scenario==='stale'?undefined:scenario==='fresh'?'AQ==':'AA==');
    assert.equal(job.snapshotCleanupBusy,undefined);
  }
});
