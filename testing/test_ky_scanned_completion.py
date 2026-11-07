"""KY-only first scanned-header completion; all network and clocks modeled."""
import ast,copy,io,json,subprocess,sys,time,types,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import registry_snapshot_server as c
from deployment.state_snapshots import CURRENT,DEADLINE,CaptureRun
FIX=Path(__file__).parent/'fixtures/hi-christian-header'

class KYScanCompletion(unittest.TestCase):
 def setUp(self):
  self.org=c.checker.Organization('Period Control Foundation','226063412')
 def call(self,*,state='KY',ein='226063412',name=None,parent=200,mode='standard',trial=True,none=False):
  run=None if none else types.SimpleNamespace(state=state,ein=ein,name=name or self.org.organization_name)
  tokens=[(CURRENT,CURRENT.set(run)),(DEADLINE,DEADLINE.set(parent)),(c.LAB_LOOKUP_MODE_CONTEXT,c.LAB_LOOKUP_MODE_CONTEXT.set(mode))]
  try:
   with patch.object(c,'trial_identity',return_value={'origin':'local'}if trial else None),patch.object(c.time,'monotonic',return_value=10),patch.object(c,'irs_period_for_label',return_value={'verified':'model'})as read:
    result=c.ky_filed_period_evidence(self.org,2025);return result,read.call_args
  finally:
   for var,token in reversed(tokens):var.reset(token)
 def test_thirty_bound_contexts_keep_retrieval14_and_first_scan28(self):
  for i in range(30):
   self.org=c.checker.Organization('Period Control '+str(i),str(120000000+i))
   _,args=self.call(ein=str(120000000+i));self.assertEqual(args.args,(self.org.ein,2025,24));self.assertEqual(args.kwargs,{'scanned_deadline':38,'ky_cover_scan':True})
 def test_other_state_identity_mode_and_unowned_context_keep_legacy_call(self):
  for kw in [{'state':'HI'},{'ein':'999999999'},{'name':'Different Name'},{'mode':'sales'},{'trial':False},{'none':True},{'parent':float('nan')},{'parent':float('inf')}]:
   with self.subTest(kw=kw):
    _,args=self.call(**kw);self.assertEqual(args.args,(self.org.ein,2025,24));self.assertEqual(args.kwargs,{})
 def test_parent_cutoff_limits_retrieval_and_cannot_start_after_expiry(self):
  for parent,stop in [(25,24),(23,22),(15,14)]:
   _,args=self.call(parent=parent);self.assertEqual(args.args[-1],stop);self.assertEqual(args.kwargs,{})
  result,args=self.call(parent=10);self.assertIsNone(args);self.assertTrue(result['period_unconfirmed']);self.assertNotIn('period_end',result)
 def scan(self,*,reserve=False,page=0,ein='226063412',label=2025):
  rows=json.loads((FIX/'rows.json').read_text())['rows'];pic=Image.open(FIX/'header.png');height=pic.height;clock=[0.0]
  def title(*args,**kw):
   clock[0]+=1;return [[[[0,0],[10,0],[10,10],[0,10]],'Form 990 Return of Organization Exempt From Income Tax',.999]],None
  def body(image,**kw):
   if kw.get('use_det')is False:clock[0]+=4;return [[',20 2026',.96]],None
   clock[0]+=6 if image.height<height else 7
   return ([],None)if image.height<height else(copy.deepcopy(rows),None)
  with patch.dict(sys.modules,{'rapidocr_onnxruntime':types.SimpleNamespace(RapidOCR=lambda **k:None)}),patch.object(c,'IRS_HEADER_OCR',body),patch.object(c,'IRS_HEADER_TITLE_OCR',title),patch.object(c.time,'monotonic',side_effect=lambda:clock[0]):
   return c.irs_scanned_header_period([(page,pic)],ein,label,'https://state/return.pdf',14,require_complete=True,legacy_heights={0:int(height*.75),page:int(height*.75)},**({'first_page_deadline':28}if reserve else{}))
 def test_modeled_actual_header_completes_after14_only_on_first_page(self):
  with self.assertRaises(c.FilingPeriodReadIncomplete):self.scan()
  result=self.scan(reserve=True);self.assertEqual((result['period_begin'],result['period_end']),('2025-07-01','2026-06-30'))
  with self.assertRaises(c.FilingPeriodReadIncomplete):self.scan(reserve=True,page=1)
 def test_reserve_does_not_accept_wrong_ein_or_tax_year(self):
  for kw in [{'ein':'999999999'},{'label':2024}]:
   with self.subTest(kw=kw),self.assertRaises(c.FilingPeriodReadIncomplete):self.scan(reserve=True,**kw)
 def test_late_scanned_evidence_is_rejected_after_reserved_stop(self):
  with Image.open(FIX/'header.png')as image:
   stream=io.BytesIO();image.convert('RGB').save(stream,format='PDF');raw=stream.getvalue()
  clock=[0.0]
  def late(*args,**kw):
   self.assertEqual(kw['first_page_deadline'],28)
   for _,image in args[0]:image.close()
   clock[0]=29;return {'ein':'226063412','tax_year_label':2025,'period_begin':'2025-07-01','period_end':'2026-06-30'}
  with patch.object(c.time,'monotonic',side_effect=lambda:clock[0]),patch.object(c,'irs_scanned_header_period',side_effect=late),self.assertRaises(c.FilingPeriodReadIncomplete):
   c.form990_pdf_period(raw,'226063412',2025,'https://state/return.pdf',14,require_complete=True,scanned_deadline=28)
 def test_document_fetch_keeps_original_deadline_and_cannot_consume_scan_reserve(self):
  source='<a rel="/charity/attachments/irs/226063412/2025/return.pdf">IRSForm990</a>'
  def fetch(url,deadline,**kw):self.assertEqual(deadline,14);raise TimeoutError('modeled retrieval timeout')
  with patch.object(c,'identity_fetch',side_effect=fetch),patch.object(c,'form990_pdf_period')as scan,self.assertRaises(c.FilingPeriodReadIncomplete):
   c.hi_attachment_period(source,'226063412',2025,14,scanned_deadline=28)
  scan.assert_not_called()
 def test_verified_text_header_returns_without_scanned_reserve(self):
  text='Form 990 EIN 22-6063412\nFor the 2025 tax year beginning 7/1/2025 and ending 6/30/2026'
  reader=types.SimpleNamespace(pages=[types.SimpleNamespace(extract_text=lambda **kw:text)])
  with patch.object(c,'PdfReader',return_value=reader),patch.object(c,'irs_scanned_header_period')as scan:
   result=c.form990_pdf_period(b'%PDF modeled','226063412',2025,'https://state/return.pdf',time.monotonic()+14,require_complete=True,scanned_deadline=time.monotonic()+28)
  self.assertEqual(result['period_end'],'2026-06-30');self.assertNotIn('scanned_completion_reserve',result);scan.assert_not_called()
 def test_exact_old_and_new_ky_caller_join_through_attachment_and_scanned_parser(self):
  root=Path(__file__).resolve().parents[1]
  old_source=subprocess.check_output(['git','show','fc62ae963e34b15a4472954bf47acdfc9c408406:registry_snapshot_server.py'],cwd=root,text=True,encoding='utf-8')
  node=next(n for n in ast.parse(old_source).body if isinstance(n,ast.FunctionDef)and n.name=='search_ky_strict_snapshot')
  scope=dict(vars(c));exec(compile(ast.Module(body=[node],type_ignores=[]),'exact-MY-KY-caller','exec'),scope)
  org=c.checker.Organization('Christian Research Institute Inc.','226063412')
  rows=json.loads((FIX/'rows.json').read_text())['rows']
  with Image.open(FIX/'header.png')as image:
   page=Image.new('RGB',(image.width,round(image.height/.24)),'white');page.paste(image,(0,0));stream=io.BytesIO();page.save(stream,format='PDF',resolution=108);page.close();pdf=stream.getvalue();header_height=image.height
  for arm,lookup in [('baseline',scope['search_ky_strict_snapshot']),('candidate',c.search_ky_strict_snapshot)]:
   clock=[0.0];calls=[]
   def fetch(url,deadline,**kw):
    self.assertLessEqual(deadline,14);calls.append(url);clock[0]+=.25
    if url.startswith('https://projects.propublica.org/nonprofits/organizations/'):
     return b'<html>No matching historical object IDs in this modeled index.</html>'
    if url.endswith('/details.html'):return b'<a rel="/charity/attachments/irs/226063412/2025/fixture.pdf">IRSForm990</a>'
    self.assertTrue(url.endswith('/2025/fixture.pdf'));return pdf
   def title(*a,**kw):clock[0]+=1;return [[[[0,0],[10,0],[10,10],[0,10]],'Form 990 Return of Organization Exempt From Income Tax',.999]],None
   def ocr(image,**kw):
    if kw.get('use_det')is False:clock[0]+=4;return [[',20 2026',.96]],None
    short=image.height<header_height-1;clock[0]+=6 if short else 7;return ([],None)if short else(copy.deepcopy(rows),None)
   tokens=[(DEADLINE,DEADLINE.set(100)),(c.LAB_LOOKUP_MODE_CONTEXT,c.LAB_LOOKUP_MODE_CONTEXT.set('standard'))]
   try:
    with CaptureRun(org.organization_name,org.ein,'KY'),patch.object(c,'trial_identity',return_value={'origin':'local'}),patch.object(c,'known_names_for_ein',side_effect=lambda ein:[org.organization_name]if c.canonical_ein_digits(ein)==org.ein else []),patch.object(c,'load_ky_snapshot_records',return_value=[('1577',org.organization_name,'2025','1577 Christian Research Institute Inc. 2025')]),patch.object(c,'downloadable_data_info',return_value={'source_url':'https://state.invalid/ky-modeled-snapshot'}),patch.object(c,'fiscal_year_end_for_ein',return_value=(6,30)),patch.object(c,'irs_latest_period',return_value={}),patch.object(c,'identity_fetch',side_effect=fetch),patch.dict(c.TAX_PERIOD_EVIDENCE_CACHE,{},clear=True),patch.dict(c.HI_DOCUMENT_PERIOD_CACHE,{},clear=True),patch.object(c.time,'monotonic',side_effect=lambda:clock[0]),patch.dict(sys.modules,{'rapidocr_onnxruntime':types.SimpleNamespace(RapidOCR=lambda **k:None)}),patch.object(c,'IRS_HEADER_OCR',ocr),patch.object(c,'IRS_HEADER_TITLE_OCR',title):
     # The exact legacy function resolves its globals from the copied scope.
     scope.update({k:getattr(c,k)for k in ['known_names_for_ein','load_ky_snapshot_records','downloadable_data_info','fiscal_year_end_for_ein']})
     result=lookup(org)
   finally:
    for var,token in reversed(tokens):var.reset(token)
   self.assertEqual(len(calls),3,calls)
   if arm=='baseline':self.assertEqual(result.status,'Unable to Confirm');self.assertFalse(hasattr(result,'tax_period_evidence'))
   else:
    self.assertEqual(c.public_status(result),'Current');self.assertEqual(result.tax_period_evidence['period_end'],'2026-06-30');self.assertEqual(result.matched_registry_identifier,'1577')

if __name__=='__main__':unittest.main()
