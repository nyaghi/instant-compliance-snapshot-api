import unittest
from pathlib import Path

from playwright.async_api import async_playwright
from testing.test_nv_responsive_snapshot import HTML


class NevadaGeometryRecovery(unittest.IsolatedAsyncioTestCase):
    async def test_same_record_layout_recaptures_but_a_different_record_does_not(self):
        connector = Path(__file__).resolve().parents[1] / "deployment/staging_connector"
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            for fault in ("geometry", "identity", "loader", "loader-identity", "none", "short", "short-identity"):
                with self.subTest(fault=fault):
                    narrow = fault.startswith("short")
                    page = await browser.new_page(viewport={"width": 640 if narrow else 1680,
                                                            "height": 140 if narrow else 927})
                    await page.route("**/*", lambda route: route.fulfill(content_type="text/html", body=HTML))
                    await page.goto("https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen?screen=Manage-Business&id=local")
                    cdp = await page.context.new_cdp_session(page)
                    await page.expose_function("localCDP", lambda method, params: cdp.send(method, params))
                    await page.evaluate("""fault => {
                      window.localFault=fault;window.shots=0;
                      window.wfAwait=(_,__,call)=>call();window.wfReturn=(_,__,value)=>value;
                      window.wfEvent=()=>{};window.diagnostic=()=>{};
                      window.P={TRIAL_ORIGIN:'local',sameQuery:(a,b)=>JSON.stringify(a)===JSON.stringify(b)};
                      window.owned=new Set([1]);window.isActive=()=>true;window.registryOrigin=()=>location.origin;
                      window.chrome={runtime:{id:'local',onMessage:{addListener:fn=>window.localListener=fn}},
                        tabs:{get:async()=>({url:location.href}),sendMessage:async(_,m)=>{
                          const reply=await new Promise(resolve=>localListener(m,{id:'local'},resolve));
                          if(m.action==='registry-snapshot-metadata'&&localFault==='short-identity'&&innerWidth>=1024)
                            reply.source_binding+='changed';
                          if(m.action==='registry-snapshot-metadata'&&shots===1&&localFault!=='none'&&!localFault.startsWith('short')){
                            reply.source_view_shape=[...reply.source_view_shape];reply.source_view_shape[0]+=1;
                            if(localFault.includes('identity'))reply.source_binding+='changed';
                            if(localFault.startsWith('loader')&&!window.loaderSeen){reply.source_loading_visible=true;window.loaderSeen=true;}
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
                      return {first:!!first,retry,second:!!second,shots,ready:metadata.source_fields_visible,
                              bound:!!metadata.source_binding,detail:metadata.source_detail,width:innerWidth,height:innerHeight};
                    }""")
                    if narrow:
                        self.assertFalse(result["detail"], result)
                        self.assertTrue(result["bound"], result)
                        self.assertEqual(result["first"], fault == "short", result)
                        self.assertEqual(result["shots"], 1 if fault == "short" else 0, result)
                        self.assertEqual((result["width"], result["height"]), (640, 140))
                        await page.close()
                        continue
                    self.assertTrue(result["ready"])
                    self.assertEqual(result["first"], fault == "none", result)
                    self.assertEqual(result["retry"], fault in ("geometry", "loader"), result)
                    self.assertEqual(result["second"], fault in ("geometry", "loader"), result)
                    self.assertEqual(result["shots"], 2 if fault in ("geometry", "loader") else 1, result)
                    await page.close()
            await browser.close()
