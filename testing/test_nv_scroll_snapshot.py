"""30 actual local Chromium source-layout controls, not live searches."""
import asyncio,base64,io,json,sys,tempfile,time,unittest,os
from pathlib import Path
from playwright.async_api import async_playwright
from pypdf import PdfReader
R=Path(__file__).resolve().parents[1];P=R.parent;sys.path.insert(0,str(R))
from deployment import state_snapshots as s
COHORT=json.loads((R/'testing/fixtures/oct19-cohort.json').read_text())[:30]
FIELDS=[('Entity Name','LOCAL ORGANIZATION',515,277,0),('NV Business ID','NV19951158753',674,328,0),('Entity Status','Permanently Revoked',587,277,1),('Entity Type','Domestic Non-Profit Corporation (82)',710,328,1),('Formation Date in Nevada','11/27/1995',780,428,1),('Annual Renewal Due Date/Expiration Date','11/30/1996',832,378,0),('Solicits Charitable Contribution?','No',1492,678,0),('IRS Registered Name','-',1530,678,1),('Campaign Name','-',1570,728,1),('FEIN','-',1614,728,0)]
HTML='''<!doctype html><meta charset="utf-8"><style>*{box-sizing:border-box}body{margin:0;font:14px Arial}header{height:66px;background:#ccc}section.app-l-body{height:calc(100vh - 60px);overflow:auto;position:relative}main{position:relative;height:2500px}p{margin:0;line-height:18px}.field{position:absolute;left:20px;width:calc(100% - 40px);top:var(--n)}@media(min-width:768px){.field{top:var(--w);left:var(--l);width:46%}}footer{position:fixed;bottom:0;width:100%;height:53px;background:#ddd}</style><header>LOCAL SOURCE FIXTURE ONLY</header><section class="app-l-body"><main><div role="form"><h4>Entity Information</h4>'''+''.join(f'<div class="field" style="--n:{n}px;--w:{w}px;--l:{2 if c==0 else 51}%"><p><strong>{k}</strong></p><p'+(' id="org"' if k=='Entity Name' else '')+f'>{v}</p></div>' for k,v,n,w,c in FIELDS)+'''<h4 style="position:absolute;top:2000px">Agent Information</h4></div></main></section><footer>LOCAL SOURCE FOOTER</footer>'''
class Scroll(unittest.IsolatedAsyncioTestCase):
 async def test_thirty_source_layouts_capture_original_pages_without_resizing(self):
  content=(R/'browser-connector/registry-content.js').read_text(encoding='utf-8');worker=(R/'browser-connector/state-snapshot-worker.js').read_text(encoding='utf-8')
  durations=[];pages_count=[];requests=[];commands=[];temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
  async def fulfill(route):requests.append(route.request.url);await route.fulfill(content_type='text/html',body=HTML)
  async with async_playwright() as pw:
   browser=await pw.chromium.launch(headless=True)
   try:
    for i,org in enumerate(COHORT):
     width,height=[(570,324),(800,450),(1280,900)][i%3];context=await browser.new_context(viewport={'width':width,'height':height});page=await context.new_page();await page.route('**/*',fulfill);await page.goto('https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen?screen=Manage-Business&id=local')
     await page.locator('#org').evaluate('(e,n)=>e.textContent=n',org['name']);session=await context.new_cdp_session(page)
     async def send(method,params):
      self.assertIn(method,{'Page.getLayoutMetrics','Page.captureScreenshot'});commands.append(method);return await session.send(method,params)
     await page.expose_function('localCDP',send);await page.expose_function('localDetach',session.detach)
     await page.evaluate('''()=>{window.chrome={runtime:{id:'local',onMessage:{addListener:fn=>window.localListener=fn}},tabs:{get:async()=>({url:location.href}),sendMessage:async(id,m)=>new Promise(resolve=>localListener(m,{id:'local'},resolve))},debugger:{attach:async()=>{},sendCommand:async(t,m,p)=>window.localCDP(m,p||{}),detach:async()=>window.localDetach()}};window.P={TRIAL_ORIGIN:'https://local.test',sameQuery:(a,b)=>JSON.stringify(a)===JSON.stringify(b)};window.isActive=()=>true;window.owned=new Set([1]);window.registryOrigin=()=>location.origin;}''')
     original=await page.evaluate('({w:innerWidth,h:innerHeight,scroll:document.querySelector("section.app-l-body").scrollTop})');await page.add_script_tag(content=content);await page.add_script_tag(content=worker)
     meta=await page.evaluate('new Promise(resolve=>localListener({action:"registry-snapshot-metadata",query:{state:"NV",operation:"detail",identifier:"NV19951158753"}},{id:"local"},resolve))');self.assertTrue(meta['source_detail']);self.assertTrue(1<=len(meta['capture_views'])<=3,(width,meta));self.assertEqual(len(meta['capture_views']),[3,2,1][i%3])
     wrong=await page.evaluate('new Promise(resolve=>localListener({action:"registry-snapshot-metadata",query:{state:"NV",operation:"detail",identifier:"NV99999999"}},{id:"local"},resolve))');self.assertFalse(wrong['source_detail']);self.assertEqual(wrong['capture_views'],[])
     adverse=await page.evaluate('''async()=>{const q={state:'NV',operation:'detail',identifier:'NV19951158753'};const send=m=>new Promise(resolve=>localListener({action:'registry-snapshot-view',...m},{id:'local'},resolve));const bad=[{query:q,command_id:'local',view:'restore'},{query:q,command_id:'local',view:'nv-3'},{query:q,command_id:'local',view:'unknown'},{query:q,command_id:'',view:'nv-0'},{query:{...q,identifier:'NV99999999'},command_id:'local',view:'nv-0'}];return Promise.all(bad.map(send));}''');self.assertTrue(all(v.get('ok') is False for v in adverse));self.assertEqual(await page.evaluate('document.querySelector("section.app-l-body").scrollTop'),original['scroll'])
     started=time.monotonic();out=await page.evaluate('''async()=>{const query={state:'NV',operation:'detail',identifier:'NV19951158753'},job={tab:1,generation:1,pending:'local',command:{id:'local',query},registryState:'NV',activeExpiresAt:Date.now()+30000};return captureStateSnapshot(job,query,'local');}''');durations.append((time.monotonic()-started)*1000);self.assertIsNotNone(out,(width,meta));self.assertLess(out['capture_ms'],1500)
     after=await page.evaluate('({w:innerWidth,h:innerHeight,scroll:document.querySelector("section.app-l-body").scrollTop})');self.assertEqual(after,original)
     images=out.get('images',[out['image']]);self.assertEqual(len(images),len(meta['capture_views']));pages_count.append(len(images))
     with unittest.mock.patch.object(s,'STORE',s.SQLiteStore(Path(temp.name)/f'{i}.sqlite')):
      record={'state':'NV','ein':org['ein'],'organization_name':org['name'],'issued':time.time()};evidence={'query':out['query'],'complete':True,'fields':{'Entity Name':org['name'],'NV Business ID':'NV19951158753'}};s.connector_archive(record,{'query_id':'local','state_snapshot':out},out['query'],evidence);self.assertTrue(record.get('source_snapshots'))
      url=record['source_snapshots'][0]['url'];_,pdf=s.saved_pdf(url.split('/')[-1][:-4],s.STORE);pages=PdfReader(io.BytesIO(pdf)).pages;self.assertEqual(len(pages),len(images))
      for pg,img in zip(pages,images):self.assertEqual(pg.extract_text(),'');self.assertEqual(list(pg['/Resources']['/XObject'].get_object().values())[0].get_object().get_data(),base64.b64decode(img))
      if i==0:(P/'local-NV-scroll-source-fixture.pdf').write_bytes(pdf)
     await context.close()
   finally:await browser.close()
  self.assertEqual(len(requests),30);(P/'nv-scroll-local-receipt.json').write_text(json.dumps({'distinct_contexts':30,'actual_local_Chromium_captures':sum(pages_count),'pages_per_context':pages_count,'live_queries':0,'invalid_view_or_command_guards':150,'wrong_ID_guards':30,'viewport_resizes':0,'original_JPEG_bytes_equal':True,'source_scroll_restored':True,'source_footer_avoided':True,'mean_ms':sum(durations)/len(durations),'max_ms':max(durations),'commands':sorted(set(commands)),'limitation':'Source-backed local geometry fixture; fresh installed public-source validation still required.'},indent=2))
if __name__=='__main__':
 import unittest.mock
 unittest.main(verbosity=2)
