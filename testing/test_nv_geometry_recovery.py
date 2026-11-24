import unittest
import html
import json
from pathlib import Path

from playwright.async_api import async_playwright
from testing.test_nv_responsive_snapshot import HTML


class NevadaGeometryRecovery(unittest.IsolatedAsyncioTestCase):
    async def test_same_record_layout_recaptures_but_a_different_record_does_not(self):
        connector = Path(__file__).resolve().parents[1] / "deployment/staging_connector"
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            faults = ("veil-geometry", "veil-loader", "veil-identity", "veil-document", "none")
            roster = json.loads((connector.parents[1] / "testing/fixtures/gate55/LOCAL-70.json").read_text())
            self.assertEqual(len({org["ein"] for org in roster}), 70)
            cases = [(org, faults[index % len(faults)]) for index, org in enumerate(roster)]
            cases.extend((roster[0], fault) for fault in ("geometry", "identity", "loader", "loader-identity"))
            for org, fault in cases:
                with self.subTest(fault=fault, organization=org["name"]):
                    page = await browser.new_page(viewport={"width": 1680, "height": 927})
                    fixture = HTML.replace("LOCAL ORGANIZATION", html.escape(org["name"]))
                    await page.route("**/*", lambda route: route.fulfill(content_type="text/html", body=fixture))
                    await page.goto("https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen?screen=Manage-Business&id=local")
                    cdp = await page.context.new_cdp_session(page)
                    await page.expose_function("localCDP", lambda method, params: cdp.send(method, params))
                    await page.evaluate("""fault => {
                      window.localFault=fault;window.shots=0;
                      if(fault.startsWith('veil-'))window.CCOwnedSourcePixels={
                        nvDetailVeiled:async()=>shots===1&&!window.veilSeen&&(window.veilSeen=true)
                      };
                      window.wfAwait=(_,__,call)=>call();window.wfReturn=(_,__,value)=>value;
                      window.wfEvent=()=>{};window.diagnostic=()=>{};
                      window.P={TRIAL_ORIGIN:'local',sameQuery:(a,b)=>JSON.stringify(a)===JSON.stringify(b)};
                      window.owned=new Set([1]);window.isActive=()=>true;window.registryOrigin=()=>location.origin;
                      window.chrome={runtime:{id:'local',onMessage:{addListener:fn=>window.localListener=fn}},
                        tabs:{get:async()=>({url:location.href}),sendMessage:async(_,m)=>{
                          const reply=await new Promise(resolve=>localListener(m,{id:'local'},resolve));
                          if(m.action==='registry-snapshot-metadata'&&shots===1&&localFault!=='none'){
                            reply.source_view_shape=[...reply.source_view_shape];reply.source_view_shape[0]+=1;
                            if(localFault.includes('identity'))reply.source_binding+='changed';
                            if(localFault.includes('document'))reply.document_id+='changed';
                            if(localFault.includes('loader')&&!window.loaderSeen){reply.source_loading_visible=true;window.loaderSeen=true;}
                          }
                          return reply;
                        }},
                        debugger:{attach:async()=>{},sendCommand:async(t,m,p)=>{
                          if(m==='Page.captureScreenshot')shots++;
                          return localCDP(m,p||{});
                        },detach:async()=>{}}};
                    }""", fault)
                    for source in ("registry-content.js", "state-snapshot-worker.js"):
                        await page.add_script_tag(content=(connector / source).read_text(encoding="utf-8"))
                    result = await page.evaluate("""async()=>{
                      const query={state:'NV',operation:'detail',identifier:'NV19951158753'};
                      const job={tab:1,generation:1,pending:'local',command:{id:'local',query},registryState:'NV',
                        activeExpiresAt:Date.now()+30000};
                      const metadata=await chrome.tabs.sendMessage(1,{action:'registry-snapshot-metadata',query});
                      const prepared={command_id:'local',query,document_id:metadata.document_id,observed_at:Date.now(),metadata};
                      const first=await captureStateSnapshot(job,query,'local',prepared);
                      const retry=job.nvGeometryRetryCommand==='local';
                      const second=retry?await captureStateSnapshot(job,query,'local',prepared,true):null;
                      return {first:!!first,retry,second:!!second,shots,ready:metadata.source_fields_visible};
                    }""")
                    self.assertTrue(result["ready"])
                    self.assertEqual(result["first"], fault == "none", result)
                    recovered = fault in ("geometry", "loader", "veil-geometry", "veil-loader")
                    self.assertEqual(result["retry"], recovered, result)
                    self.assertEqual(result["second"], recovered, result)
                    self.assertEqual(result["shots"], 2 if recovered else 1, result)
                    await page.close()
            await browser.close()
