"""Isolated performance service entry point; all state checks use the master.

This deployment-only boundary supplies private lab authentication, local static
assets and telemetry. It is not a state adapter or a replacement status engine.
It must never be used to start the staging or production services.
"""
import base64
import hmac
import io
import json
import mimetypes
import os
from pathlib import Path
import sys
import threading
import time
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from deployment.lab_identity import configured_lab_origin, trial_identity, trial_access_expired, TRIAL_RELEASE_LABEL

LAB_ORIGIN = configured_lab_origin()
LAB_SERVICE_ID = 'srv-d8u0hsu7r5hc73aqfsg0'
DISABLED_CONNECTIONS = (
    'CE_SINGLE_STATE_OVERFLOW_API_URL', 'CE_SINGLE_STATE_OVERFLOW_API_URLS',
    'CE_BATCH_FANOUT_API_URL', 'CE_BATCH_FANOUT_API_URLS',
    'CE_WI_SIDECAR_URL', 'CE_NM_STATUS_SIDECAR_URL',
    'CE_GA_SIDECAR_URL', 'CE_LEAD_LOG_WEBHOOK_URL',
)


def validate_environment(env):
    trial = trial_identity(env) if env.get('CE_FINAL_FOUR_TRIAL') == '1' else None
    if env.get('CE_FINAL_FOUR_TRIAL') == '1' and trial is None:
        raise RuntimeError('29.2 requires its own active services and queue database')
    if env.get('PUBLIC_BASE_URL') != LAB_ORIGIN:
        raise RuntimeError('Performance entry point requires its isolated lab origin')
    service = env.get('RENDER_SERVICE_ID', LAB_SERVICE_ID)
    worker_allowed = (env.get('CE_LAB_ROLE') == 'worker'
        and service == env.get('CE_LAB_WORKER_SERVICE_ID')
        and env.get('RENDER_SERVICE_NAME') == 'charityclarity-performance-lab-worker-1')
    if trial is None and service != LAB_SERVICE_ID and not worker_allowed:
        raise RuntimeError('Performance entry point refuses another Render service')
    if service in ('srv-d8a38lnavr4c73d4ib30', 'srv-d82afqjrjlhs738j7or0'):
        raise RuntimeError('A protected staging service is never a lab worker')
    if not env.get('CE_APP_VERSION', '').endswith('-performance-lab'):
        raise RuntimeError('Performance version label required')
    if len(env.get('CE_LAB_ACCESS_KEY', '')) < 40:
        raise RuntimeError('A separate strong lab access key is required')
    if env.get('CE_STAGING_ACCESS_REQUIRED') != '1' or env.get('CE_PUBLIC_SINGLE_STATE_ONLY') != '1':
        raise RuntimeError('Private single-state access boundary required')
    if env.get('CE_BATCH_FANOUT_SINGLE_STATE_LOOKUPS') != '0':
        raise RuntimeError('Lab fanout must be disabled for the baseline')
    for key in DISABLED_CONNECTIONS:
        if env.get(key) != '':
            raise RuntimeError('Connection must be explicitly disabled: ' + key)
    if trial is None and env.get('CE_LAB_DURABLE_QUEUE') == '1':
        database = urlparse(env.get('CE_LAB_DATABASE_URL', ''))
        if database.scheme not in ('postgres', 'postgresql') or database.hostname not in (
            'dpg-dar6utvavr4c7380ou60-a', 'dpg-dar6utvavr4c7380ou60-a.oregon-postgres.render.com'
        ) or database.path != '/cc_performance_lab':
            raise RuntimeError('Durable queue requires the isolated lab database')


def valid_authorization(header, key):
    if header.startswith('Bearer '):
        candidate = header[7:]
    elif header.startswith('Basic '):
        try:
            user, candidate = base64.b64decode(header[6:], validate=True).decode().split(':', 1)
        except (ValueError, UnicodeError):
            return False
        if user != 'lab':
            return False
    else:
        return False
    return hmac.compare_digest(candidate.encode(), key.encode())


def blocked_app_host(host):
    host = str(host).lower().rstrip('.')
    return (host == 'compliance-express.com' or host.endswith('.compliance-express.com')
            or host.endswith('.onrender.com') or host.endswith('.trycloudflare.com'))


def install_http_egress_guard():
    # A second defense against accidentally reusing an application helper.
    # State registries and public IRS sources retain their existing paths.
    def audit(event, args):
        if event == 'socket.getaddrinfo' and blocked_app_host(args[0]):
            raise PermissionError('Performance lab cannot call an application environment')
    sys.addaudithook(audit)


def final_four_asset(name, text):
    """Trial-only presentation/transport assembly; no registry interpretation."""
    identity = trial_identity()
    if not identity:
        return text
    def replace(old, new, count=1):
        nonlocal text
        if text.count(old) != count:
            raise RuntimeError('29.2 asset no longer matches the approved template: ' + name)
        text = text.replace(old, new)
    if name == 'index.html':
        import re
        label = re.search(r'<label[^>]*><input type="checkbox" name="states" value="AK"[^>]* /> <span>Alaska</span></label>', text)
        if not label: raise RuntimeError('Missing approved state selector template')
        # Keep the existing selector's alphabetical display order. Its layout
        # does not control the separately sorted execution order.
        additions = [label[0].replace('value="AK"', 'value="'+state+'"').replace('>Alaska<', '>'+title+'<')
                     for state, title in [('AL','Alabama'),('NC','North Carolina'),('NV','Nevada'),('TN','Tennessee')]]
        selector = re.compile(r'<label[^>]*><input type="checkbox" name="states" value="[A-Z]{2}"[^>]* /> <span>[^<]+</span></label>')
        choices = list(selector.finditer(text))
        if len(choices) != 34:
            raise RuntimeError('29.2 state selector no longer matches the approved template')
        labels = [match[0] for match in choices] + additions
        labels.sort(key=lambda value: re.search(r'<span>([^<]+)</span>', value)[1].casefold())
        text = text[:choices[0].start()] + '\n\n                  '.join(labels) + text[choices[-1].end():]
        replace('!["IL", "GA"].includes(state)', '!["NY", "IL", "GA", "AL", "NC", "NV", "TN", "NM", "MS"].includes(state)')
        replace('["NY", "IL", "GA"].includes(state)', '["NY", "IL", "GA", "AL", "NC", "NV", "TN", "NM", "MS"].includes(state)')
        replace('alternateNames = runAlternateNames, {signal} = {}', 'alternateNames = runAlternateNames, {signal,mode="standard"} = {}')
        replace('alternate_names: alternateNames, signal,', 'alternate_names: alternateNames, signal, mode,')
        # Trial-only, in-memory diagnostics for incomplete public browser
        # lookups. This does not change registry requests or results.
        replace('            onProgress: (message) => {', '''            onProgress: (message, detail) => {
              if (detail && ["NM", "MS", "IL", "NV", "GA"].includes(detail.state)) {
                const events = window.__CCLabStateTrace ||= [];
                events.push({at: Date.now(), state: detail.state, stage: detail.stage || "",
                  action: detail.action || "", operation: detail.query?.operation || "",
                  query: detail.query?.name || "", reason: detail.reason || "",
                  ny_phase: detail.ny_phase || "", http_status: detail.http_status ?? null,
                  phase: detail.phase || "", diagnostic: detail.diagnostic || null,
                  page_visibility: detail.page_visibility || "",
                  trial_diagnostics: Array.isArray(detail.trial_diagnostics)
                    ? detail.trial_diagnostics.slice(-120) : null,
                  il_dom: Array.isArray(detail.il_dom) ? detail.il_dom : null,
                  nv_readiness: detail.nv_readiness || null,
                  nv_filings: detail.nv_filings || null});
                if (events.length > 2000) events.splice(0, events.length - 2000);
                let traceNode = document.getElementById("cc-lab-state-trace");
                if (!traceNode) {
                  traceNode = document.createElement("script");
                  traceNode.id = "cc-lab-state-trace";
                  traceNode.type = "application/json";
                  document.body.appendChild(traceNode);
                }
                traceNode.textContent = JSON.stringify(events);
              }''')
        # Keep the full first-pass timing evidence in the existing download.
        # An HTML comment leaves the visible spreadsheet unchanged and lets a
        # diagnostic survive a browser-control disconnect without another run.
        replace('      const blob = new Blob([html], { type: "application/vnd.ms-excel" });', '''      const labTrace = encodeURIComponent(JSON.stringify({
        schema:"cc-lab-trace-v1",exported_at:new Date().toISOString(),
        events:Array.isArray(window.__CCLabStateTrace)?window.__CCLabStateTrace:[]
      }));
      const blob = new Blob([`<!--CC_LAB_TRACE_V1:${labTrace}-->`,html], { type: "application/vnd.ms-excel" });''')
        replace('          result.status_reason = "NY_CONNECTOR_UNAVAILABLE";', '''          result.status_reason = "NY_CONNECTOR_UNAVAILABLE";
          result.reviewed_alternate_names = [...alternateNames];''')
        replace('v2026.09.29.1 &middot; Staging', 'v2026.09.'+TRIAL_RELEASE_LABEL+' &middot; Isolated Trial')
    elif name == 'optimized-workflows.js':
        # User-approved Sales contract: entered name/EIN, no alias preparation.
        # Keep the protected staging template unchanged.
        replace("states, aliases=[], mode='standard', credentials,", "states, aliases:providedAliases=[], mode='standard', credentials,")
        replace("    const results=new Map(), external=states.filter(s=>s==='IL'||s==='GA');", '''    const runStarted=Date.now();
    const trace=(stage,detail={})=>{
      const events=window.__CCLabStateTrace ||= [];
      events.push({at:Date.now(),state:"*",stage,elapsed_ms:Date.now()-runStarted,...detail});
      if(events.length>2000)events.splice(0,events.length-2000);
    };
    trace("workflow started",{mode,states:[...states]});
    const results=new Map(), external=states.filter(s=>s==='IL'||s==='GA');''')
        replace('      results.set(result.state,result);onResult(result);', '''      results.set(result.state,result);
      trace("state result",{state:result.state,status:result.status||"",reason:result.status_reason||""});
      onResult(result);''')
        replace('      connectorStarted=true;', '      connectorStarted=true;trace("browser collectors dispatched",{states:[...external]});')
        # Spread only Standard browser starts over 3.2 seconds at most. This
        # avoids a nine-tab Chrome launch burst without changing any state's
        # query plan, deadline, status interpretation, or the 60-second Sales
        # contract. Keep release/settlement behavior in Promise.all unchanged.
        replace('connector=Promise.all(external.map(async state=>{', '''connector=Promise.all(external.map(async (state, launchIndex)=>{
        if(mode==='standard' && launchIndex>0) {
          const launchDelayMs=launchIndex*400;
          trace("browser collector scheduled",{state,delay_ms:launchDelayMs});
          await new Promise(resolve=>setTimeout(resolve,launchDelayMs));
        }
        if(signal?.aborted) return;
        trace("browser collector launched",{state});''')
        replace('        token=accepted.token;', '        token=accepted.token;trace("backend workflow accepted",{progressive_external_release:accepted.progressive_external_release===true});')
        replace("            try{await call('release-external');released=true;}catch{signal?.throwIfAborted();}", "            try{await call('release-external');released=true;trace('external collectors released');}catch{signal?.throwIfAborted();}")
        replace('      return states.map(state=>results.get(state));', '      trace("workflow finished",{result_count:results.size});\n      return states.map(state=>results.get(state));', 2)
        replace("    const results=new Map(),", "    const aliases=mode==='sales'?[]:providedAliases;\n    const results=new Map(),")
        replace("const needsIdentity=mode==='sales'&&external.length>0&&aliases.length===0;", "const needsIdentity=false;")
        replace('signal, onResult=()=>{}, externalLookup} = options;', 'signal, onResult=()=>{}, externalLookup, sales_cutoff_seconds} = options;')
        replace('mode,consent:true,request_id:', 'mode,...(sales_cutoff_seconds!==undefined?{sales_cutoff_seconds}:{}),consent:true,request_id:')
        replace("states.filter(s=>s==='IL'||s==='GA')", "states.filter(s=>['NY','IL','GA','AL','NC','NV','TN','NM','MS'].includes(s))")
        replace("headers:{'Content-Type':'application/json'}", "headers:{'Content-Type':'application/json','Authorization':'Bearer '+credentials.admin_passcode}")
    elif name == 'sales-mode.js':
        replace("const VERSION = '2026.09.29.1-sales';", "const VERSION = '2026.09."+TRIAL_RELEASE_LABEL+"-sales-trial';")
        replace('const NAMES = {', 'const NAMES = {"AL":"Alabama","NC":"North Carolina","NV":"Nevada","TN":"Tennessee",')
        replace('Choose any or all 34 states.', 'Choose any or all ${STATES.length} states.')
        replace('Select all 34</button>', 'Select all ${STATES.length}</button>')
        replace('Staging · Sales Mode ${VERSION}', 'Isolated Trial · Sales Mode ${VERSION}')
        replace('{signal:controller.signal}', '{signal:controller.signal,mode:"sales"}', 2)
    elif name == 'ny-connector.js':
        diagnostic_source = (Path(__file__).resolve().parents[1]/'browser-connector'/'protocol.js').read_text(encoding='utf-8')
        diagnostic_source = diagnostic_source.split('// BEGIN NY_DIAGNOSTICS:',1)[1].split('\n',1)[1].split('// END NY_DIAGNOSTICS',1)[0]
        text = diagnostic_source + '\n' + text
        text = text.replace('cc-ny-staging-v1', 'cc-final-four-trial-v1')
        # The worker owns FIFO within each registry. A page-wide promise tail
        # would serialize unrelated registries before they reach those lanes.
        replace('const pending = lookupTail.then(() => performLookup(input));', 'return performLookup(input);')
        replace('    lookupTail = pending.catch(() => {});', '')
        replace('    return pending;', '')
        replace('state: registryState = "NY", signal })', 'state: registryState = "NY", signal, mode = "standard", sales_cutoff_seconds })')
        replace('...(Array.isArray(alternate_names) ? {alternate_names} : {})', '...(mode==="sales" ? {alternate_names:[]} : (Array.isArray(alternate_names) ? {alternate_names} : {}))')
        replace('{NY:"New York",IL:"Illinois",GA:"Georgia"}', '{NY:"New York",IL:"Illinois",GA:"Georgia",AL:"Alabama",NC:"North Carolina",NV:"Nevada",TN:"Tennessee",NM:"New Mexico",MS:"Mississippi"}')
        replace('    const supported = c =>', '    const finalFour = ["AL","NC","NV","TN","NM","MS"].includes(registryState);\n    const supported = c => (!finalFour || c.capabilities?.includes("final-four-public-v1")) &&')
        replace('API + "/api/ny-connector"', 'API + (finalFour ? "/api/final-four-connector" : "/api/ny-connector")')
        replace('headers: { "Content-Type": "application/json" }', 'headers: { "Content-Type": "application/json", "Authorization": "Bearer " + admin_passcode }')
        replace('action: "start", state: registryState,', 'action: "start", mode, ...(finalFour && sales_cutoff_seconds!==undefined ? {sales_cutoff_seconds}:{}), state: registryState,')
        replace('recovery_protocol: "il-fresh-page-v1"', 'recovery_protocol: registryState === "NC" ? "nc-fresh-search-v1" : "il-fresh-page-v1"')
        replace('registryState !== "IL" || recoveryUsed', '!["IL", "NC"].includes(registryState) || recoveryUsed')
        replace('onProgress?.("Illinois: verification stalled. Reopening the state page once and resuming this check.");',
                'onProgress?.(`${label}: the search stalled. Reopening the state page once and resuming this check.`);')
        replace('() => onProgress?.("Illinois: waiting to resume after verification recovery."), "IL", recoverySignal',
                '() => onProgress?.(`${label}: waiting to resume this check.`), registryState, recoverySignal')
        replace('const searchSignal = recoveryUsed ?', 'const searchSignal = (recoveryUsed || finalFour) ?')
        replace('if (!recoveryUsed) throw error;', 'if (!recoveryUsed && !finalFour) throw error;')
        # Trial-only, public-stage diagnostics. Never emit credentials, signed
        # continuations, source pages, or verification challenge material.
        replace('    async function api(fields, cleanup = false) {', '''    const trace = (stage, query = null, detail = {}) => {
      const publicQuery = query ? Object.fromEntries(Object.entries(query).filter(([key]) => ["state","operation","name","identifier","ein","orgName","orgID","city"].includes(key))) : null;
      onProgress?.(`${label}: ${stage}.`, {state:registryState,stage,query:publicQuery,...detail});
    };
    async function api(fields, cleanup = false) {
      if (!cleanup) trace("master request", null, {action:fields.action});''')
        replace('      let connection = await bridge("ping", null, null, null, null, signal);',
                '      trace("connector handshake started");\n      let connection = await bridge("ping", null, null, null, null, signal);')
        replace('      let acquired = connection;',
                '      trace("connector handshake returned",null,{ok:connection.ok===true,reason:connection.reason||""});\n      let acquired = connection;')
        replace('        acquired = await bridge("acquire", null, lookupId,',
                '        trace("connector queue entered");\n        acquired = await bridge("acquire", null, lookupId,', 2)
        replace('      // Start the signed continuation only after queue admission.',
                '      trace("connector queue returned",null,{ok:acquired.ok===true,reason:acquired.reason||""});\n      // Start the signed continuation only after queue admission.')
        replace('          if (!recoveryUsed && !finalFour) throw error;',
                '          trace("browser query exception",state.query,{name:error?.name||"Error",reason:error?.message||""});\n          if (!recoveryUsed && !finalFour) throw error;')
        replace('      const payload = await response.json();', '      const payload = await response.json();\n      if (!cleanup) trace("master response", null, {action:fields.action,http_status:response.status,phase:payload.phase,diagnostic:payload.result?.lab_diagnostic||null});')
        replace('        let completed;', '        let completed;\n        trace("browser query started", state.query);')
        replace('progress => onProgress?.(progress.reconnecting ? `${label}: reconnecting and resuming this check.',
                'progress => ["opening_page","waiting_for_form","preparing_query","query_sent"].includes(progress.ny_phase) ? trace("browser stage", state.query, {ny_phase:progress.ny_phase}) : Array.isArray(progress.ny_diagnostics) ? trace("browser stage", state.query, {ny_diagnostics:nyDiagnostics(progress.ny_diagnostics)}) : onProgress?.(progress.reconnecting ? `${label}: reconnecting and resuming this check.')
        replace('        state = completed.ok', '        trace("browser query returned", state.query, {ok:completed.ok,reason:completed.reason||"",...(registryState==="NY" ? {ny_diagnostics:nyDiagnostics(completed.ny_diagnostics)} : {}),...(["GA","MS"].includes(registryState) && Array.isArray(completed.trial_diagnostics) ? {trial_diagnostics:completed.trial_diagnostics} : {}),...(["NY_CONNECTOR_VERIFICATION_REJECTED","NY_CONNECTOR_SEARCH_VERIFICATION_REJECTED"].includes(completed.ny_failure_cause) ? {ny_failure_cause:completed.ny_failure_cause,ny_reset_cooldown:completed.ny_reset_cooldown===true} : {}),...(completed.nv_readiness ? {nv_readiness:completed.nv_readiness} : {}),...(completed.nc_submission ? {nc_submission:completed.nc_submission} : {}),...(["visible","hidden"].includes(completed.page_visibility) ? {page_visibility:completed.page_visibility} : {}),...(registryState === "IL" && Array.isArray(completed.diagnostics) ? {il_dom:completed.diagnostics.slice(0,32).map(({phase,event,elapsed_ms,visibility})=>({phase,event,elapsed_ms,visibility}))} : {}),...(registryState === "NV" && completed.evidence?.filings ? {nv_filings:{complete:completed.evidence.filings.complete===true,total:completed.evidence.filings.total??null,failure_code:completed.evidence.filings.failure_code||""}} : {})});\n        state = completed.ok')
        # An explicit source rejection is not an idle browser form. The
        # installed collector already exports these bounded public timings.
        # Keep its normal same-page attempt, but do not amplify a 429 by
        # requesting the master's fresh-page recovery as well.
        replace('        state = completed.ok', '''        if (registryState === "NC" && completed.ok === false &&
            completed.reason === "NY_CONNECTOR_NC_SEARCH_NOT_STARTED" &&
            Array.isArray(completed.nc_submission) && completed.nc_submission.some(entry =>
              Array.isArray(entry?.requests) && entry.requests.some(request =>
                request?.search_route === true && request.status === 429))) {
          completed = {...completed, reason:"NY_CONNECTOR_NC_RATE_LIMITED"};
        }
        state = completed.ok''')
    return insight_asset(name, text)


def insight_asset(name, text):
    """Trial-only Head Start/report integration; protected frontend stays frozen."""
    if not trial_identity() or name != 'index.html':
        return text
    text = text.replace('\r\n', '\n')
    replacements = [
        ('>Generate report</button>', '>Connect to Insight</button>'),
        ('    const STAGING_ACCESS_REQUIRED = true;', '    const STAGING_ACCESS_REQUIRED = true;\n    window.CCHeadStartConfig = () => ({apiBase:API_BASE,email:email.value.trim(),passcode:adminPasscode.value.trim(),unlocked:internalUnlocked,generateReport,renderResults});'),
        ('      unlockButton.textContent = internalUnlocked ? "Unlocked" : "Unlock";', '      unlockButton.textContent = internalUnlocked ? "Unlocked" : "Unlock";\n      window.CCHeadStart?.applyStates();'),
        ('      generateReportButton.disabled = false;', '      generateReportButton.disabled = false;\n      window.CCHeadStart?.refresh();'),
        ('const reportFields = ["organization_name",', 'const reportFields = ["success", "error", "organization_name",'),
        ('        const response = await fetch(`${API_BASE}/api/report`, {', '        const assessment = window.CCHeadStart?.forResults(results);\n        window.CCHeadStart?.save().catch(() => {});\n        const response = await fetch(`${API_BASE}/api/report`, {'),
        ('headers: { "Content-Type": "application/json" },\n          signal: controller.signal,', 'headers: { "Content-Type": "application/json", "Authorization": "Bearer " + adminPasscode.value.trim() },\n          signal: controller.signal,'),
        ('body: JSON.stringify({ results, email: email.value.trim(), admin_passcode: adminPasscode.value.trim() })', 'body: JSON.stringify({ results, email: email.value.trim(), admin_passcode: adminPasscode.value.trim(), head_start:assessment })'),
        ('link.download = `CharityClarity Aurora-', "link.download = `CharityClarity ${window.CCHeadStart?.forResults(results)?'Insight':'Aurora'}-"),
        ('generateReportButton.disabled = submitButton.disabled || !latestResults.length;', 'generateReportButton.disabled = !latestResults.length;'),
        ('      stateCheckboxes.forEach((box) => { box.checked = false; });\n\n      updatePasscodeVisibility();', '      if(!window.CCHeadStart?.hasAssessment())stateCheckboxes.forEach((box) => { box.checked = false; });\n\n      updatePasscodeVisibility();'),
        ('</head>', '  <link rel="stylesheet" href="/head-start/journey.css?v=20261008.1">\n</head>'),
        ('</body>', '  <script src="/head-start-bridge.js?v=2.0.1"></script>\n</body>'),
    ]
    for old, new in replacements:
        if text.count(old) != 1:
            raise RuntimeError('Insight frontend template mismatch: '+old[:100]+'; matches='+str(text.count(old)))
        text = text.replace(old, new, 1)
    return text


def lab_asset(path):
    path = unquote(urlparse(path).path)
    if path in ('/head-start', '/head-start/'):
        path = '/head-start/index.html'
    if path.startswith('/head-start/') or path == '/head-start-bridge.js':
        root = (ROOT/'deployment/insight').resolve()
        file = (root/path.lstrip('/')).resolve()
        if (not file.is_relative_to(root) or file.suffix.lower() not in {'.html','.js','.css','.png','.svg','.ttf'} or not file.is_file()):
            return None
        return file.read_bytes(), mimetypes.guess_type(file)[0] or 'application/octet-stream'
    if path == '/connector/final-four-validation.html' and trial_identity():
        return (ROOT/'deployment/final-four-validation.html').read_bytes(), 'text/html'
    if path in ('/', '/registry-snapshot', '/registry-snapshot/', '/instant-compliance-snapshot', '/instant-compliance-snapshot/'):
        path = '/index.html'
    root = (ROOT / 'web-staging').resolve()
    file = (root / path.lstrip('/')).resolve()
    if not file.is_relative_to(root) or file.suffix.lower() not in {'.html', '.js', '.css', '.png', '.ico', '.svg', '.jpg'}:
        return None
    if not file.is_file():
        return None
    data = file.read_bytes()
    if file.suffix.lower() in {'.html', '.js', '.css'}:
        text = data.decode('utf-8')
        text = final_four_asset(file.name, text)
        for origin in ('https://instant-compliance-snapshot-api-staging-8dnk.onrender.com',
                       'https://instant-compliance-snapshot-api-staging.onrender.com',
                       'https://staging.compliance-express.com'):
            text = text.replace(origin, LAB_ORIGIN)
        if file.name == 'index.html':
            text = text.replace('<title>', '<title>Performance Lab — ', 1)
            text = text.replace('<body', '<body data-performance-lab="true"', 1)
            ny_note = ('New York uses this lab\'s isolated browser connector.' if trial_identity() else
                       'New York uses an isolated backend browser.' if os.environ.get('CE_LAB_NY_BROWSER') == '1' else
                       'New York browser validation is not enabled.')
            marker = '<div style="padding:10px;background:#fff3cd;color:#533f03;text-align:center">Isolated performance lab. Capacity is under evaluation. '+ny_note+'</div>'
            import re
            text = re.sub(r'(<body\b[^>]*>)', lambda m: m.group(1) + marker, text, count=1)
        data = text.encode('utf-8')
    return data, mimetypes.guess_type(file)[0] or 'application/octet-stream'


def build_handler(master, key, capacity=None, durable=None):
    lock = threading.Lock()
    telemetry = {'started_epoch': time.time(), 'active_requests': 0, 'peak_requests': 0, 'completed_requests': 0}

    class LabHandler(master.RegistrySnapshotHandler):
        def _send_json(self, status_code, payload, extra_headers=None):
            from deployment.lab_capacity import REQUEST_TIMING
            timing = REQUEST_TIMING.get()
            headers = dict(extra_headers or {})
            if timing is not None:
                queue = timing.get('queue_seconds', 0)
                elapsed = time.monotonic() - timing['started']
                headers['Server-Timing'] = f'queue;dur={queue*1000:.2f}, execution;dur={max(0, elapsed-queue)*1000:.2f}'
                headers['X-CC-Lab-Version'] = master.APP_VERSION
            return super()._send_json(status_code, payload, headers)

        def authorized(self):
            if valid_authorization(self.headers.get('Authorization', ''), key):
                return True
            if getattr(self, 'command', '') == 'POST':
                # Closing with unread request bytes can reset the connection
                # before the caller receives the denial. Drain only a small,
                # bounded body, with a separate one-second rejection deadline.
                self.close_connection = True
                previous_timeout = self.connection.gettimeout()
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if 0 < length <= 32768:
                        deadline = time.monotonic()+1
                        while length and (remaining := deadline-time.monotonic()) > 0:
                            self.connection.settimeout(remaining)
                            chunk = self.rfile.read1(length)
                            if not chunk: break
                            length -= len(chunk)
                except (OSError, ValueError):
                    pass
                finally:
                    self.connection.settimeout(previous_timeout)
            self._send_json(401, {'error': 'Private performance lab access required.'},
                            {'WWW-Authenticate': 'Basic realm="CharityClarity performance lab"', 'Cache-Control': 'no-store'})
            return False

        def _send_healthz(self, include_body=True):
            data = {'ok': True, 'app_version': master.APP_VERSION, 'environment': 'performance-lab',
                    'supported_states': master.SUPPORTED_STATES, 'private_access': True,
                    'ny_browser_validation_enabled': os.environ.get('CE_LAB_NY_BROWSER') == '1', 'shared_helpers_enabled': False,
                    'durable_workflows_enabled': durable is not None,
                    'sales_queue_policy': getattr(durable, 'sales_policy', None),
                    'downloadable_data': {s: master.downloadable_data_info(s) for s in ('KS','KY','LA','NH','OR')}}
            if os.environ.get('CE_FINAL_FOUR_TRIAL') == '1':
                data['trial_access_active'] = trial_identity() is not None
                data['trial_access_expired'] = trial_access_expired()
            if trial_identity():
                from charity_clarity_report import INSIGHT_VERSION
                data['trial_release'] = TRIAL_RELEASE_LABEL
                data['insight_report_version'] = INSIGHT_VERSION
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            if include_body: self.wfile.write(body)

        def _get(self, include_body):
            if self.path in ('/health', '/healthz'):
                return self._send_healthz(include_body)
            # This empty test form contains no credentials or results. Its API
            # calls still require the private trial key, including the master
            # passcode checks. No customer/backend data becomes public.
            if trial_identity() and urlparse(self.path).path in (
                    '/connector/final-four-validation.html','/ny-connector.js','/optimized-workflows.js'):
                body,kind=lab_asset(self.path)
                self.send_response(200);self.send_header('Content-Type',kind)
                self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
                self.end_headers()
                if include_body:self.wfile.write(body)
                return
            if not self.authorized(): return
            if self.path == '/api/lab/trial-export' and trial_identity() and durable is not None:
                # Authenticated evidence export before retiring this disposable
                # database. The approved pool never exposes this endpoint.
                with durable.transaction() as (connection, _):
                    evidence = {}
                    for table, limit in (('cc_lab_settings', 1), ('cc_lab_workflows', 1000), ('cc_lab_jobs', 40000)):
                        count = connection.execute('SELECT count(*) AS n FROM ' + table).fetchone()['n']
                        if count > limit:
                            return self._send_json(413, {'error': 'Trial export needs a paginated archival pass'})
                        evidence[table] = connection.execute('SELECT * FROM ' + table).fetchall()
                data = json.loads(json.dumps(evidence, default=str))
                return self._send_json(200, {'app_version': master.APP_VERSION, 'evidence': data}, {'Cache-Control':'no-store'})
            if self.path == '/api/lab/metrics':
                with lock: data = dict(telemetry)
                data['app_version'] = master.APP_VERSION
                data['instance'] = os.environ.get('RENDER_INSTANCE_ID', 'local')
                if capacity is not None: data['capacity'] = capacity.snapshot()
                if durable is not None: data['durable_queue'] = durable.metrics()
                try:
                    import resource
                    data['process_peak_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                except ImportError: pass
                return self._send_json(200, data, {'Cache-Control':'no-store'})
            if self.path.startswith('/api/lab/workflows/') and durable is not None:
                from deployment.durable_queue import NotFound
                ident = self.path.removeprefix('/api/lab/workflows/')
                try: data = durable.status('private-performance-lab', ident)
                except NotFound: return self._send_json(404, {'error': 'Workflow not found'})
                except Exception: return self._send_json(503, {'error': 'Saved progress is temporarily unavailable'})
                return self._send_json(200, data, {'Cache-Control': 'no-store'})
            if durable is not None and self.path.startswith('/evidence/'):
                return self._send_json(409, {'error': 'Evidence execution is not enabled in the durable queue experiment'})
            asset = lab_asset(self.path)
            if asset:
                body, kind = asset
                self.send_response(200)
                self.send_header('Content-Type', kind)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                if include_body: self.wfile.write(body)
                return
            # Evidence can trigger work in the master, so it stays private too.
            return super().do_GET() if include_body else super().do_HEAD()

        def do_GET(self): return self._get(True)
        def do_HEAD(self): return self._get(False)

        def do_POST(self):
            if not self.authorized(): return
            if trial_access_expired() and self.path in ('/api/workflow', '/api/discover-names',
                    '/api/check', '/api/ny-connector', '/api/final-four-connector'):
                return self._send_json(503, {'code': 'PERFORMANCE_LAB_EXPIRED',
                    'error': 'The isolated Performance Lab access window has expired. No registry search was run.'})
            if trial_identity():
                if self.path == '/api/workflow' and durable is not None:
                    from deployment.staging_workflows import handle
                    return handle(master, self, trial_queue=durable)
                if self.path in ('/api/final-four-connector', '/api/ny-connector', '/api/identity-review', '/api/report', '/api/head-start'):
                    return super().do_POST()
                if self.path == '/api/discover-names':
                    # The approved master already bounds concurrent discovery;
                    # its implementation and source set are unchanged.
                    return super().do_POST()
            if durable is not None:
                from deployment.durable_queue import normalize_submission, Conflict, QueueFull, NotFound
                try:
                    if self.path != '/api/lab/workflows':
                        # Consume bounded ignored bodies before closing a rejected
                        # or cancellation request. Unread bytes can reset the TCP
                        # connection before the client receives our JSON response.
                        length = int(self.headers.get('Content-Length', '0'))
                        if not 0 <= length <= 32768: raise ValueError('Invalid request size')
                        self.rfile.read(length)
                    if self.path == '/api/lab/workflows':
                        length = int(self.headers.get('Content-Length', '0'))
                        if not 0 < length <= 32768: raise ValueError('Workflow input must be 1–32768 bytes')
                        payload = normalize_submission(json.loads(self.rfile.read(length)), master.SUPPORTED_STATES)
                        ident, created = durable.submit('private-performance-lab', self.headers.get('Idempotency-Key'),
                            payload, master.APP_VERSION, (*master.IDENTITY_STATES, 'IRS'))
                        return self._send_json(202 if created else 200,
                            {'id': ident, 'created': created, 'progress_url': '/api/lab/workflows/'+ident}, {'Cache-Control': 'no-store'})
                    if self.path.startswith('/api/lab/workflows/') and self.path.endswith('/cancel'):
                        ident = self.path.removeprefix('/api/lab/workflows/').removesuffix('/cancel')
                        durable.cancel('private-performance-lab', ident)
                        return self._send_json(202, {'id': ident, 'cancel_requested': True})
                    if self.path.startswith('/api/lab/workflows/') and self.path.endswith('/release-external'):
                        ident = self.path.removeprefix('/api/lab/workflows/').removesuffix('/release-external')
                        durable.release_external_slots('private-performance-lab', ident)
                        return self._send_json(200, {'id': ident, 'external_slots_released': True})
                    if self.path in ('/api/check', '/api/discover-names', '/api/ny-connector'):
                        return self._send_json(409, {'error': 'Use the durable lab workflow endpoint; direct execution is disabled'})
                    return self._send_json(404, {'error': 'Not found'})
                except Conflict as exc: return self._send_json(409, {'error': str(exc)})
                except QueueFull as exc: return self._send_json(429, {'error': str(exc)})
                except NotFound: return self._send_json(404, {'error': 'Workflow not found'})
                except (ValueError, TypeError, UnicodeError): return self._send_json(400, {'error': 'Invalid workflow input or idempotency key'})
                except Exception: return self._send_json(503, {'error': 'Workflow persistence unavailable; retry with the same idempotency key'})
            if self.path == '/api/ny-connector':
                return self._send_json(503, {'error':'An isolated New York browser collector has not been configured in this lab.'})
            from deployment.lab_capacity import REQUEST_GROUP, REQUEST_TIMING
            group = 'lab:other'
            if self.path in ('/api/check', '/api/discover-names'):
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 131072: raise ValueError('Invalid request size')
                    raw = self.rfile.read(length)
                    payload = json.loads(raw)
                    if not isinstance(payload, dict): raise ValueError('Object required')
                    import re
                    ein = re.sub(r'\D', '', str(payload.get('ein', '')))
                    group = 'lab:' + ein if len(ein) == 9 else 'lab:invalid'
                    self.rfile = io.BytesIO(raw)
                except (ValueError, TypeError):
                    return self._send_json(400, {'error': 'Invalid lab request body.'})
            group_token = REQUEST_GROUP.set(group)
            timing_token = REQUEST_TIMING.set({'started': time.monotonic()})
            with lock:
                telemetry['active_requests'] += 1
                telemetry['peak_requests'] = max(telemetry['peak_requests'], telemetry['active_requests'])
            try:
                return super().do_POST()
            finally:
                REQUEST_TIMING.reset(timing_token)
                REQUEST_GROUP.reset(group_token)
                with lock:
                    telemetry['active_requests'] -= 1
                    telemetry['completed_requests'] += 1
    return LabHandler


def main():
    validate_environment(os.environ)
    install_http_egress_guard()
    import registry_snapshot_server as master
    # Private lab credential, distinct from the existing staging access code.
    master.ADMIN_PASSCODE = os.environ['CE_LAB_ACCESS_KEY']
    capacity = None
    durable = None
    supervisor = None
    supervisor_thread = None
    if os.environ.get('CE_LAB_DURABLE_QUEUE') == '1':
        from deployment.durable_queue import Queue
        durable = Queue(os.environ['CE_LAB_DATABASE_URL'], ny_enabled=os.environ.get('CE_LAB_NY_BROWSER') == '1')
        limits = {s: 4 for s in master.SUPPORTED_STATES}
        limits.update(ME=1, AR=1, FL=3, IRS=4, NY=2)
        durable.initialize(master.APP_VERSION, limits,
                           workflow_limit=int(os.environ.get('CE_LAB_WORKFLOW_LIMIT', '15')))
        if os.environ.get('CE_LAB_QUEUE_WORKER') == '1':
            from deployment.queue_worker import Supervisor
            supervisor = Supervisor(durable, master.APP_VERSION, int(os.environ.get('CE_LAB_WORKER_SLOTS', '8')))
            supervisor_thread = threading.Thread(target=supervisor.run, daemon=True, name='lab-worker-supervisor')
            supervisor_thread.start()
    elif os.environ.get('CE_LAB_FAIR_CAPACITY') == '1':
        from deployment.lab_capacity import install
        capacity = install(master, int(os.environ['CE_MAX_BROWSER_LOOKUPS']))
    master.RegistrySnapshotHandler = build_handler(master, master.ADMIN_PASSCODE, capacity, durable)
    if durable is None:
        master.main()
        return
    import signal
    from http.server import ThreadingHTTPServer
    ThreadingHTTPServer.request_queue_size = 128
    with ThreadingHTTPServer((master.HOST, master.PORT), master.RegistrySnapshotHandler) as server:
        def stop(*args):
            if supervisor: supervisor.stop()
            threading.Thread(target=server.shutdown, daemon=True).start()
        for sig in (signal.SIGINT, signal.SIGTERM): signal.signal(sig, stop)
        try: server.serve_forever()
        finally:
            if supervisor:
                supervisor.stop()
                supervisor_thread.join(25)
            durable.close()


if __name__ == '__main__':
    main()
