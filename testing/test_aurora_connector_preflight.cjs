const {test} = require('node:test');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const {webcrypto} = require('node:crypto');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

const origin = 'https://fixture-final-four.onrender.com';
const {connector, html, alias} = JSON.parse(execFileSync('python', ['-c', `
import json
from pathlib import Path
from unittest.mock import patch
from deployment import performance_lab as lab
origin = "${origin}"
read_original = Path.read_bytes
def render_checkout(path):
    data = read_original(path)
    return data.replace(b'\\r\\n', b'\\n') if path.suffix in {'.js','.html'} else data
with patch.object(lab, "trial_identity", return_value={"origin":origin,"permanent_staging":True}), patch.object(lab,"LAB_ORIGIN",origin), patch.object(Path, "read_bytes", render_checkout):
    print(json.dumps(dict(connector=lab.lab_asset("/ny-connector.js")[0].decode(),
                          html=lab.lab_asset("/")[0].decode(),
                          alias=lab.lab_asset("/instant-compliance-snapshot")[0].decode())))
`], {encoding:'utf8'}));
const caps = JSON.parse(readFileSync('deployment/staging_connector/worker.js','utf8')
  .match(/version: chrome\.runtime\.getManifest\(\)\.version, capabilities: (\[.*?), \.\.\.\(P\.TRIAL_ORIGIN/)[1] + ']');
caps.push('final-four-public-v1');
const handlerStart = html.indexOf('    form.addEventListener("submit", async (event) => {');
const handlerEnd = html.indexOf('      latestResults = [];', handlerStart) + '      latestResults = [];'.length;
assert.ok(handlerStart >= 0 && handlerEnd > handlerStart);

function fixture(replies = [], picked = ['TN','NV','AL','GA','IL','MS','NC','NM','NY','CA']) {
  let listener, submit, pings = 0, searches = 0, error = '', retry, focus = false;
  const button = {disabled:false,textContent:'Run CharityClarity Aurora'};
  const org = {value:'Example organization'};
  const callbacks = {preventDefault() {}};
  const window = {addEventListener(kind, fn) { if (kind==='message') listener=fn; },
    postMessage(message) {
      assert.equal(message.action, 'ping');
      const reply = replies[pings++];
      if (!reply) return;
      queueMicrotask(() => listener({source:window, origin,
        data:{...message, direction:'response', ok:true, version:'0.6.135',
          capabilities:reply, il_transport:{protocol:'il-bound-replies-v1',extension_id:'a'.repeat(32),lookup_id:null}}}));
    },
    CCIdentity:{ready:()=>true,names:()=>['Reviewed alias'],setBusy() {}}
  };
  const form = {addEventListener(_kind, fn) { submit=fn; }, requestSubmit:()=>submit(callbacks)};
  const context = vm.createContext({window,location:{origin},crypto:webcrypto,
    setTimeout:(fn,ms)=>{assert.equal(ms,5000);return setTimeout(fn,1);},clearTimeout,
    fetch:()=>{throw Error('Preflight cannot start a server check');},
    form,nyResultRefresh:false,connectorPreflightPending:false,submitButton:button,
    clearError() { error='';retry=null; },showError(text) { error=text; },
    selectedStates:()=>picked,organizationName:org,ein:{value:'12-3456789'},
    email:{value:'fixture@compliance-express.com',checkValidity:()=>true},
    stateLimit:()=>38,STAGING_ACCESS_REQUIRED:true,isComplianceExpressEmail:()=>true,
    adminPasscode:{value:'fixture'},internalUnlocked:true,namesRequired:()=>true,
    runAlternateNames:[],latestResults:['prior saved result'],recordStart:()=>searches++,
    errorBox:{append(_space, item) { retry=item; }},
    document:{createElement:()=>({addEventListener(_kind, fn) { this.click = fn; },focus() { focus=true; }})}
  });
  vm.runInContext(connector,context);
  vm.runInContext(html.slice(handlerStart,handlerEnd) + '\nrecordStart(); });',context);
  return {run:form.requestSubmit,org,button,window,picked,get pings(){return pings;},
    get searches(){return searches;},get error(){return error;},
    get retry(){return retry;},get focus(){return focus;},get previous(){return context.latestResults;}};
}

test('healthy full selection gets one quick preflight and starts once', async () => {
  const f = fixture([caps]);
  await f.run();
  assert.equal(f.pings,1);
  assert.equal(f.searches,1);
  assert.equal(f.error,'');
});
test('initial silence auto-recovers after one bounded retry', async () => {
  const f = fixture([null,caps]);
  await f.run();
  assert.equal(f.pings,2);
  assert.equal(f.searches,1);
});
test('persistent outage keeps old results and Retry connectors starts a fresh check', async () => {
  const f = fixture([null,null,caps]);
  const first = f.run();
  assert.equal(f.button.disabled,true);
  assert.match(f.button.textContent,/Connecting/);
  await f.run(); // A repeat submission while waiting cannot start another check.
  await first;
  assert.equal(f.pings,2);
  assert.equal(f.searches,0);
  assert.equal(f.previous[0],'prior saved result');
  assert.match(f.error,/did not start/);
  assert.equal(f.retry.textContent,'Retry connectors');
  assert.equal(f.focus,true);
  assert.equal(f.button.disabled,false);
  await f.retry.click();
  assert.equal(f.pings,3);
  assert.equal(f.searches,1);
  assert.equal(f.error,'');
});
test('older extension gets an update message rather than registry results', async () => {
  const f = fixture([caps.filter(cap => cap!=='final-four-public-v1')]);
  await f.run();
  assert.equal(f.pings,1);
  assert.equal(f.searches,0);
  assert.match(f.error,/needs an update/);
});
test('missing connector script has the same actionable message', async () => {
  const f = fixture();
  delete f.window.CCNYConnector;
  await f.run();
  assert.equal(f.pings,0);
  assert.equal(f.searches,0);
  assert.match(f.error,/did not start/);
  assert.equal(f.retry.textContent,'Retry connectors');
});
test('edits during preflight cannot dispatch a check for the previous selection', async () => {
  const f = fixture([caps]);
  const pending = f.run();
  f.org.value = 'A different charity';
  await pending;
  assert.equal(f.searches,0);
  assert.match(f.error,/details changed/);
});
test('server-only checks bypass preflight and both Aurora aliases have the warning', async () => {
  const f = fixture([],['CA','OR']);
  await f.run();
  assert.equal(f.pings,0);
  assert.equal(f.searches,1);
  for (const page of [html,alias]) {
    assert.match(page,/id="errorBox" role="alert"/);
    assert.match(page,/Retry connectors/);
  }
});
