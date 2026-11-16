const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('deployment/staging_connector/alerts-background.js','utf8');
function fixture(hour=23){
 const origin='https://example.test',session={},local={ccAlertsProfile:'p'.repeat(43)},tabs=new Map([[1,{id:1,url:origin+'/'}]]);
 let listener,alarm,created=0,clock=1000000,jobs=[];
 const storage=data=>({get:async key=>({[key]:structuredClone(data[key])}),set:async value=>Object.assign(data,structuredClone(value)),remove:async key=>{delete data[key];}});
 const chrome={runtime:{onMessage:{addListener:fn=>listener=fn},onStartup:{addListener(){}},onInstalled:{addListener(){}}},
  alarms:{get:async()=>({}),create:async()=>{},clear:async()=>{},onAlarm:{addListener:fn=>alarm=fn}},
  storage:{session:storage(session),local:storage(local)},
  tabs:{get:async id=>{if(!tabs.has(id))throw Error('closed');return tabs.get(id);},remove:async id=>tabs.delete(id),
   create:async options=>{assert.equal(options.active,false);const id=100+(++created);const tab={id,...options};tabs.set(id,tab);return tab;}}};
 class Clock extends Date{static now(){return clock;}getHours(){return hour;}}
 vm.runInNewContext(source,{chrome,P:{TRIAL_ORIGIN:origin},URL,Date:Clock,allJobs:()=>jobs,
  allowedSender:s=>s.url?.startsWith(origin+'/')&&s.frameId===0});
 const sender=(id=1,documentId='doc1')=>({tab:{id},documentId,url:tabs.get(id)?.url,frameId:0});
 const call=(action,id=1,documentId='doc1')=>new Promise(resolve=>{
  const accepted=listener({type:'cc-alerts-background',action},sender(id,documentId),resolve);
  if(!accepted)resolve({ok:false});});
 const tick=async()=>{alarm({name:'charityclarity-alerts'});for(let i=0;i<6;i++)await new Promise(setImmediate);};
 return {call,tick,session,tabs,origin,get created(){return created;},advance:ms=>clock+=ms,setJobs:value=>jobs=value,setHour:value=>hour=value};
}

test('automatic runner only opens from 22:00 through 04:59 local time',async()=>{
 for(const hour of [5,9,17,21]){const f=fixture(hour);await f.tick();assert.equal(f.created,0);assert.equal((await f.call('foreground-start')).ok,true);}
 for(const hour of [22,23,0,4]){const f=fixture(hour);await f.tick();assert.equal(f.created,1);}
});

test('five a.m. prevents the next organization but preserves the in-progress runner until done',async()=>{
 const f=fixture(4);await f.tick();const id=f.session.ccAlertsRunnerTab.id;f.setHour(5);
 assert.equal((await f.call('config',id)).reason,'OUTSIDE_OVERNIGHT_WINDOW');assert.ok(f.tabs.has(id));
 await f.call('done',id);assert.ok(!f.tabs.has(id));await f.tick();assert.equal(f.created,1);
 assert.equal((await f.call('foreground-start')).ok,true);
});
test('Aurora reservation blocks alarms until its explicit completion',async()=>{
 const f=fixture();assert.equal((await f.call('foreground-start')).ok,true);
 await f.tick();assert.equal(f.created,0);await f.call('foreground-end');await f.tick();assert.equal(f.created,1);
});
test('existing automatic check finishes its organization, cannot claim the next, and does not overlap Aurora',async()=>{
 const f=fixture();await f.tick();const id=f.session.ccAlertsRunnerTab.id;
 assert.equal((await f.call('config',id)).ok,true);
 assert.equal((await f.call('foreground-start')).reason,'ALERTS_CHECK_IN_PROGRESS');
 assert.equal((await f.call('config',id)).reason,'AURORA_CHECK_IN_PROGRESS');
 await f.call('done',id);assert.equal((await f.call('foreground-start')).ok,true);
 await f.tick();assert.equal(f.created,1);
});
test('simultaneous alarm and foreground request cannot both acquire',async()=>{
 const f=fixture();const a=f.tick(),b=f.call('foreground-start');const result=await b;await a;
 assert.ok(f.created===0&&result.ok || f.created===1&&result.reason==='ALERTS_CHECK_IN_PROGRESS');
});
test('old document cannot release the current document reservation',async()=>{
 const f=fixture();await f.call('foreground-start',1,'new');await f.call('foreground-end',1,'old');
 await f.tick();assert.equal(f.created,0);await f.call('foreground-end',1,'new');await f.tick();assert.equal(f.created,1);
});
test('closed tab and expired reservation recover without changing monitoring preference',async()=>{
 const f=fixture();await f.call('foreground-start');f.tabs.delete(1);await f.tick();assert.equal(f.created,1);
 const g=fixture();await g.call('foreground-start');g.advance(600001);await g.tick();assert.equal(g.created,1);
});
test('runner and unrelated paths cannot claim foreground or finish another owned runner',async()=>{
 const f=fixture();await f.tick();const id=f.session.ccAlertsRunnerTab.id;
 assert.equal((await f.call('foreground-start',id)).ok,false);
 f.tabs.set(2,{id:2,url:f.origin+'/alerts-runner.html'});
 assert.equal((await f.call('done',2)).ok,false);assert.ok(f.tabs.has(id));
});
