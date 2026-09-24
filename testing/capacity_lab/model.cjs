// Executes unchanged Standard/Sales schedulers with recorded response durations.
// No browser or network. Model times are not live throughput predictions.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'), dataRoot=process.argv[2], out=process.argv[3];
assert(dataRoot&&out,'Usage: node model.cjs <project root> <output directory>');
const evidence=path.join(dataRoot,'outputs/standard15-release-20260924');
const files=['staging-single-54-1517707.json','candidate-repeat-86-0481941.json','candidate-repeat-84-1267604.json'];
const controls=files.map(file=>JSON.parse(fs.readFileSync(path.join(evidence,file),'utf8').replace(/^\uFEFF/,'')));
const ny=JSON.parse(fs.readFileSync(path.join(evidence,'ny-postvalidation.json'),'utf8').replace(/^\uFEFF/,''));
const html=fs.readFileSync(path.join(root,'web-staging/index.html'),'utf8');
const begin=html.indexOf('    async function runStateChecks('),end=html.indexOf('\n    stateCheckboxes.forEach',begin);
const source=html.slice(begin,end),states=[...html.matchAll(/name="states" value="([A-Z]{2})"/g)].map(m=>m[1]);
const {setup}=require('../sales_test_dom.cjs'),tick=()=>new Promise(setImmediate);
const digits=s=>s.replace(/\D/g,'');

async function run(mode,n,slots,profiles){
 let now=0,nextId=0,active=0,done=0,peak=0;
 const timers=new Map(),waiting=[],profile=Array.from({length:profiles},()=>({active:false,ready:0,timer:null,waiting:[]}));
 const finished=[],runs=[],models=[];
 function later(fn,ms){const id=++nextId;timers.set(id,{at:now+ms,fn});return id;}
 function clear(id){timers.delete(id);}
 function pumpBackend(){while(active<slots&&waiting.length){const job=waiting.shift();if(job.stopped)continue;active++;peak=Math.max(peak,active);job.running=true;job.timer=later(()=>complete(job),job.ms);}}
 function pumpNy(p){if(p.active||!p.waiting.length||p.timer)return;if(now<p.ready){p.timer=later(()=>{p.timer=null;pumpNy(p);},p.ready-now);return;}
  const job=p.waiting.shift();if(job.stopped){pumpNy(p);return;}p.active=true;job.running=true;job.timer=later(()=>complete(job),job.ms);}
 function free(job){job.running=false;if(job.p){job.p.active=false;job.p.ready=now+3000;pumpNy(job.p);}else{active--;pumpBackend();}}
 function complete(job){if(job.stopped)return;clear(job.transportTimer);free(job);job.settled=true;job.resolve(structuredClone(job.result));}
 function request(i,state,signal){return new Promise((resolve,reject)=>{
  const c=controls[i%controls.length],nyRow=ny.find(r=>digits(r.ein)===digits(c.ein));
  const result=state==='NY'?nyRow.result:c.results.find(r=>r.state===state);
  assert(result,'Missing recorded response '+state);
  const job={resolve,reject,result,ms:1000*(state==='NY'?nyRow.seconds:result.lookup_seconds),stopped:false,running:false};
  const stop=()=>{job.stopped=true;clear(job.transportTimer);if(job.running){clear(job.timer);free(job);}else{const q=job.p?job.p.waiting:waiting;const at=q.indexOf(job);if(at>=0)q.splice(at,1);}};
  const abort=()=>{if(job.stopped||job.settled)return;stop();reject(Error('deadline'));};
  if(signal?.aborted){abort();return;}signal?.addEventListener('abort',abort,{once:true});
  if(state==='NY'){job.p=profile[i%profiles];job.p.waiting.push(job);pumpNy(job.p);}else{waiting.push(job);pumpBackend();}
  if(mode==='Standard')job.transportTimer=later(()=>{if(job.stopped||job.settled)return;stop();resolve({state,ein:c.ein,status:'Unable to Confirm',success:false,status_reason:'MODELED_TRANSPORT_TIME_LIMIT'});},300000);
 });}
 for(let i=0;i<n;i++){
  const c=controls[i%controls.length];
  if(mode==='Standard'){
   const ctx=vm.createContext({progressCount:{},progressBar:{style:{}},stateLaneBases:()=>['offline'],checkSingleState:(_l,_e,_email,state)=>request(i,state)});
   vm.runInContext(source,ctx);
   runs.push(ctx.runStateChecks(states,c.ein,'offline@example.test',c.organization).then(rows=>{done++;const expired=rows.filter(r=>r.status_reason==='MODELED_TRANSPORT_TIME_LIMIT').length;finished.push({seconds:now/1000,confirmed:rows.length-expired,deadline:expired});}));
  }else{
   const clock={performance:{now:()=>now},setTimeout:later,clearTimeout:clear,setInterval:()=>0,clearInterval:()=>{}};
   const f=setup({clock});models.push(f);f.context.requestSingleState=(...args)=>request(i,args[3],args[7].signal);
   f.elements.ccSalesMode.onclick();f.elements.ccSalesName.value=c.organization;f.elements.ccSalesEin.value=c.ein;f.elements.ccSalesSelectAll.onclick();
   runs.push(f.submit().then(()=>{done++;const r=f.events[0].detail;finished.push({seconds:r.seconds,confirmed:r.results.filter(r=>r.result.status_reason!=='SALES_TIME_LIMIT').length,deadline:r.results.filter(r=>r.result.status_reason==='SALES_TIME_LIMIT').length});}));
  }
 }
 let loops=0;
 while(done<n){assert(++loops<100000);await tick();if(done===n)break;assert(timers.size);now=Math.min(...[...timers.values()].map(t=>t.at));
  const due=[...timers].filter(([,t])=>t.at===now);for(const [id,t]of due)if(timers.delete(id))t.fn();await tick();}
 await Promise.all(runs);assert(finished.every(r=>r.confirmed+r.deadline===32));
 return {mode,organizations:n,profiles,modeled_backend_slots:slots,peak_backend_active:peak,
  all_finished_seconds:Math.max(...finished.map(r=>r.seconds)),mean_seconds:finished.reduce((s,r)=>s+r.seconds,0)/n,
  recorded_responses_received:finished.reduce((s,r)=>s+r.confirmed,0),deadline_results:finished.reduce((s,r)=>s+r.deadline,0),total_results:n*32};
}
(async()=>{
 const results=[];
 for(const mode of ['Standard','Sales']){
  results.push(await run(mode,1,24,1));
  for(const slots of [12,24,48,96,192])for(const profiles of [1,15])results.push(await run(mode,15,slots,profiles));
 }
 const report={warning:'RECORDED-DURATION MODEL, NOT LIVE PERFORMANCE. Three healthy controls are repeated five times for fifteen workflows. Recorded lookup durations may already contain server/registry waiting. No CPU/RAM, outages, new verification, cache gains or source variability are simulated. Successful receipt means replayed evidence, not fresh verification.',
  source_files:files,ny_source:'ny-postvalidation.json',ny_pacing_seconds:3,standard_request_timeout_seconds:300,
  ny_serial_15_seconds:5*ny.reduce((s,r)=>s+r.seconds,0)+14*3,
  results};
 fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'recorded-duration-model.json'),JSON.stringify(report,null,2));
 console.log(JSON.stringify(report,null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
