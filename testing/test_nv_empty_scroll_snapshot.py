"""Original page pixels from 30 local empty-source contexts, not live searches."""
import asyncio,base64,copy,io,json,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from playwright.async_api import async_playwright
from pypdf import PdfReader
R=Path(__file__).resolve().parents[1];P=R.parent;sys.path.insert(0,str(R))
from deployment import state_snapshots as s
COHORT=json.loads((R/'testing/fixtures/oct19-cohort.json').read_text())[:30]
HEADERS=['Entity Name','NV Business Id #','Entity No.','Entity Type','Registered Agent Name','Formation Date','Status']
HTML='''<!doctype html><meta charset="utf-8"><style>*{box-sizing:border-box}body{margin:0;font:14px Arial}header{height:55px;background:#ddd}section.app-l-body{height:calc(100vh - 60px);overflow:auto}main{height:1800px;position:relative}label{display:block}input{height:40px;width:90%}.query{position:absolute;top:350px;left:30px;width:90%}casex-data-table{display:block;position:absolute;top:650px;left:30px;width:90%}table{width:100%}td{height:226px;text-align:center}footer{position:fixed;bottom:0;height:53px;width:100%;background:#ddd}</style><header>LOCAL SOURCE FIXTURE ONLY</header><section class="app-l-body"><main><div role="combobox">Starts With</div><div class="query"><label id="name-label">Entity Name</label><input id="local-entityName" aria-labelledby="name-label"><input id="local-entityNumber"><input id="local-nvBusinessId"></div><casex-data-table><h4>Search Results</h4><table role="grid" aria-rowcount="1"><thead><tr>'''+''.join(f'<th role="columnheader" aria-label="{h}">{h}</th>' for h in HEADERS)+'''</tr></thead><tbody><tr class="k-grid-norecords" role="row"><td colspan="7">No records available</td></tr></tbody></table></casex-data-table></main></section><footer>LOCAL SOURCE FOOTER</footer>'''

class EmptyScroll(unittest.IsolatedAsyncioTestCase):
 async def test_thirty_empty_queries_original_pixels_archive_and_adverse_guards(self):
  source=(R/'browser-connector/registry-content.js').read_text();worker=(R/'browser-connector/state-snapshot-worker.js').read_text()
  # The local source model supplies the collector's already-completed receipt.
  # Initial/foreign receipts are separately rejected; no live scripts changed.
  source=source.replace('let nvLastSearch = null;','let nvLastSearch = window.localCompletedReceipt || null;',1)
  durations=[];pages_count=[];guards=0;temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
  async with async_playwright() as pw:
   browser=await pw.chromium.launch(headless=True)
   try:
    for i,org in enumerate(COHORT):
     width,height=[(570,324),(800,450),(1280,900)][i%3];context=await browser.new_context(viewport={'width':width,'height':height});page=await context.new_page()
     await page.route('**/*',lambda route:route.fulfill(content_type='text/html',body=HTML))
     await page.goto('https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen?screen=external-GenericFilingsSearch&tabRoute=business')
     q=dict(state='NV',operation='search',name=org['name']);await page.locator('#local-entityName').fill(org['name'])
     await page.evaluate('(q)=>window.localCompletedReceipt=q',q);session=await context.new_cdp_session(page);seen=[]
     async def send(method,params):
      self.assertIn(method,{'Page.getLayoutMetrics','Page.captureScreenshot'})
      if method=='Page.captureScreenshot':
       seen.append(await page.evaluate('''()=>{const panel=document.querySelector('section.app-l-body'),r=panel.getBoundingClientRect(),bottom=Math.min(innerHeight,document.querySelector('footer').getBoundingClientRect().top);const full=e=>{const b=e.getBoundingClientRect();return b.top>=r.top&&b.bottom<=bottom&&b.left>=0&&b.right<=innerWidth;};const range=document.createRange();range.selectNodeContents(document.querySelector('.k-grid-norecords td'));return {query:full(document.querySelector('#local-entityName')),empty:full(range)};}'''))
      return await session.send(method,params)
     await page.expose_function('localCDP',send);await page.expose_function('localDetach',session.detach)
     await page.evaluate('''()=>{window.chrome={runtime:{id:'local',onMessage:{addListener:fn=>window.localListener=fn}},tabs:{get:async()=>({url:location.href}),sendMessage:async(id,m)=>new Promise(resolve=>localListener(m,{id:'local'},resolve))},debugger:{attach:async()=>{},sendCommand:async(t,m,p)=>window.localCDP(m,p||{}),detach:async()=>window.localDetach()}};window.P={TRIAL_ORIGIN:'https://local.test',sameQuery:(a,b)=>JSON.stringify(a)===JSON.stringify(b)};window.isActive=()=>true;window.owned=new Set([1]);window.registryOrigin=()=>location.origin;}''')
     await page.add_script_tag(content=source);await page.add_script_tag(content=worker)
     request='(q)=>new Promise(resolve=>localListener({action:"registry-snapshot-metadata",query:q},{id:"local"},resolve))'
     meta=await page.evaluate(request,q);self.assertTrue(meta['source_search_empty'],meta);self.assertTrue(1<=len(meta['capture_views'])<=3)
     for bad in [{**q,'name':'OTHER'},{**q,'exact_above':20},{**q,'operation':'detail','identifier':'NV999999'}]:
      self.assertFalse((await page.evaluate(request,bad)).get('source_search_empty'));guards+=1
     for selector,prop,value in [('#local-entityName','value','OTHER'),('#local-entityNumber','value','123'),('#local-nvBusinessId','value','NV123'),('[role=combobox]','innerText','Exact Match'),('.k-grid-norecords td','innerText','Loading')]:
      original=await page.locator(selector).evaluate('(e,p)=>e[p]',prop);await page.locator(selector).evaluate('(e,x)=>e[x.p]=x.v',dict(p=prop,v=value));self.assertFalse((await page.evaluate(request,q)).get('source_search_empty'));guards+=1;await page.locator(selector).evaluate('(e,x)=>e[x.p]=x.v',dict(p=prop,v=original))
     original=await page.evaluate('({w:innerWidth,h:innerHeight,scroll:document.querySelector("section.app-l-body").scrollTop})')
     out=await page.evaluate('''async(q)=>{const job={tab:1,generation:1,pending:'local',command:{id:'local',query:q},registryState:'NV',activeExpiresAt:Date.now()+30000};return captureStateSnapshot(job,q,'local');}''',q)
     self.assertIsNotNone(out,meta);durations.append(out['capture_ms']);self.assertTrue(any(x['query'] for x in seen));self.assertTrue(any(x['empty'] for x in seen));self.assertEqual(await page.evaluate('({w:innerWidth,h:innerHeight,scroll:document.querySelector("section.app-l-body").scrollTop})'),original)
     images=out.get('images',[out['image']]);pages_count.append(len(images))
     with patch.object(s,'STORE',s.SQLiteStore(Path(temp.name)/f'{i}.sqlite')):
      record=dict(state='NV',ein=org['ein'],organization_name=org['name'],issued=time.time());evidence=dict(query=q,complete=True,total=0,rows=[])
      s.connector_archive(record,dict(query_id='local',state_snapshot=out),q,evidence);self.assertEqual(record['source_snapshots'][0]['identifier'],'@completed-search')
      _,pdf=s.saved_pdf(record['source_snapshots'][0]['url'].split('/')[-1][:-4],s.STORE);pages=PdfReader(io.BytesIO(pdf)).pages;self.assertEqual(len(pages),len(images))
      for pg,img in zip(pages,images):self.assertEqual(pg.extract_text(),'');self.assertEqual(list(pg['/Resources']['/XObject'].get_object().values())[0].get_object().get_data(),base64.b64decode(img))
      if i==0:(P/'local-NV-empty-scroll-source-fixture.pdf').write_bytes(pdf)
     await context.close()
   finally:await browser.close()
  (P/'nv-empty-scroll-local-receipt.json').write_text(json.dumps(dict(distinct_contexts=30,actual_local_Chromium_pages=sum(pages_count),pages_per_context=pages_count,adverse_guards=guards,mean_ms=sum(durations)/len(durations),max_ms=max(durations),query_and_empty_message_visible=True,original_JPEG_bytes_equal=True,source_scroll_restored=True,viewport_resizes=0,live_queries=0,limitation='Modeled completed source receipt and source-backed local DOM geometry; not30 live state searches'),indent=2))

if __name__=='__main__':unittest.main(verbosity=2)
