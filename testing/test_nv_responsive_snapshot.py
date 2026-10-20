"""Actual local Chromium/CDP captures; source-backed layout fixture, no live queries."""
import asyncio,base64,io,json,sys,tempfile,time,unittest,os,subprocess
from pathlib import Path
from playwright.async_api import async_playwright
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from deployment import state_snapshots as s
COHORT=json.loads((ROOT/'testing/fixtures/oct19-cohort.json').read_text())[:30]
FIELDS=[('Entity Name','LOCAL ORGANIZATION'),('NV Business ID','NV19951158753'),('Entity Status','Permanently Revoked'),('Entity Type','Domestic Non-Profit Corporation (82)'),('Formation Date in Nevada','11/27/1995'),('Annual Renewal Due Date/Expiration Date','11/30/1996'),('Solicits Charitable Contribution?','No'),('IRS Registered Name','-'),('Campaign Name','-'),('FEIN','-')]
HTML='''<!doctype html><meta charset="utf-8"><style>
*{box-sizing:border-box}body{margin:0;font:16px Arial}header{height:60px;padding:16px;background:#eee}
section.app-l-body{position:relative;max-height:calc(100vh - 60px);overflow:hidden auto;transition:.2s ease-in}
main{padding:25px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:22px}p{margin:9px 0}h1{font-size:30px}
@media(max-width:767px){.grid{grid-template-columns:1fr}}footer{position:fixed;bottom:0;background:#ddd;width:100%;height:30px}
</style><header>LOCAL SOURCE LAYOUT FIXTURE - NOT LIVE EVIDENCE</header><section class="app-l-body"><main>
<h1 id="org">LOCAL ORGANIZATION</h1><button>Return To Results</button><h4>Entity Information</h4><div role="form"><h4>Entity Information</h4><div class="grid">'''+''.join('<div><p><strong>'+k+'</strong></p><p>'+v+'</p></div>' for k,v in FIELDS)+'''</div><h4>Agent Information</h4><p>Excluded from identity</p><div style="height:1800px">LOCAL lower source panel</div></div></main></section><footer>LOCAL footer</footer>'''
class Responsive(unittest.IsolatedAsyncioTestCase):
 async def test_thirty_native_windows_capture_complete_original_fields_and_restore(self):
  # Historical GE viewport experiment, kept separate from candidate scroll coverage.
  content=subprocess.check_output(['git','show','b033361c760abceaabb08988a2a128b7d5fad10d:browser-connector/registry-content.js'],cwd=ROOT,text=True,encoding='utf-8');worker=subprocess.check_output(['git','show','b033361c760abceaabb08988a2a128b7d5fad10d:browser-connector/state-snapshot-worker.js'],cwd=ROOT,text=True,encoding='utf-8')
  durations=[];requests=[];commands=[];initial_clipped=0
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
  async def fulfill(route):requests.append(route.request.url);await route.fulfill(content_type='text/html',body=HTML)
  async with async_playwright() as pw:
   sizes=[(360,280),(640,440),(1280,900)];browsers={w:await pw.chromium.launch(headless=True,args=[f'--window-size={w},{h}']) for w,h in sizes}
   try:
    store=s.SQLiteStore(Path(temp.name)/'local.sqlite')
    for i,org in enumerate(COHORT):
     w,h=sizes[i%3];context=await browsers[w].new_context(no_viewport=True);page=await context.new_page();await page.route('**/*',fulfill)
     await page.goto('https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen?screen=Manage-Business&id=local')
     await page.locator('#org').evaluate('(e,n)=>e.textContent="LOCAL: "+n',org['name']);session=await context.new_cdp_session(page)
     async def send(method,params):
      self.assertIn(method,{'Page.getLayoutMetrics','Page.captureScreenshot','Emulation.setDeviceMetricsOverride','Emulation.clearDeviceMetricsOverride'});commands.append(method);return await session.send(method,params)
     await page.expose_function('localCDP',send);await page.expose_function('localDetach',session.detach)
     await page.evaluate('''()=>{window.chrome={runtime:{id:'local',onMessage:{addListener:fn=>window.localListener=fn}},tabs:{get:async()=>({url:location.href}),sendMessage:async(id,m)=>new Promise(resolve=>localListener(m,{id:'local'},resolve))},debugger:{attach:async()=>{},sendCommand:async(t,m,p)=>window.localCDP(m,p||{}),detach:async()=>window.localDetach()}};window.P={TRIAL_ORIGIN:'https://local.test',sameQuery:(a,b)=>JSON.stringify(a)===JSON.stringify(b)};window.isActive=()=>true;window.owned=new Set([1]);window.registryOrigin=()=>location.origin;}''')
     original=await page.evaluate('({w:innerWidth,h:innerHeight,scroll:document.querySelector("section.app-l-body").scrollTop})')
     await page.add_script_tag(content=content);await page.add_script_tag(content=worker)
     before=await page.evaluate('new Promise(resolve=>localListener({action:"registry-snapshot-metadata",query:{state:"NV",operation:"detail",identifier:"NV19951158753"}},{id:"local"},resolve))')
     self.assertTrue(before['source_detail']);initial_clipped+=not before['source_fields_visible']
     wrong=await page.evaluate('new Promise(resolve=>localListener({action:"registry-snapshot-metadata",query:{state:"NV",operation:"detail",identifier:"NV99999999"}},{id:"local"},resolve))');self.assertFalse(wrong['source_detail']);self.assertFalse(wrong['source_fields_visible'])
     await page.evaluate('''()=>{const send=chrome.tabs.sendMessage;chrome.tabs.sendMessage=async(id,m)=>{const out=await send(id,m);if(m.settle)window.localCaptureMeta=out;return out;};}''')
     started=time.monotonic();out=await asyncio.wait_for(page.evaluate('''async()=>{const query={state:'NV',operation:'detail',identifier:'NV19951158753'},job={tab:1,generation:1,pending:'local',command:{id:'local',query},registryState:'NV',activeExpiresAt:Date.now()+30000};return captureStateSnapshot(job,query,'local');}'''),10);durations.append((time.monotonic()-started)*1000)
     self.assertIsNotNone(out,(org['name'],original));self.assertLess(out['capture_ms'],1500)
     after=await page.evaluate('({w:innerWidth,h:innerHeight,scroll:document.querySelector("section.app-l-body").scrollTop})');self.assertEqual(after,original)
     self.assertTrue((await page.evaluate('localCaptureMeta'))['source_fields_visible'])
     asset=s.asset_for(base64.b64decode(out['image']),kind='image',state='NV',ein=org['ein'],run_id='local-nv-capture-00000001',source_url=out['source_url'],identifier='NV19951158753',record_name=org['name'])
     ref=s.archive(asset,ein=org['ein'],state='NV',run_id=asset['run_id'],store=store);_,pdf=s.saved_pdf(ref['url'].split('/')[-1][:-4],store)
     pg=PdfReader(io.BytesIO(pdf)).pages[0];self.assertEqual(pg.extract_text(),'');self.assertEqual(list(pg['/Resources']['/XObject'].get_object().values())[0].get_object().get_data(),base64.b64decode(out['image']))
     if i==0 and not os.environ.get('CC_SNAPSHOT_RECEIPT_PATH'):(ROOT.parent/'local-responsive-NV-fixture.pdf').write_bytes(pdf)
     await context.close()
   finally:
    for browser in browsers.values():await browser.close()
  self.assertEqual(len(requests),30);self.assertGreaterEqual(initial_clipped,20)
  Path(os.environ.get('CC_SNAPSHOT_RECEIPT_PATH',str(ROOT.parent/'nv-crop-local-capture-receipt.json'))).write_text(json.dumps({'distinct_contexts':30,'local_Chromium_CDP_captures':30,'original_JPEG_byte_preserved':True,'source_fields_visible':True,'viewport_and_scroll_restored':True,'initial_clipped_contexts':initial_clipped,'mean_ms':sum(durations)/len(durations),'max_ms':max(durations),'live_queries':0,'commands':sorted(set(commands)),'limitation':'Source-backed modeled local layout; actual source desktop experiment separate, not 30 live searches.'},indent=2))
if __name__=='__main__':unittest.main(verbosity=2)
