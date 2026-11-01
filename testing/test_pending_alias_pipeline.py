"""Serialize real retained alias results through normalization, review and capture admission."""
import copy,hashlib,io,json,socket,time,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw
import registry_snapshot_server as m
from deployment import short_alias_identity as a,state_snapshots as ss,source_visual_adapters as visuals
F=json.loads((Path(__file__).parent/'fixtures/combined-nf-retained.json').read_text(encoding='utf-8'))

class PendingAliasPipeline(unittest.TestCase):
 def setUp(self):
  p=patch.object(socket,'create_connection',side_effect=AssertionError('No live source requests'));p.start();self.addCleanup(p.stop)
  self.org=m.checker.Organization('National Ataxia Foundation Inc.','410832903')
  token=m.REVIEWED_NAME_CONTEXT.set({'410832903':['NAF']});self.addCleanup(m.REVIEWED_NAME_CONTEXT.reset,token)
  token=m.USER_IDENTITY_CONTEXT.set({});self.addCleanup(m.USER_IDENTITY_CONTEXT.reset,token)
 def public(self,state):
  row=copy.deepcopy(next(x for x in F['alias_rows']if x['state']==state));r=m.checker.StateResult(self.org.organization_name,self.org.ein,state,row['status'],row['source_url'])
  for k,v in row.items():setattr(r,k,v)
  body=''
  if state=='ME':
   r.status='Unable to Confirm';r.success=False;r.status_reason='REGISTRY_ADDRESS_CONFLICT'
   body='License Number: CO9076 Status: Active Expiration Date: 11/30/2026 NAF NATIONAL ACADEMY FOUNDATION'
  with patch.object(m,'APP_VERSION','2026.09.29.2-performance-lab'),patch.object(m,'performance_origin_enabled',return_value=True),patch.object(m,'trial_identity',return_value=None),patch.dict(m.os.environ,{'CE_AURORA_STAGING_BRIDGE':'1','CE_FINAL_FOUR_CHILD':'1'}):
   return m.response_data_for_lookup(r,body,self.org,self.org.organization_name,self.org.ein,state,time.perf_counter())
 def test_real_five_results_keep_bound_candidates_through_public_serialization(self):
  for state in ['ME','NH','KY','OK','SC']:
   data=self.public(state);self.assertEqual(data['status'],'Unable to Confirm',state);self.assertFalse(data['success']);ctx=data['_worker_identity_review'];self.assertEqual(len(ctx['records']),1);self.assertEqual(data['matched_registry_identifier'],ctx['records'][0]['identifier']);self.assertEqual(data['matched_registry_name'],ctx['records'][0]['name'])
 def test_me_sc_visual_admission_uses_candidate_copy_and_preserves_public_uncertainty(self):
  for state in ['ME','SC']:
   data=self.public(state);before=copy.deepcopy(data);candidate=a.visual_result(data);self.assertIsNot(candidate,data);self.assertTrue(candidate['success']);self.assertEqual(candidate['status'],data['_worker_identity_review']['records'][0]['status']);self.assertEqual(data,before)
   with patch.object(visuals,'capture_selected_source')as selected,patch.object(visuals,'capture_negative_search'):
    visuals.capture_result_visuals(m,data,ss.CaptureRun(self.org.organization_name,self.org.ein,state),time.monotonic()+30)
   self.assertEqual(selected.call_args.args[1],candidate);self.assertEqual(data,before)
 def test_wv_normalization_and_visual_admission_keep_exact_pending_row(self):
  r=m.checker.StateResult(self.org.organization_name,self.org.ein,'WV','Needs Review',m.WV_SEARCH_URL);r.reason_code='WV_SHORT_NAME_IDENTITY_UNCONFIRMED';r.success=False;r.matched_registry_name='NAF';r.matched_registry_identifier='C230307021959';r.raw_status_text='Status: Active | Expiration Date: 03/07/2027'
  r._cc_identity_review={'records':[{'name':'NAF','identifier':r.matched_registry_identifier,'url':m.WV_SEARCH_URL,'status':'Current','raw_status':'Active','expiration':'03/07/2027','_identity_outcome':'possible'}],'search_complete':False}
  m.normalize_registry_match_fields(r,self.org);self.assertEqual(r.matched_registry_identifier,'C230307021959')
  data={'state':'WV','ein':self.org.ein,'status':'Unable to Confirm','success':False,'reason_code':r.reason_code,'matched_registry_name':r.matched_registry_name,'matched_registry_identifier':r.matched_registry_identifier,'source_url':m.WV_SEARCH_URL,'_worker_identity_review':r._cc_identity_review};self.assertTrue(a.visual_result(data)['success']);self.assertFalse(data['success'])
 def test_changed_or_incomplete_candidates_cannot_get_visual_admission(self):
  for state in ['ME','SC']:
   data=self.public(state)
   for key,value in [('identifier','other'),('name','different'),('status','Unable to Confirm'),('url','https://other.invalid'),('_identity_outcome','rejected')]:
    bad=copy.deepcopy(data);bad['_worker_identity_review']['records'][0][key]=value;self.assertIs(a.visual_result(bad),bad)
   bad=copy.deepcopy(data);bad['_worker_identity_review']['records']*=2;self.assertIs(a.visual_result(bad),bad)
 def test_thirty_unrelated_and_incomplete_capture_paths_are_unchanged(self):
  states=['AK','AL','AR','CA','CO','CT','DC','FL','GA','HI','IL','KS','KY','LA','MA','MD','MI','MN','MS','NC','ND','NH','NJ','NM','NV','NY','OH','OK','OR','PA']
  for state in states:
   for status in ['Current','Not Registered','Unable to Confirm']:
    data={'state':state,'ein':self.org.ein,'status':status,'success':status!='Unable to Confirm','matched_registry_name':'EXAMPLE FOUNDATION','matched_registry_identifier':'123'};self.assertIs(a.visual_result(data),data)
  for state in ['ME','SC','WV']:
   data={'state':state,'ein':self.org.ein,'status':'Unable to Confirm','success':False,'reason_code':'PORTAL_ERROR'};self.assertIs(a.visual_result(data),data)
 def test_ok_pending_identity_keeps_original_certificate_without_confirming_status(self):
  import re
  from reportlab.pdfgen import canvas
  from pypdf import PdfReader
  from deployment.ok_certificate_evidence import retain_certificate
  data=self.public('OK');before=copy.deepcopy(data);candidate=data['_worker_identity_review']['records'][0];run=ss.CaptureRun(self.org.organization_name,self.org.ein,'OK')
  document=re.search(r'(?<!\d)\d{8,}(?!\d)',candidate['raw_status'])[0];detail_url='https://www.sos.ok.gov/corp/charityDetail.aspx?id='+candidate['identifier']
  out=io.BytesIO();p=canvas.Canvas(out);p.drawString(20,800,'LOCAL MODELED FIXTURE');p.drawString(20,770,'CERTIFICATE OF REGISTRATION');p.drawString(20,740,'Registration of NAF has been filed');p.save();retain_certificate(run,detail_url,document,'NAF',out.getvalue())
  image=Image.new('RGB',(800,600),'white');ImageDraw.Draw(image).text((20,20),'LOCAL MODELED SOURCE NAF '+candidate['identifier']+' '+document,fill='black');out=io.BytesIO();image.save(out,format='PNG');run.document(detail_url,out.getvalue(),'image','NAF '+candidate['identifier']+' '+document)
  value=run.finish(data);self.assertEqual(data,before);self.assertEqual(value['status'],'Unable to Confirm');self.assertFalse(value['success']);assets=value['_worker_source_archives'];self.assertTrue(any(x['kind']=='source_pdf' for x in assets))
  import base64
  self.assertEqual(len(PdfReader(io.BytesIO(base64.b64decode(next(x['content']for x in assets if x['kind']=='source_pdf')))).pages),2)
 def test_pending_me_sc_originals_survive_actual_archive_assembly_without_status_acceptance(self):
  for state in ['ME','SC']:
   data=self.public(state);candidate=data['_worker_identity_review']['records'][0];run=ss.CaptureRun(self.org.organization_name,self.org.ein,state)
   image=Image.new('RGB',(800,600),'white');ImageDraw.Draw(image).text((20,20),'LOCAL MODELED SOURCE PIXELS '+candidate['name']+' '+candidate['identifier'],fill='black');stream=io.BytesIO();image.save(stream,format='PNG');raw=stream.getvalue()
   if state=='SC':run.sc_selected_image_bindings={hashlib.sha256(raw).hexdigest():(candidate['name'],candidate['identifier'])}
   run.document(data['source_url'],raw,'image','LOCAL MODELED SOURCE '+candidate['name']+' '+candidate['identifier'])
   value=run.finish(data);self.assertEqual(value['status'],'Unable to Confirm');self.assertFalse(value['success']);self.assertTrue(value.get('_worker_source_archives'));self.assertTrue(all(x['identifier']==candidate['identifier']for x in value['_worker_source_archives']))

if __name__=='__main__':unittest.main()
