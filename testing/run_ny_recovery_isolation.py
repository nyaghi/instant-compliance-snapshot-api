"""Exercise the actual cleanup module in a disposable Chromium profile.

All HTTP traffic is routed to synthetic .test sites; no user profile or live
registry is accessed. The fixture extension alone has additional host grants.
"""
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

WORK = Path(__file__).resolve().parents[1]
TARGET = 'https://charities-search.example.test'
SIBLING = 'https://other.example.test'
UNRELATED = 'https://unrelated.test'
report = {'checks': {}, 'live_registry_contacted': False, 'user_profile_used': False}

def run():
    with tempfile.TemporaryDirectory(prefix='cc-ny-isolation-') as tmp:
        root = Path(tmp).resolve()
        assert root.parent == Path(tempfile.gettempdir()).resolve()
        extension = root / 'extension'; extension.mkdir()
        source = (WORK / 'browser-connector/recovery.js').read_text().replace('charities-search.ag.ny.gov', 'charities-search.example.test').replace('https://ny.gov', 'https://example.test')
        (extension / 'recovery.js').write_text(source)
        (extension / 'worker.js').write_text('/* Broad fixture helper seeds and observes controls only. */')
        (extension / 'manifest.json').write_text(json.dumps({'manifest_version': 3, 'name': 'NY cleanup isolation fixture', 'version': '1.0', 'permissions': ['browsingData', 'cookies', 'storage'], 'host_permissions': [TARGET+'/*', SIBLING+'/*', UNRELATED+'/*', 'https://example.test/*', 'https://elsewhere.test/*'], 'background': {'service_worker': 'worker.js'}}))
        narrow = root / 'narrow'; narrow.mkdir()
        (narrow / 'recovery.js').write_text(source)
        (narrow / 'cleanup-worker.js').write_text('importScripts("recovery.js");')
        (narrow / 'manifest.json').write_text(json.dumps({'manifest_version': 3, 'name': 'Actual narrow recovery scope', 'version': '1.0', 'permissions': ['browsingData', 'cookies', 'storage'], 'host_permissions': [TARGET+'/*'], 'background': {'service_worker': 'cleanup-worker.js'}}))
        with c.checker.sync_playwright() as p:
            context = p.chromium.launch_persistent_context(str(root/'profile'), headless=True, channel='chromium', args=[f'--disable-extensions-except={extension},{narrow}', f'--load-extension={extension},{narrow}'])
            def route_request(route):
                if route.request.url.startswith((TARGET,SIBLING,UNRELATED)):
                    route.fulfill(content_type='text/html', body='<title>Isolated storage control</title>')
                elif route.request.url.startswith('chrome-extension:'):
                    route.continue_()
                else:
                    route.abort()
            context.route('**/*', route_request)
            while len(context.service_workers) < 2: context.wait_for_event('serviceworker')
            worker = next(w for w in context.service_workers if w.url.endswith('/worker.js'))
            cleanup = next(w for w in context.service_workers if w.url.endswith('/cleanup-worker.js'))
            report['checks']['cleanup_has_only_exact_host_permission'] = cleanup.evaluate('chrome.runtime.getManifest().host_permissions') == [TARGET+'/*']
            pages = {origin: context.new_page() for origin in [TARGET, SIBLING, UNRELATED]}
            for origin, page in pages.items():
                page.goto(origin)
                page.evaluate("""async () => {localStorage.setItem('control','kept');await new Promise((resolve,reject)=>{const r=indexedDB.open('control',1);r.onupgradeneeded=()=>r.result.createObjectStore('data');r.onsuccess=()=>{r.result.close();resolve();};r.onerror=reject;});const cache=await caches.open('control');await cache.put('/saved',new Response('kept'));}""")
            metadata = worker.evaluate("""async target => {const tabs=await chrome.tabs.query({url:target+'/*'});const tab=tabs[0];const stores=await chrome.cookies.getAllCookieStores();const store=stores.find(s=>s.tabIds.includes(tab.id));return {tabId:tab.id,storeId:store.id,...await chrome.cookies.getPartitionKey({tabId:tab.id,frameId:0})};}""", TARGET)
            assert metadata['partitionKey']['topLevelSite']
            worker.evaluate("""async ({target,sibling,unrelated,partitionKey}) => {
              const set=(url,name,extra={})=>chrome.cookies.set({url,name,value:'fixture-control',secure:true,path:'/',...extra});
              await set(target,'collision',{domain:'.example.test'});
              await set(target,'collision'); await set(target,'own');
              await set(target,'own',{path:'/nested'});
              await set(target,'partitionOwn',{partitionKey});
              await set(target,'otherPartition',{partitionKey:{topLevelSite:'https://elsewhere.test'}});
              await set(target,'crossSitePartition',{partitionKey:{...partitionKey,hasCrossSiteAncestor:true}});
              await set(target,'shared',{domain:'.example.test'});
              await set(target,'sameDomain',{domain:'.charities-search.example.test'});
              await set(sibling,'sibling');await set(unrelated,'unrelated');
              globalThis.beforeCookies=await chrome.cookies.getAll({partitionKey:{}});
            }""", {'target':TARGET, 'sibling':SIBLING, 'unrelated':UNRELATED, 'partitionKey':metadata['partitionKey']})
            blocked = cleanup.evaluate("""async id => {try {await CCNYRecovery.clearForTab(id,[],async()=>{});return 'unexpected-success';}catch(e){return e.message;}}""", metadata['tabId'])
            report['checks']['user_owned_ny_page_blocks_cleanup'] = blocked == 'NY_CONNECTOR_RECOVERY_PAGE_OPEN'
            report['checks']['blocked_cleanup_preserves_storage'] = pages[TARGET].evaluate("localStorage.getItem('control')") == 'kept'
            # Introduce an overlapping parent cookie between enumeration and the
            # first exact expired overwrite. URL-based deletion is not used.
            cleanup.evaluate("""target => {const original=chrome.cookies.set.bind(chrome.cookies);globalThis.savedSet=original;let raced=false;chrome.cookies.set=async details=>{if(details.expirationDate===1&&!raced){raced=true;await original({url:target,name:details.name,value:'concurrent-parent',domain:'.example.test',path:details.path,secure:true});}return original(details);};}""", TARGET)
            outcome = cleanup.evaluate("""async ({tabId}) => CCNYRecovery.clearForTab(tabId,[tabId],()=>chrome.tabs.remove(tabId))""", metadata)
            report['scoped_cookie_expirations'] = outcome['scopedCookiesExpired']
            after = worker.evaluate("""async ({target,partitionKey})=>{
              const all=await chrome.cookies.getAll({partitionKey:{}}),host=new URL(target).hostname;
              const key=c=>JSON.stringify([c.name,c.domain,c.path,c.storeId,c.partitionKey||null]);
              const targetCookie=c=>c.hostOnly&&c.domain===host&&(!c.partitionKey||JSON.stringify(c.partitionKey)===JSON.stringify(partitionKey));
              const controls=beforeCookies.filter(c=>!targetCookie(c)&&c.name!=='collision');
              return {targetGone:!all.some(targetCookie),controlsKept:controls.every(c=>all.some(a=>key(a)===key(c)&&a.value===c.value)),parentRaceKept:all.some(c=>!c.hostOnly&&c.domain==='.example.test'&&c.value==='concurrent-parent'),crossSitePartitionKept:all.some(c=>c.name==='crossSitePartition'),sameDomainKept:all.some(c=>c.name==='sameDomain'),otherPartitionKept:all.some(c=>c.name==='otherPartition'),parentCollisionKept:all.some(c=>c.name==='collision'&&!c.hostOnly)};
            }""", {'target':TARGET,'partitionKey':metadata['partitionKey']})
            report['checks'].update(after)
            fresh = context.new_page(); fresh.goto(TARGET)
            read = """async()=>({local:!!localStorage.getItem('control'),indexed:(await indexedDB.databases()).some(d=>d.name==='control'),cache:(await caches.keys()).includes('control')})"""
            report['checks']['target_storage_removed'] = not any(fresh.evaluate(read).values())
            report['checks']['sibling_storage_preserved'] = all(pages[SIBLING].evaluate(read).values())
            report['checks']['unrelated_storage_preserved'] = all(pages[UNRELATED].evaluate(read).values())
            # Other-store cookies are excluded before any write by the module.
            # Incognito is disabled in the actual manifest, not silently covered.
            report['checks']['four_exact_host_cookie_identities_expired'] = outcome['scopedCookiesExpired'] == 4
            context.close()
    report['passed'] = all(report['checks'].values())
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1

if __name__ == '__main__':
    sys.exit(run())
