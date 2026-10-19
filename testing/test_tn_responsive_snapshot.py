"""Real local Chromium/CDP captures of a source-backed responsive fixture.
This is not a live TN search: layout models the observed min-width800 column.
"""
import asyncio,base64,io,json,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.async_api import async_playwright
from deployment import state_snapshots as s
from pypdf import PdfReader
COHORT=json.loads((ROOT/'testing/fixtures/oct19-cohort.json').read_text())[:30]
HTML='''<style>body{margin:0;font:18px Arial;background:#eee}#KendoWindowLevel1{position:fixed;left:8px;top:20px;width:calc(100vw - 16px);height:210px;overflow:auto;background:white;box-sizing:border-box;border:1px solid #333}h2{font:24px Georgia;margin:10px}h4{font:18px Arial;margin:8px}.purpose{height:400px}table{width:100%;border-collapse:collapse}th,td{height:35px;border:1px solid #ddd;text-align:left} @media(max-width:799px){th:first-child,td:first-child{display:none}}</style>
<p>LOCAL RESPONSIVE SOURCE FIXTURE — NOT LIVE STATE EVIDENCE</p>
<div id="KendoWindowLevel1"><h2 id="org"></h2><p>85 HERRICK STREET BEVERLY MA 01915</p><h4>Status: Expired</h4><h4>CO Number: CO42115</h4><h4>Registration Date: 12/07/2021</h4><h4>Expiration Date: 08/28/2023</h4><div class="purpose">Local fixture purpose section</div><div id="DetailsTabStrip-1"><a>Financials (3)</a><table role="grid"><thead><tr><th data-field="FinancialPeriod">Fiscal Year End</th><th>Total Revenue</th></tr></thead><tbody><tr><td>09/30/2018</td><td>LOCAL OLD</td></tr><tr><td>09/30/2020</td><td>LOCAL LATEST</td></tr><tr><td>09/30/2019</td><td>LOCAL OTHER</td></tr></tbody></table></div><div style="height:230px">Local fixture tail</div></div>'''
class Responsive(unittest.IsolatedAsyncioTestCase):
 async def test_thirty_actual_local_browser_worker_captures_keep_native_source_pixels_and_restore(self):
  content=(ROOT/'browser-connector/registry-content.js').read_text(encoding='utf-8');worker=(ROOT/'browser-connector/state-snapshot-worker.js').read_text(encoding='utf-8')
  durations=[];http=[];page_count=0;commands=[]
  tempdir=tempfile.TemporaryDirectory();self.addCleanup(tempdir.cleanup);temp=tempdir.name
  async def fulfill(route):
   http.append(route.request.url);await route.fulfill(content_type='text/html',body=HTML)
  async with async_playwright() as pw:
   browsers={width:await pw.chromium.launch(headless=True,args=[f'--window-size={width},{height}']) for width,height in [(360,280),(640,440),(1024,900)]}
   try:
    store=s.SQLiteStore(Path(temp)/'evidence.sqlite')
    for i,org in enumerate(COHORT):
     width,height=[(360,280),(640,440),(1024,900)][i%3];context=await browsers[width].new_context(no_viewport=True);page=await context.new_page()
     await page.route('**/*',fulfill);await page.goto('https://tncab.tnsos.gov/portal/registered-charities-search');await page.locator('#org').evaluate('(el,name)=>el.textContent="LOCAL FIXTURE: "+name',org['name'])
     session=await context.new_cdp_session(page)
     async def send(method,params):
      self.assertIn(method,{'Page.getLayoutMetrics','Page.captureScreenshot','Emulation.setDeviceMetricsOverride','Emulation.clearDeviceMetricsOverride'});commands.append(method);return await session.send(method,params)
     await page.expose_function('localCDP',send);await page.expose_function('localDetach',session.detach)
     await page.evaluate('''() => {window.chrome={runtime:{id:'local',onMessage:{addListener:fn=>window.localSnapshotListener=fn}},tabs:{get:async()=>({url:location.href}),sendMessage:async(id,m)=>{const result=await new Promise(resolve=>window.localSnapshotListener(m,{id:'local'},resolve));if(m.action==='registry-snapshot-view'&&m.view!=='restore')window.localView=m.view;return result;}},debugger:{attach:async()=>{},sendCommand:async(target,method,params)=>{if(method==='Page.captureScreenshot'){const d=document.querySelector('#KendoWindowLevel1'),bounds=d.getBoundingClientRect(),inside=el=>{const r=el.getBoundingClientRect();return r.width>0&&r.top>=bounds.top&&r.bottom<=Math.min(innerHeight,bounds.top+d.clientHeight);};window.localChecks.push({view:window.localView,sourceWidth:innerWidth,standing:[...d.querySelectorAll('h4')].every(inside),header:inside([...d.querySelectorAll('th')].find(el=>el.textContent==='Fiscal Year End')),latest:inside([...d.querySelectorAll('td')].find(el=>el.textContent==='09/30/2020'))});}return window.localCDP(method,params||{});},detach:async()=>window.localDetach()}};window.localChecks=[];window.P={TRIAL_ORIGIN:'https://fixture.test',sameQuery:(a,b)=>JSON.stringify(a)===JSON.stringify(b)};window.isActive=()=>true;window.owned=new Set([1]);window.registryOrigin=()=>location.origin;document.querySelector('#KendoWindowLevel1').scrollTop=70;}''')
     original=await page.evaluate('({width:innerWidth,height:innerHeight})');await page.add_script_tag(content=content);await page.add_script_tag(content=worker)
     started=time.monotonic();out=await asyncio.wait_for(page.evaluate('''async()=>{const query={state:'TN',operation:'detail',identifier:'CO42115'},job={tab:1,generation:1,pending:'local-command',command:{id:'local-command',query},registryState:'TN',activeExpiresAt:Date.now()+30000};return captureStateSnapshot(job,query,'local-command');}'''),timeout=10);durations.append((time.monotonic()-started)*1000)
     self.assertIsNotNone(out,(org['name'],width,durations[-1]));self.assertLess(out['capture_ms'],1500)
     checks=await page.evaluate('({checks:localChecks,width:innerWidth,scroll:document.querySelector("#KendoWindowLevel1").scrollTop})');self.assertEqual(checks['width'],original['width']);self.assertEqual(checks['scroll'],70)
     self.assertTrue(all(x['sourceWidth']>=800 for x in checks['checks']));self.assertTrue(any(x['view']=='expiration' and x['standing'] for x in checks['checks']));self.assertTrue(any(x['view']=='financial' and x['latest'] and x['header'] for x in checks['checks']))
     encoded=out.get('images') or [out['image']];self.assertGreaterEqual(len(encoded),2);page_count+=len(encoded)
     asset=s.asset_for(json.dumps(encoded).encode(),kind='image_pages',state='TN',ein=org['ein'],run_id='local-responsive-000000001',source_url=out['source_url'],identifier='CO42115',record_name=org['name'])
     ref=s.archive(asset,ein=org['ein'],state='TN',run_id=asset['run_id'],store=store);_,pdf=s.saved_pdf(ref['url'].split('/')[-1][:-4],store)
     for pg,original in zip(PdfReader(io.BytesIO(pdf)).pages,encoded):
      self.assertEqual(pg.extract_text(),'');self.assertEqual(len(pg.images),1);objects=list(pg['/Resources']['/XObject'].get_object().values());self.assertEqual(objects[0].get_object().get_data(),base64.b64decode(original))
     if i==0:(ROOT.parent/'local-responsive-TN-fixture.pdf').write_bytes(pdf)
     await context.close()
   finally:
    for browser in browsers.values():await browser.close()
  self.assertEqual(len(http),30)
  (ROOT.parent/'gd-responsive-capture-receipt.json').write_text(json.dumps({'distinct_retained_contexts':30,'local_Chromium_CDP_captures':30,'original_image_pages':page_count,'original_JPEG_byte_preserved':True,'viewport_and_scroll_restored':True,'standing_and_latest_FYE_visible':True,'capture_mean_ms':sum(durations)/len(durations),'capture_max_ms':max(durations),'http_fixture_requests':len(http),'live_registry_queries':0,'commands':sorted(set(commands)),'limitation':'Source-backed responsive local fixtures; not 30 live searches or installed extension acceptance.'},indent=2))
if __name__=='__main__':unittest.main(verbosity=2)
