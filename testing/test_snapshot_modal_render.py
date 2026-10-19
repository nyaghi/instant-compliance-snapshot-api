"""Actual local browser rendering of a clearly marked Kendo-shaped fixture."""
import base64,io,json,sys,time,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from deployment import state_snapshots as s
from testing.test_state_snapshots import COHORT
from pypdf import PdfReader
from PIL import Image

class Render(unittest.TestCase):
 def test_thirty_local_rendered_dialogs_capture_and_restore_original_views(self):
  source=(ROOT/'browser-connector/registry-content.js').read_text(encoding='utf-8')
  calls=[]
  with tempfile.TemporaryDirectory() as tmp,sync_playwright() as p:
   store=s.SQLiteStore(Path(tmp)/'archive.sqlite')
   browser=p.chromium.launch(headless=True)
   try:
    page=browser.new_page(viewport={'width':640,'height':440})
    def fulfill(route):
     calls.append(route.request.url);route.fulfill(content_type='text/html',body='<html><body>LOCAL TEST ONLY</body></html>')
    page.route('**/*',fulfill)
    page.goto('https://tncab.tnsos.gov/portal/registered-charities-search')
    for index,org in enumerate(COHORT):
     page.set_content('''<style>body{font-family:Arial;background:#ddd}#KendoWindowLevel1{position:fixed;top:20px;left:30px;width:550px;height:300px;overflow:auto;background:white;border:2px solid #333}.gap{height:270px}h4{margin:12px}</style>
      <p>LOCAL SOURCE FIXTURE -- NOT A LIVE STATE CAPTURE</p><div id="KendoWindowLevel1"><h2 id="name"></h2><h4>CO Number: CO42115</h4><h4>Status: Expired</h4><div class="gap"></div><h4>Expiration Date: 08/28/2023</h4><div class="gap"></div><div id="DetailsTabStrip-1"><table><tbody><tr><td>Fiscal Year End: 09/30/2020</td></tr></tbody></table></div><div class="gap"></div></div>''')
     page.locator('#name').evaluate('(el,name)=>el.textContent="LOCAL FIXTURE: "+name',org['name'])
     page.evaluate('''() => {window.chrome={runtime:{id:'local-extension',onMessage:{addListener:fn=>window.localSnapshotListener=fn}}};document.querySelector('#KendoWindowLevel1').scrollTop=90;}''')
     page.add_script_tag(content=source)
     query={'state':'TN','operation':'detail','identifier':'CO42115'}
     def request(action,view=None):
      m={'action':action,'query':query,'command_id':'local-command'}
      if view:m['view']=view
      return page.evaluate('m=>new Promise(resolve=>window.localSnapshotListener(m,{id:"local-extension"},resolve))',m)
     meta=request('registry-snapshot-metadata');self.assertEqual(meta['capture_views'],['top','expiration','financial'])
     screenshots=[]
     for view in meta['capture_views']:
      self.assertTrue(request('registry-snapshot-view',view)['ok'])
      screenshots.append(page.screenshot())
     self.assertTrue(request('registry-snapshot-view','restore')['ok'])
     self.assertEqual(page.locator('#KendoWindowLevel1').evaluate('el=>el.scrollTop'),90)
     self.assertEqual(len(set(screenshots)),3)
     asset=s.asset_for(json.dumps([base64.b64encode(b).decode() for b in screenshots]).encode(),kind='image_pages',state='TN',ein=org['ein'],run_id='local-render-00000000000001',source_url=meta['url'],record_name=org['name'],identifier='CO42115',capture_note='LOCAL MODELED SOURCE DOM; no real registry search.')
     ref=s.archive(asset,ein=org['ein'],state='TN',run_id=asset['run_id'],store=store)
     _,pdf=s.saved_pdf(ref['url'].split('/')[-1][:-4],store)
     pages=PdfReader(io.BytesIO(pdf)).pages;self.assertEqual(len(pages),3)
     for page_pdf,png in zip(pages,screenshots):
      with Image.open(io.BytesIO(page_pdf.images[0].data)) as embedded,Image.open(io.BytesIO(png)) as original:self.assertEqual(embedded.convert('RGB').tobytes(),original.convert('RGB').tobytes())
     if index==0:(ROOT.parent/'local-modal-source-coverage-fixture.pdf').write_bytes(pdf)
    self.assertEqual(len(calls),1,'Source view capture must not issue a search or extra HTTP request')
   finally:browser.close()
  (ROOT.parent/'modal-render-local-receipt.json').write_text(json.dumps({'retained_identity_contexts':30,'real_local_browser_dialogs':30,'fixture_screenshot_pages':90,'pixel_equal':True,'source_scroll_restored':True,'fixture_HTTP_requests':len(calls),'registry_queries':0,'scope':'Local modeled source DOM; not live Tennessee validation'},indent=2))

if __name__=='__main__':unittest.main(verbosity=2)
