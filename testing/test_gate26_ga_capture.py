"""Replay retained official GA HTML through actual connector and Chromium pixels."""
import asyncio,base64,json,os,unittest
from pathlib import Path
from playwright.async_api import async_playwright
R=Path(__file__).resolve().parents[1]
F=R/'testing/fixtures/gate26'
class Capture(unittest.IsolatedAsyncioTestCase):
 async def test_actual_primary_record_capture_and_guards(self):
  html=json.loads((F/'GA-OFFICIAL-DETAIL.json').read_text())['html']
  package=R/'deployment/staging_connector'
  results=[]
  async with async_playwright() as p:
   browser=await p.chromium.launch(headless=True)
   try:
    for mode,width,height in [('baseline',1024,700),('good',1024,700),('small',600,379),('wide',1600,900),('wrong-id',1024,700),('wrong-name',1024,700),('changed',1024,700),('hidden',1024,700)]:
     context=await browser.new_context(viewport={'width':width,'height':height});page=await context.new_page()
     async def route(r):
      name=r.request.url.rsplit('/',1)[-1]
      asset=F/name
      if r.request.resource_type=='document':await r.fulfill(content_type='text/html',body=html)
      elif asset.is_file():await r.fulfill(path=str(asset))
      else:await r.fulfill(status=200,body='')
     await page.route('**/*',route);await page.goto('https://verify.sos.ga.gov/verification/Details.aspx?result=local')
     # Preserve the official primary section and force the observed long-history condition.
     await page.locator('#more_details').evaluate('(e)=>e.style.minHeight="3200px"')
     if mode=='hidden':await page.locator('span[id$="_status"]:not([id*="_label_"])').first.evaluate('(e)=>e.style.visibility="hidden"')
     session=await context.new_cdp_session(page);shots=[]
     async def send(method,params):
      result=await session.send(method,params)
      if method=='Page.captureScreenshot':
       shots.append(params)
       if mode=='changed':await page.locator('span[id$="_license_no"]').first.evaluate('(e)=>e.textContent="CH999999"')
      return result
     await page.expose_function('localCDP',send);await page.expose_function('localDetach',session.detach)
     await page.evaluate('''()=>{window.wfAwait=async(j,k,f)=>f();window.wfReturn=(j,k,v)=>v;window.logs=[];window.diagnostic=(a,b,c)=>logs.push(JSON.parse(c));window.chrome={runtime:{id:'local',onMessage:{addListener:fn=>window.localListener=fn}},tabs:{get:async()=>({url:location.href}),sendMessage:async(id,m)=>new Promise(resolve=>localListener(m,{id:'local'},resolve))},debugger:{attach:async()=>{},sendCommand:async(t,m,p)=>window.localCDP(m,p||{}),detach:async()=>window.localDetach()}};window.P={TRIAL_ORIGIN:'https://local.test',sameQuery:(a,b)=>JSON.stringify(a)===JSON.stringify(b)};window.isActive=()=>true;window.owned=new Set([1]);window.registryOrigin=()=>location.origin;}''')
     source=Path(os.environ['CC_BASELINE_CONNECTOR']) if mode=='baseline' else package
     await page.add_script_tag(content=(source/'registry-content.js').read_text(encoding='utf-8'))
     await page.add_script_tag(content=(source/'state-snapshot-worker.js').read_text(encoding='utf-8'))
     name=await page.locator('span[id$="_full_name"]:not([id*="_label_"])').first.inner_text()
     query={'state':'GA','identifier':'CH999999' if mode=='wrong-id' else 'CH002776','record_name':'Other Organization' if mode=='wrong-name' else ' '.join(name.split())}
     metadata=await page.evaluate('(query)=>new Promise(resolve=>localListener({action:"registry-snapshot-metadata",query},{id:"local"},resolve))',query)
     out=await page.evaluate('''async query=>{const job={tab:1,generation:1,pending:'local',command:{id:'local',query},registryState:'GA',activeExpiresAt:Date.now()+30000};return captureStateSnapshot(job,query,'local');}''',query)
     logs=await page.evaluate('logs');after=await page.evaluate('({width:innerWidth,height:innerHeight})')
     self.assertEqual(after,{'width':width,'height':height})
     good=mode in ('good','small','wide')
     geometry=await page.evaluate('''({boundary:document.querySelector('#more_details').getBoundingClientRect().toJSON(),spans:[...document.querySelectorAll('span[id]')].filter(e=>/^_ctl[0-9]+__ctl[0-9]+_(full_name|license_no|profession|license_type|status|issue_date|expiry|last_ren)$/.test(e.id)&&!!(e.compareDocumentPosition(document.querySelector('#more_details'))&Node.DOCUMENT_POSITION_FOLLOWING)).map(e=>({id:e.id,t:e.innerText,r:e.getBoundingClientRect().toJSON()}))})''')
     self.assertEqual(out is not None,good,(mode,geometry,logs))
     if good:
      self.assertEqual(len(shots),1);self.assertLess(out['capture_ms'],10000)
      (F/f'GA-{mode}.jpg').write_bytes(base64.b64decode(out['image']))
     elif mode!='changed':self.assertEqual(len(shots),0)
     results.append({'mode':mode,'captured':out is not None,'viewport_restored':True,'capture_ms':out['capture_ms'] if out else None,'trace':logs})
     await context.close()
   finally:await browser.close()
  (F/'GA-CAPTURE-RECEIPT.json').write_text(json.dumps(results,indent=2))
if __name__=='__main__':unittest.main(verbosity=2)
