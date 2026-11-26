const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('deployment/staging_connector/registry-content.js','utf8');
const helper = source.slice(source.indexOf('  function ilObserveDetailClick('),
    source.indexOf('  async function ilOpenSelectedDetail('));
const origin = 'https://charitable.illinoisattorneygeneral.gov';

function fixture(record, options = {}) {
  let clock = 1000, count = 0, observer, timerId = 0, clicks = 0, stopped = false;
  const timers = new Map();
  const trace = [];
  const query = {identifier: record.ein.replace(/\D/g, '').slice(0,8)};
  const row = {id:query.identifier};
  const button = {disabled:false,getAttribute:()=>null,click:()=>{clicks++;}};
  const doc = {
    querySelector: () => options.dialog ? {} : null,
    querySelectorAll: selector => selector === 'button'
      ? [{innerText:'Search',disabled:!!options.verification}]
      : options.loading ? [{}] : [],
  };
  const context = {
    Date:{now:()=>clock}, performance:{now:()=>clock}, URL, location:{origin},
    PerformanceObserver:class {
      constructor(cb){observer=cb;}
      observe(){ count++; }
      disconnect(){ stopped=true; }
    },
    setTimeout:(f,n)=>{const id=++timerId; timers.set(id, {f,t:clock+n}); return id;},
    clearTimeout:id=>timers.delete(id), document:doc,
    visible:obj=>!!obj, text:el=>el.innerText,
    ilSelectedVisibleRow:given=>!options.changed && given.identifier===row.id ? row : null,
    wfcActive:new Map([[1,{}]]),wfcEvent:(_ctx,_stage,outcome,data)=>trace.push([outcome,data]),
  };
  const detail = vm.runInNewContext(helper+'\nilObserveDetailClick',context)(query,row,button,25000);
  const send = (statuses, fields={}) => observer({getEntries:()=>statuses.map(status=>({
    startTime:1000, initiatorType:'xmlhttprequest',responseStatus:status,duration:100,
    name:origin+'/RegistrationSearch/Details?test-only=omitted', ...fields,
  }))});
  const at = (t) => {clock=t; for(const [id,item] of timers) if(item.t<=clock){timers.delete(id);item.f();}};
  detail.click();
  return {send,at,detail,trace,clicks:()=>clicks,observation:()=>[count,stopped,timers.size]};
}

const file=process.env.CC_IL_RECOVERY_ROSTER;
test('archived identities receive one bounded retry only after a completed transient detail response', {skip:!file}, () => {
  const roster=JSON.parse(fs.readFileSync(file,'utf8'));
  assert.ok(new Set(roster.map(x=>x.ein)).size >= 100);
  for(const record of roster) {
    const healthy=fixture(record);
    healthy.send([200]);healthy.at(6000);healthy.detail.stop();
    assert.equal(healthy.clicks(),1,record.ein);
    const transient=fixture(record);
    transient.send([502]);transient.at(1500);
    assert.equal(transient.clicks(),2,record.ein);
    transient.send([502]);transient.at(4000);transient.detail.stop();
    assert.equal(transient.clicks(),2,record.ein);
    assert.deepEqual(transient.observation(),[1,true,0]);
    const pending=fixture(record);
    pending.at(18000);pending.detail.stop();
    assert.equal(pending.clicks(),1,record.ein);
  }
});

test('verification, moved rows, a pending modal and active loading protect the original path', () => {
  const record={ein:'13-1624103'};
  for (const flags of [{verification:true},{changed:true},{dialog:true},{loading:true}]) {
    const test=fixture(record,flags);
    test.send([500]);test.at(1800);test.detail.stop();
    assert.equal(test.clicks(),1);
  }
});

test('denials, late responses, foreign URLs, overlap and stopped observers cause no retry', () => {
  const record={ein:'13-1624103'};
  for (const [statuses,fields,t,earlyStop] of [
    [[403],{},1800,false],[[429],{},1800,false],[[503],{},1800,false],
    [[0],{},1800,false],[[502],{},26000,false], [[502,502],{},1800,false],
    [[502],{name:'https://example.com/RegistrationSearch/Details'},1800,false],
    [[502],{startTime:900},1800,false],[[502],{},1800,true],
  ]) {
    const test=fixture(record);
    test.send(statuses,fields);
    if(earlyStop)test.detail.stop();
    test.at(t);
    assert.equal(test.clicks(),1);
    test.detail.stop();
  }
});
