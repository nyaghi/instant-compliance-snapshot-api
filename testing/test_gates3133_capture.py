import copy, io, time, unittest
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch
from testing.test_nj_selected_evidence_handoff import SelectedEvidenceHandoff
from deployment import gates3133_repairs as g, ma_status_extract as ma, pa_detail_evidence as pa

class NJRecovery(SelectedEvidenceHandoff):
 def test_capture_timeout_recovers_only_same_selected_record(self):
  self.page.screenshot.side_effect=[TimeoutError('capture timed out'),b'original']
  self.capture();self.assertEqual(len(self.run.documents),1)
  self.assertEqual(self.page.screenshot.call_count,2)
  self.assertLessEqual(self.page.screenshot.call_args.kwargs['timeout'],4000)
 def test_changed_record_during_timeout_is_not_retried(self):
  def failed(**kw):
   self.fields['crsm_federalein']='999999999';raise TimeoutError('capture timed out')
  self.page.screenshot.side_effect=failed;self.capture()
  self.assertEqual(self.run.documents,[]);self.assertEqual(self.page.screenshot.call_count,1)
 def test_other_capture_errors_are_not_retried(self):
  self.page.screenshot.side_effect=RuntimeError('browser closed');self.capture()
  self.assertEqual(self.run.documents,[]);self.assertEqual(self.page.screenshot.call_count,1)

class OriginalEvidence(unittest.TestCase):
 def test_nv_verified_mark_history_and_counterexamples(self):
  row=dict(identifier='NV20222655231',name='National college advising corps inc',entity_type='NT7 Business License Other')
  detail=dict(source_url='https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen?screen=Manage-Business&id=546cfde8-8298-4355-b566-8a825d08fd51',fields={'NV Business ID':row['identifier'],'Entity Name':row['name'],'Entity Type':row['entity_type'],'Solicits Charitable Contribution?':'No'},filings=dict(identifier=row['identifier'],name=row['name'],complete=True,total=2,headers=['Filed Date','Effective Date','Filing Number','Filing Type','No. of Pages'],rows=[['10/05/2023','10/05/2023','20233538792','Cancellation','1'],['12/22/2022','12/22/2022','20222829769','Mark Registration','2']]))
  self.assertTrue(g.nv_verified_mark_record(row,detail))
  for mutation in ['incomplete','total','duplicate','other_filing','solicits','identity','host','missing_registration']:
   bad=copy.deepcopy(detail)
   if mutation=='incomplete':bad['filings']['complete']=False
   elif mutation=='total':bad['filings']['total']=3
   elif mutation=='duplicate':bad['filings']['rows'][0][2]=bad['filings']['rows'][1][2]
   elif mutation=='other_filing':bad['filings']['rows'][0][3]='Charitable Solicitation Registration'
   elif mutation=='solicits':bad['fields']['Solicits Charitable Contribution?']='Yes'
   elif mutation=='identity':bad['fields']['NV Business ID']='NV99999999999'
   elif mutation=='host':bad['source_url']=bad['source_url'].replace('orion.nv.gov','example.com')
   else:bad['filings']['rows'][1][3]='Cancellation'
   with self.subTest(mutation=mutation):self.assertFalse(g.nv_verified_mark_record(row,bad))

 def test_ma_extract_is_explicit_and_preserves_original_page(self):
  from reportlab.pdfgen.canvas import Canvas
  from pypdf import PdfReader
  original=io.BytesIO();c=Canvas(original);c.drawString(50,700,'Original source fixture');c.save()
  value=dict(ein='123456789',name='Example Charity',ago_account='123456',registry_status='Deactivated',source_field='Charity_Status__c',source_url='https://masscharities.my.site.com/FilingSearch/s/detail/a09123456789012')
  meta=dict(state='MA',ein=value['ein'],identifier=value['ago_account'],record_name=value['name'])
  self.assertEqual(ma.validate(value,meta),value)
  pdf=PdfReader(io.BytesIO(ma.append(original.getvalue(),value)))
  self.assertEqual(len(pdf.pages),2);self.assertIn('Original source fixture',pdf.pages[0].extract_text())
  self.assertIn('not a screenshot',pdf.pages[1].extract_text());self.assertIn('Deactivated',pdf.pages[1].extract_text())
  for field in ['ein','ago_account','name','source_field','source_url']:
   with self.subTest(field=field),self.assertRaises(ValueError):ma.validate(dict(value,**{field:'wrong'}),meta)

 def test_pa_original_pair_and_changed_detail_rejection(self):
  for changed in [False,True]:
   with self.subTest(changed=changed):
    cells=['TEACH FOR ALL, INC.','','','101367','08/15/2027','26-2122566']+['']*6
    fields=dict(EntityName=cells[0],RegNum=cells[3],Expdt=cells[4],FederalID=cells[5])
    run=NS(state='PA',ein='262122566',visual_adapter_facts=[],documents=[])
    run.document=lambda *args,**kw:run.documents.append(args)
    page=MagicMock(url=pa.SEARCH)
    from unittest.mock import create_autospec
    from playwright.sync_api import Locator
    page.locator.return_value.evaluate_all=create_autospec(Locator,instance=True).evaluate_all
    page.locator.return_value.evaluate_all.side_effect=lambda expression, arg=None:[dict(index=0,cells=cells)]
    popup=MagicMock(url=pa.DETAIL);page.expect_popup.return_value.__enter__.return_value.value=popup
    page.screenshot.return_value=b'original-grid';popup.screenshot.return_value=b'original-detail'
    popup.evaluate.side_effect=[fields,dict(fields,RegNum='999999') if changed else fields]
    token=pa.CURRENT.set(run);deadline=pa.DEADLINE.set(time.monotonic()+30)
    try:pa.capture(page,NS(ein=run.ein),NS(state='PA',success=True,status='Current',matched_registry_name=cells[0],matched_registry_identifier=cells[3]))
    finally:pa.CURRENT.reset(token);pa.DEADLINE.reset(deadline)
    self.assertEqual(len(run.documents),0 if changed else 1);popup.close.assert_called_once()
    if not changed:
     import json,base64
     self.assertEqual([base64.b64decode(v) for v in json.loads(run.documents[0][1])],[b'original-grid',b'original-detail'])

if __name__=='__main__':unittest.main()
