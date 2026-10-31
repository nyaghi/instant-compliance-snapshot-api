"""Selected NJ status lookup must hand its proven detail to evidence capture."""
import copy,time,threading,unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from deployment import source_visual_adapters as a
URL='https://charportal.dca.njoag.gov/CHR-Public-Details-Page/?id=11111111-1111-1111-1111-111111111111&rid=22222222-2222-2222-2222-222222222222'
class SelectedEvidenceHandoff(unittest.TestCase):
 def setUp(self):
  self.result={'state':'NJ','ein':'131846366','organization_name':'March of Dimes Inc.','success':True,'status':'Current','matched_registry_name':'MARCH OF DIMES INC','matched_registry_identifier':'','verified_registry_ein':'131846366'}
  self.run=SimpleNamespace(state='NJ',ein='131846366',documents=[],errors=[],capture_ms=0,source_detail_hints={'131846366':{'name':'MARCH OF DIMES INC','url':URL}},visual_adapter_facts=[])
  self.run.document=lambda url,raw,kind,text:self.run.documents.append((url,raw,kind,text,time.time(),''))
  self.fields={'name':'MARCH OF DIMES INC','crsm_federalein':'131846366','accountnumber':'CH0072600','crsm_filestanding':'Compliant','crsm_fiscalyearenddate_datepicker_description':'12/31/2025'}
  self.page=MagicMock();self.page.url=URL;self.page.goto.return_value=SimpleNamespace(status=200)
  self.page.evaluate.side_effect=lambda js:dict(self.fields)if js==a.NJ_VISIBLE_FIELDS else True
  self.page.inner_text.return_value='MARCH OF DIMES INC 131846366 CH0072600 Fiscal Year End 12/31/2025 Compliant'
  self.page.locator.return_value.evaluate.return_value={'width':1280,'height':1400};self.page.screenshot.return_value=b'fixture-image'
  self.context=MagicMock();self.context.new_page.return_value=self.page;self.browser=MagicMock();self.browser.new_context.return_value=self.context
  self.master=SimpleNamespace(checker=SimpleNamespace(sync_playwright=MagicMock()),BROWSER_LOOKUP_SEMAPHORE=threading.BoundedSemaphore(1),launch_lookup_browser=MagicMock(return_value=self.browser),nj_completed_future_detail=lambda *args:False)
 def capture(self,seconds=30):a.capture_selected_nj_source(self.master,self.result,self.run,time.monotonic()+seconds)
 def test_saved_result_without_display_identifier_produces_bound_original_detail(self):
  original=copy.deepcopy(self.result);self.capture();self.assertEqual(self.result,original);self.assertEqual(len(self.run.documents),1);self.assertEqual(self.run.documents[0][0],URL);self.assertIn('12/31/2025',self.run.documents[0][3]);self.assertEqual(self.run.visual_adapter_facts[0]['identity_source'],'verified_same_run_ein_hint');self.context.close.assert_called_once();self.browser.close.assert_called_once()
 def test_missing_wrong_or_unbound_identity_never_opens_evidence_page(self):
  for change in ['missing_verified','wrong_verified','wrong_ein','no_hint','wrong_name','unsafe_url']:
   with self.subTest(change=change):
    self.setUp()
    if change=='missing_verified':self.result.pop('verified_registry_ein')
    elif change=='wrong_verified':self.result['verified_registry_ein']='999999999'
    elif change=='wrong_ein':self.result['ein']='999999999'
    elif change=='no_hint':self.run.source_detail_hints={}
    elif change=='wrong_name':self.run.source_detail_hints['131846366']['name']='Unrelated Chapter'
    elif change=='unsafe_url':self.run.source_detail_hints['131846366']['url']=URL.replace('charportal.dca.njoag.gov','unrelated.example')
    self.capture();self.master.launch_lookup_browser.assert_not_called();self.assertEqual(self.run.documents,[])
 def test_existing_selected_original_is_not_fetched_again(self):
  self.run.documents=[(URL,b'original','image',self.page.inner_text.return_value,time.time(),'')];self.capture();self.master.launch_lookup_browser.assert_not_called();self.assertEqual(len(self.run.documents),1)
 def test_changed_identity_during_photo_is_rejected(self):
  before=dict(self.fields);after={**before,'crsm_federalein':'999999999'};reads=iter([before,after]);self.page.evaluate.side_effect=lambda js:next(reads)if js==a.NJ_VISIBLE_FIELDS else True
  self.capture();self.assertEqual(self.run.documents,[]);self.assertEqual(self.run.visual_adapter_facts[0]['outcome'],'source_changed_during_capture')
 def test_legacy_populated_identifier_remains_supported(self):
  self.result['matched_registry_identifier']='131846366';self.result.pop('verified_registry_ein');self.capture();self.assertEqual(len(self.run.documents),1);self.assertNotIn('identity_source',self.run.visual_adapter_facts[0])
 def test_near_deadline_does_not_start_a_second_page(self):
  self.capture(1);self.master.launch_lookup_browser.assert_not_called();self.assertEqual(self.run.visual_adapter_facts[0]['outcome'],'deadline_reserve')
if __name__=='__main__':unittest.main()
