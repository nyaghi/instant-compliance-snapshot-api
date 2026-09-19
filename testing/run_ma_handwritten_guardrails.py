"""MA handwritten-account regression: actual public scan plus identity/retrieval controls."""
import copy,json,sys,unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c
F=Path(__file__).parent/'fixtures/ma-handwritten-account'
class Today(date):
 @classmethod
 def today(cls):return cls(2026,9,19)
class HandwrittenAccount(unittest.TestCase):
 def setUp(self):
  self.completed=json.loads((F/'completed-evidence.json').read_text())
  self.record=self.completed['record'];self.text=(F/'ocr.txt').read_text(encoding='utf8')
  self.url=next(r['url'] for r in self.completed['filings']['052619']['annual_scans'] if r['year']=='2021')
  p=patch.object(c,'date',Today);p.start();self.addCleanup(p.stop)
  p=patch.object(c.urllib.request,'urlopen',side_effect=AssertionError('Offline fixture'));p.start();self.addCleanup(p.stop)
 def parse(self,text=None,record=None,url=None,year=2021,period_text=''):
  return c.ma_scanned_form_pc_evidence(self.text if text is None else text,year,'052619','352058177',period_text,registry_record=self.record if record is None else record,document_url=self.url if url is None else url)
 def page(self):
  p=Mock();p.context.request.get.return_value.ok=True
  p.context.request.get.return_value.body.return_value=(F/'form-pc.tiff').read_bytes()
  p.locator.return_value.inner_text.return_value='AG Account Number 052619'
  p.get_by_role.return_value.all_inner_texts.return_value=['2021 FY2021 PC - Form PC/Annual RPT.tiff','2022 FY2022 PC - Other/Misc.tiff']
  return p
 def result(self):return c.checker.StateResult('Vera Bradley Foundation for Breast Cancer','352058177','MA','Current','')
 def test_original_failure_and_confirmed_period(self):
  self.assertFalse(c.ma_scanned_form_pc_evidence(self.text,2021,'052619','352058177'))
  r=self.parse();self.assertEqual(r['period_end'],'10/31/2021');self.assertTrue(r['legacy_identity_from_registry'])
 def test_missing_wrong_multiple_ein(self):
  for text in [self.text.replace('35-2058177',''),self.text.replace('35-2058177','99-9999999'),self.text+'\n99-9999999']:
   with self.subTest(text=text[-20:]):self.assertFalse(self.parse(text))
 def test_same_ein_with_wrong_partial_or_chapter_name(self):
  original='Vera Bradley Foundation for Breast Cancer, Inc.'
  for replacement in ['Vera Bradley Sales, LLC','Vera Bradley Foundation','Vera Bradley Foundation for Breast Cancer, Inc. Wisconsin Chapter','Vera Bradley Foundation for Breast Cancer','VBFBC','']:
   with self.subTest(replacement=replacement):self.assertFalse(self.parse(self.text.replace(original,replacement)))
 def test_registry_record_identity_required(self):
  for field,value in [('record_id',''),('record_id','not-a-record'),('ago_account','999999'),('ein','999999999'),('name','Different Foundation Inc'),('name','')]:
   record={**self.record,field:value}
   with self.subTest(field=field,value=value):self.assertFalse(self.parse(record=record))
  self.assertFalse(self.parse(record={}))
 def test_selected_official_document_required(self):
  for url in ['',self.url.replace('https:','http:'),self.url.replace('masscharities.my.site.com','example.com'),self.url.replace('document/download','other'),self.url+'/other']:
   with self.subTest(url=url):self.assertFalse(self.parse(url=url))
 def test_explicit_conflicting_account_is_not_treated_as_handwriting(self):
  for label in ["Attorney General's Account #: 999999","Attorney General Account: 999999","Attorney General’s Account # 999999"]:
   with self.subTest(label=label):self.assertFalse(self.parse(self.text+'\n'+label))
 def test_missing_form_or_period_label_and_wrong_year_rejected(self):
  for text in [self.text.replace('Form PC','Other/Misc'),self.text.replace('Report for the Fiscal Period','Received date')]:
   self.assertFalse(self.parse(text))
  self.assertFalse(self.parse(year=2022))
 def test_period_reread_cannot_replace_document_identity(self):
  period='Report for the Fiscal Period: 11/1/2020 to 10/31/2021'
  for text in [self.text.replace('35-2058177','99-9999999'),self.text.replace('Vera Bradley Foundation for Breast Cancer, Inc.','Different Foundation Inc')]:
   self.assertFalse(self.parse(text,period_text=period))
 def test_invalid_or_unreadable_period_still_rejected(self):
  for period in ['Report for the Fiscal Period: 11/1/2020 to 31/2021','Report for the Fiscal Period: 11/1/2020 to 2/31/2021','Report for the Fiscal Period: 11/1/2018 to 10/31/2021']:
   self.assertFalse(self.parse(period_text=period))
 def test_name_punctuation_and_order_only_equivalence(self):
  record={**self.record,'name':'Vera Bradley Foundation for Breast Cancer Inc'}
  self.assertTrue(self.parse(record=record))
  for name in ['Vera Bradley Foundation for Breast Cancer Inc Inc','Vera Bradley Foundation for Breast Cancer Inc New York','Vera Bradley Foundation for Breast Cancer Association']:
   self.assertFalse(self.parse(record={**record,'name':name}))
 def test_legible_account_path_remains_unchanged(self):
  text=self.text.replace('652619','052619')
  r=c.ma_scanned_form_pc_evidence(text,2021,'052619','352058177')
  self.assertEqual(r['period_end'],'10/31/2021');self.assertNotIn('legacy_identity_from_registry',r)
 def test_no_additional_request_or_ocr_when_corroborated(self):
  page=self.page();ocr=Mock(return_value=(json.loads((F/'ocr-lines.json').read_text()),None))
  with patch.object(c,'_MA_LEGACY_OCR',ocr),patch.object(c,'ma_scanned_period_row_text',side_effect=AssertionError('No second OCR pass')):
   r=c.ma_read_legacy_form_pc(page,self.completed,'052619')
  self.assertEqual(r['period_end'],'10/31/2021');page.context.request.get.assert_called_once_with(self.url,timeout=15000);ocr.assert_called_once()
 def test_actual_scan_through_master_period_status_and_comment(self):
  page=self.page();e=c.ma_read_latest_form_pc(page,self.result(),'AG Account Number 052619',self.completed)
  self.assertTrue(e['legacy_identity_from_registry']);self.assertEqual(e['period_end'],'10/31/2021')
  result=c.annotate_ma_visible_form_pc_due(self.result(),e)
  self.assertEqual(result.status,'Delinquent');self.assertEqual(result.computed_due_date,'9/15/2023')
  comment=c.comments_for_result(result,'','Delinquent')
  for value in ['10/31/2021','9/15/2023','automatic six-month extension']:self.assertIn(value,comment)
  self.assertNotIn('In-Progress',comment);page.context.request.get.assert_called_once()
 def test_unavailable_and_unreadable_download_not_delinquent(self):
  for mode in ['http','timeout','nonimage']:
   page=self.page()
   if mode=='http':page.context.request.get.return_value.ok=False
   elif mode=='timeout':page.context.request.get.side_effect=TimeoutError()
   else:page.context.request.get.return_value.body.return_value=b'incomplete'
   e=c.ma_read_latest_form_pc(page,self.result(),'AG Account Number 052619',self.completed)
   self.assertEqual(c.annotate_ma_visible_form_pc_due(self.result(),e).status,'Unable to Confirm')
 def test_duplicate_latest_and_wrong_record_not_first_selected(self):
  completed=copy.deepcopy(self.completed);rows=completed['filings']['052619']['annual_scans']
  rows.append({**next(r for r in rows if r['year']=='2021'),'url':self.url+'different'})
  page=self.page();self.assertFalse(c.ma_read_legacy_form_pc(page,completed,'052619'));page.context.request.get.assert_not_called()
  completed['record']['ago_account']='999999'
  self.assertFalse(c.ma_read_legacy_form_pc(page,completed,'052619'));page.context.request.get.assert_not_called()
 def test_visible_statuses_still_override_scan(self):
  for status,expected in [('Pending','Pending'),('In-Progress','Pending'),('Suspended','Suspended'),('Revoked','Revoked'),('Closed','Closed / Withdrawn / Canceled')]:
   page=self.page();body='AG Account Number 052619 Registration Status: '+status
   page.locator.return_value.inner_text.return_value=body
   e=c.ma_read_latest_form_pc(page,self.result(),body,self.completed)
   self.assertEqual(c.annotate_ma_visible_form_pc_due(self.result(),e).status,expected);page.context.request.get.assert_not_called()
 def test_recent_valid_period_not_forced_to_delinquent(self):
  text=self.text.replace('Report for the Fiscal Period: 11 01\n2020\nto\n10\n31\n2021','Report for the Fiscal Period: 1/1/2025 to 12/31/2025')
  e=self.parse(text,year=2025);self.assertEqual(e['period_end'],'12/31/2025')
  self.assertEqual(c.annotate_ma_visible_form_pc_due(self.result(),e).status,'Current')
if __name__=='__main__':unittest.main(verbosity=2)
