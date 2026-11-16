import base64,json,threading,time,unittest
from types import SimpleNamespace as NS
from unittest.mock import MagicMock
from deployment import source_visual_adapters as va,pa_detail_evidence as pa
class CaptureRepair(unittest.TestCase):
 def va_case(self,mutation):
  fields={'fullName':'Community Foundation','status':'Not Authorized to Solicit','ein':'22-2281783'}
  text=['Registration Type Registration ID Expiration Date Footer before']
  page=MagicMock(url='https://vdacs.evokeplatform.com/app/publicPortal/entity/29747');page.goto.return_value=NS(status=200)
  panel=MagicMock();panel.count.return_value=1
  def field(sel):
   el=MagicMock();el.count.return_value=1;el.is_visible.return_value=True;k=sel.split('component-')[-1]
   el.inner_text.side_effect=lambda **kw:dict(fullName='Name',status='Status',ein='FEIN')[k]+'\n'+fields[k];return el
  panel.locator.side_effect=field
  empty=MagicMock();empty.count.return_value=1;empty.is_visible.return_value=True
  zero=MagicMock();zero.count.return_value=0
  page.locator.side_effect=lambda sel:panel if sel=='.formio-form'else zero
  page.get_by_role.return_value.count.return_value=1;page.get_by_role.return_value.get_attribute.return_value='true'
  page.get_by_text.return_value=empty;page.inner_text.side_effect=lambda *a,**kw:text[0]
  def photo(**kw):
   if mutation=='footer':text[0]='Registration Type Registration ID Expiration Date Footer after'
   if mutation in fields:fields[mutation]='Other'
   if mutation=='loading':zero.count.return_value=1
   if mutation=='verification':text[0]+=' verify you are human'
   if mutation=='url':page.url='https://vdacs.evokeplatform.com/app/publicPortal/entity/999'
   return b'original-virginia-pixels'
  page.screenshot.side_effect=photo
  context=MagicMock();context.new_page.return_value=page;browser=MagicMock();browser.new_context.return_value=context
  master=NS(checker=NS(sync_playwright=MagicMock()),launch_lookup_browser=MagicMock(return_value=browser),BROWSER_LOOKUP_SEMAPHORE=threading.BoundedSemaphore(1))
  run=NS(state='VA',ein='222281783',documents=[],capture_ms=0,visual_adapter_facts=[]);run.document=lambda *a,**kw:run.documents.append(a)
  result=dict(state='VA',ein=run.ein,success=True,status='Suspended',status_reason='VA_CONFIRMED_SOLICITATION_RESTRICTION',source_url=va.VA_FINAL_SEARCH,matched_registry_name='Community Foundation',matched_registry_identifier='29747',va_entity_evidence=dict(id='29747',entity_id='29747',ein=run.ein,name='Community Foundation',status='Not Authorized to Solicit',registration_count=0))
  va.capture_va_unregistered_entity(master,result,run,time.monotonic()+35)
  return run,page
 def test_va_original_pixels_and_unrelated_text(self):
  for change in ['none','footer']:
   with self.subTest(change=change):
    run,page=self.va_case(change);self.assertEqual(len(run.documents),1,run.visual_adapter_facts);self.assertEqual(run.documents[0][1],b'original-virginia-pixels');self.assertEqual(page.screenshot.call_count,1)
 def test_va_real_changes_rejected(self):
  for change in ['fullName','status','ein','loading','verification','url']:
   with self.subTest(change=change):
    run,page=self.va_case(change);self.assertEqual(run.documents,[]);self.assertEqual(page.screenshot.call_count,1)
 def test_pa_duplicate_and_exempt_original_pairs(self):
  for exempt in [False,True]:
   for changed in [False,True]:
    with self.subTest(exempt=exempt,changed=changed):
     cells=['Community Foundation','','','123'if not exempt else'','11/15/2026'if not exempt else'','22-2281783']+['EXEMPT FROM REGISTRATION REQUIREMENTS - E1'if exempt else'']+['']*5
     fields=dict(EntityName=cells[0],FederalID=cells[5],RegNum=cells[3],Expdt=cells[4],Status=cells[6])
     rows=[dict(index=0,cells=cells)]
     if not exempt:rows.append(dict(index=1,cells=[cells[0],'','','','',cells[5]]+['']*6))
     run=NS(state='PA',ein='222281783',visual_adapter_facts=[],documents=[]);run.document=lambda *a,**kw:run.documents.append(a)
     page=MagicMock(url=pa.SEARCH);page.locator.return_value.evaluate_all.return_value=rows
     popup=MagicMock(url=pa.DETAIL);page.expect_popup.return_value.__enter__.return_value.value=popup
     page.screenshot.return_value=b'original-list';popup.screenshot.return_value=b'original-detail'
     popup.evaluate.side_effect=[fields,True,dict(fields,FederalID='99-9999999')if changed else fields]
     token=pa.CURRENT.set(run);stop=pa.DEADLINE.set(time.monotonic()+20)
     try:pa.capture(page,NS(ein=run.ein),NS(state='PA',success=True,status='Exempt'if exempt else'Delinquent',raw_status_text=cells[4],matched_registry_name=cells[0],matched_registry_identifier=cells[3]))
     finally:pa.CURRENT.reset(token);pa.DEADLINE.reset(stop)
     self.assertEqual(len(run.documents),0 if changed else 1,run.visual_adapter_facts)
     if not changed:self.assertEqual([base64.b64decode(x)for x in json.loads(run.documents[0][1])],[b'original-list',b'original-detail'])
if __name__=='__main__':unittest.main(verbosity=2)
