import copy,time,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from playwright.sync_api import sync_playwright
from deployment import md_listing_evidence as m
from testing import test_md_capture_finish as md_controls

class ListingEvidence(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.p=sync_playwright().start();cls.browser=cls.p.chromium.launch(headless=True)
 @classmethod
 def tearDownClass(cls):cls.browser.close();cls.p.stop()
 def execute(self,mutation='',remaining=6):
  table=(Path(__file__).parent/'fixtures/md_irex_official_listing.html').read_text(encoding='utf8')
  if mutation=='ein':table=table.replace('22-3087809','99-9999999')
  if mutation=='id':table=table.replace('23836','99999')
  if mutation=='status':table=table.replace('Current','Expired')
  if mutation=='name':table=table.replace('International Research and Exchanges Board, Inc.','Other Charity')
  if mutation=='link':table=table.replace('62f96f50a51891019eb6c5b7','a'*24)
  if mutation=='duplicate':table+=table
  fixture='<html><body><input id="filter-'+m.FIELD+'" value="22-3087809"><div role="status">1 record</div>'+table+(' Verify you are human' if mutation=='blocked' else '')+'</body></html>'
  if mutation=='slow':
   import json
   fixture='<html><body>Loading...<script>setTimeout(()=>document.body.innerHTML='+json.dumps(fixture.replace('<html><body>','').replace('</body></html>',''))+',7000)</script></body></html>'
  ctx=self.browser.new_context();requests=[]
  ctx.route('**/*',lambda route:(requests.append(route.request.url),route.fulfill(status=504 if mutation=='http' else 200,content_type='text/html',body=fixture)))
  result=dict(state='MD',ein='223087809',success=True,status='Current',matched_registry_name='International Research and Exchanges Board, Inc.',matched_registry_identifier='23836',source_url=m.LIST)
  hint=dict(url='https://onestop.md.gov/detail_views/62f3e17b7f7e3200016a4b6c/entry/62f96f50a51891019eb6c5b7',source_fields={'status':'Current'})
  run=NS(state='MD',ein=result['ein'],documents=[],capture_ms=0,visual_adapter_facts=[]);run.document=lambda *a,**kw:run.documents.append((a,kw))
  new=ctx.new_page
  def page():
   p=new()
   if mutation=='changed':
    shot=p.screenshot
    def screenshot(**kw):
     raw=shot(**kw);p.locator('body').evaluate('(e)=>e.append(" source changed")');return raw
    p.screenshot=screenshot
   return p
  original=copy.deepcopy(result)
  try:
   m.capture(run,result,hint,NS(new_page=page),time.monotonic()+remaining)
   self.assertEqual(result,original);self.assertEqual(ctx.pages,[])
   return run,requests
  finally:ctx.close()
 def test_official_listing_original_captures_exact_record(self):
  r,requests=self.execute();self.assertEqual(len(r.documents),1);self.assertEqual(len(requests),1);self.assertTrue(r.documents[0][0][1].startswith(b'\xff\xd8'))
  self.assertIn('detail page was unavailable',r.documents[0][1]['note'])
 def test_wrong_identity_status_link_block_and_changed_source_rejected(self):
  for mutation in ['ein','id','status','name','link','duplicate','blocked','changed','http']:
   with self.subTest(mutation=mutation):
    r,_=self.execute(mutation);self.assertEqual(r.documents,[])
 def test_expired_deadline_does_not_navigate(self):
  r,requests=self.execute(remaining=0);self.assertEqual(requests,[]);self.assertEqual(r.documents,[])
 def test_observed_listing_loading_boundary_can_finish_within_ten_seconds(self):
  r,requests=self.execute('slow',remaining=10);self.assertEqual(len(r.documents),1);self.assertLess(r.visual_adapter_facts[0]['total_ms'],10000)

class RecoveryAdmission(unittest.TestCase):
 run_case=md_controls.MarylandFinishTests.run_case
 def test_only_access_failures_enter_listing_fallback(self):
  for opts,eligible in [({'nav':40},True),({'http_status':504,'nav':1},True),({'http_status':403,'nav':1},False),({'fields':{'Charity ID':'999'}},False),({'change_shot':True},False),({'nav':1,'panel_delay':.1},False)]:
   with self.subTest(opts=opts),patch.object(m,'capture') as capture:
    self.run_case(**opts)
    self.assertEqual(capture.call_count,int(eligible))
    if eligible:self.assertLessEqual(capture.call_args.args[-1],140)

if __name__=='__main__':unittest.main()
