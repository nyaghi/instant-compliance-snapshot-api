import sys,time,json,copy,io,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from types import SimpleNamespace as NS
D=Path(__file__).resolve().parent/'fixtures/gates29-30'
W=Path(__file__).resolve().parents[1];sys.path.insert(0,str(W))
import registry_snapshot_server as m
from deployment import wv_legal_identity as wv,wa_conflict_review as wa,mi_alias_identity as mi,state_snapshots as s,identity_evidence
from deployment.dc_transport_diagnostics import failure
from testing.test_gates22_23_capture_budget import fixture_image
from deployment.search_history import SourceQueryReceipt
from pypdf import PdfReader

class Joined(unittest.TestCase):
 def test_tn_historical_visible_purpose_and_office_join(self):
  org=m.checker.Organization('Plan International USA Inc.','135661832');alias="FOSTER PARENTS' PLAN FOR SPANISH CHILDREN, INC."
  fields={'Name':alias,'CO Number':'CO16','Status':'Expired','Registration Date':'11/26/2008','Expiration Date':'12/31/2025','Address':'275 PROMENADE STREET, SUITE 225 PROVIDENCE RI 02908','Purpose':'Plan International USA, Inc. is a girls rights organization.'}
  query={'name':alias,'city':'PROVIDENCE','region':'RI','aliases':[]}
  reviewed=['PLAN INTERNATIONAL USA, INC.','FOSTER PARENTS PLAN, INC.']
  office={'address_role':'organization','ein':org.ein,'street':'275 PROMENADE STREET SUITE 225','state':'RI','postal_code':'02908','names':[org.organization_name]}
  with patch.object(m,'known_names_for_ein',side_effect=lambda e:reviewed if m.canonical_ein_digits(e)==org.ein else []),patch.object(m,'licensed_charity_foreign_ein',return_value={}),patch.object(m,'identity_source_result',return_value={'organization_records':[office]}):
   row=m.tn_charity_detail_evidence(fields,'CO16',query)
   self.assertEqual(m.licensed_charity_identity(org,row,'TN',time.monotonic()+8),'accepted',row)
   self.assertEqual(row['status'],'Delinquent')
   missing=m.tn_charity_detail_evidence(fields|{'Purpose':''},'CO16',query)
   self.assertEqual(m.licensed_charity_identity(org,missing,'TN',time.monotonic()+8),'possible')
   with patch.object(m,'licensed_charity_foreign_ein',return_value={'decision':'different_ein'}):
    row=m.tn_charity_detail_evidence(fields,'CO16',query);self.assertEqual(m.licensed_charity_identity(org,row,'TN',time.monotonic()+8),'rejected')
 def test_ct_dotted_legal_name_is_not_credential(self):
  org=m.checker.Organization('Water.org Inc.','582060131')
  row='<tr><td><b class="forge-typography--headline6">WATER.ORG, INC.</b><b>Credential</b><p>CHR.0051375</p><b>Credential Description</b><p>PUBLIC CHARITY</p><b>Status</b><p>ACTIVE</p><b>Status Reason</b><p>CURRENT</p></td></tr>'
  with patch.object(m,'known_names_for_ein',return_value=['WATER.ORG, INC.']),patch.object(m,'ct_direct_detail_text',return_value='Name and Address WATER.ORG, INC. Credential CHR.0051375 Expiration Date 11/30/2027'):
   result,score=m.ct_direct_result_from_row(org,row,m.organization_match_target_variants(org.organization_name,org.ein),'https://www.elicense.ct.gov/')
   self.assertEqual(result.matched_registry_identifier,'CHR.0051375');self.assertEqual(m.public_status(result),'Current')
 def test_mi_legal_alias_requires_its_labeled_ein(self):
  org=m.checker.Organization('Lutheran World Relief','132574963')
  for value,outcome in [('13-2574963','accepted'),('12-3456789','rejected'),('','possible'),('bad123','possible')]:
   data={'lblLegalName':'CORUS INTERNATIONAL INC','lblEIN':value,'lblFileNo':'12345'}
   frame=Mock();frame.locator.side_effect=lambda selector:NS(inner_text=lambda **kw:data[selector.split('_')[-1]])
   self.assertEqual(mi.detail_identity(m,org,frame,'Corus International Inc')[0],outcome)
  self.assertTrue(mi.materially_different(m,org.organization_name,'Corus International'))
  self.assertFalse(mi.materially_different(m,org.organization_name,'Lutheran World Relief, Inc.'))
 def test_wv_actual_legal_dba_office_beats_wrong_short_hit(self):
  source=json.loads((D/'WV-OFFICIAL-SOURCE.json').read_text());org=m.checker.Organization('World Relief','236393344')
  rows=[(r['target'],*r['values'],[]) for r in source['rows']]
  class Lookup:
   def detail(self,target,identifier):return source['details'][identifier]
  office={'address_role':'organization','ein':org.ein,'street':'7 EAST BALTIMORE STREET','state':'MD','postal_code':'21202','names':['WORLD RELIEF CORPORATION OF NATIONAL ASSOCIATION OF EVANGELICALS','World Relief']}
  with patch.object(m,'known_names_for_ein',side_effect=lambda e:[rows[1][2]] if m.canonical_ein_digits(e)==org.ein else []),patch.object(m,'identity_source_result',return_value={'organization_records':[office]}):
   selected=wv.choose(m,org,rows[0],rows,Lookup(),time.perf_counter()+16)
   self.assertIsNotNone(selected);self.assertEqual(selected[0][1],'2808');self.assertIn('7 East Baltimore',selected[1])
   with patch.object(m,'identity_source_result',return_value={'organization_records':[office|{'ein':'132574963'}]}):
    self.assertIsNone(wv.choose(m,org,rows[0],rows,Lookup(),time.perf_counter()+16))
   source['details']['2808']=source['details']['2808'].replace('DBA\nName\nWorld Relief','DBA\nName\nDifferent Organization')
   self.assertIsNone(wv.choose(m,org,rows[0],rows,Lookup(),time.perf_counter()+16))
 def test_wa_source_discrepancy_review_original_accept_reject_undo(self):
  name='Human Appeal Inc.';ein='872410117';foreign='872610117';url='https://ccfs.sos.wa.gov/#/cftSearch'
  body='ORGANIZATION INFORMATION\nOrganization Name:\nHUMAN APPEAL INC\nRegistration Number:\n2010658\nFEIN Number:\n872610117\nStatus:\nActive\nRenewal Date:\n11/30/2026\nStreet Address:\n26050 ACERO, MISSION VIEJO, CA, 92691-2768\nMailing Address:\nN/A\nCONTACT INFORMATION'
  module=m.load_wa_nm_module()
  result=module.SearchResult(organization_name=name,ein=ein,state='WA',status=module.STATUS_UNKNOWN,raw_status_text='',source_url=url,source_note='',matched_registry_name='')
  result._wa_name_conflict={'FEINNumber':foreign,'EntityName':'HUMAN APPEAL INC'}
  office={'address_role':'organization','ein':ein,'street':'26050 ACERO SUITE 415','state':'CA','postal_code':'92691','names':['HUMAN APPEAL INC']}
  with patch.object(m,'identity_source_result',return_value={'organization_records':[office]}):
   result=m.wa_apply_detail_master(result,body)
  self.assertTrue(getattr(result,'_cc_identity_review',{}),vars(result))
  row=result._cc_identity_review['records'][0];self.assertTrue(wa.allowed(row,name,ein),row)
  for changed in [row|{'ein':'111111111'},row|{'name':'Another Organization'},row|{'identifier':'999'},row|{'wa_ein_conflict':{}}]:self.assertFalse(wa.allowed(changed,name,ein))
  copied=m.copy_external_result(m.checker.Organization(name,ein),'WA',result)
  run=s.CaptureRun(name,ein,'WA');run.remember_detail('2010658','HUMAN APPEAL INC',url)
  SourceQueryReceipt(run,{'state':'WA','operation':'search','ein':ein,'url':url,'source_kind':'state_portal','filter_label':'Name'}).complete(1)
  run.document(url,fixture_image(body),'image',body)
  public={**m.checker.asdict(copied),'status':m.public_status(copied),'_worker_identity_review':result._cc_identity_review,'comments':result.source_note}
  with tempfile.TemporaryDirectory()as folder:
   store=s.SQLiteStore(Path(folder)/'wa.sqlite')
   with patch.object(s,'STORE',store),patch.object(m,'APP_VERSION','offline-staging'),patch.object(m,'trial_identity',return_value=False),patch.object(m,'NY_CONNECTOR_SIGNING_KEY','fixture-signing-'*4):
    public=s.persist_worker_result(None,run.finish(public),{'state':'WA','payload':{'ein':ein}},store=store)
    m.attach_identity_review(public,public['_worker_identity_review']);public=identity_evidence.bind(m,public)
    card=public['identity_review']['candidates'][0];ref=card['evidence_url'];self.assertTrue(ref)
    self.assertEqual(len(PdfReader(io.BytesIO(s.saved_pdf(ref.split('/')[-1][:-4],store)[1])).pages),1)
    def decide(data,action):return m.resolve_identity_review({'token':data['identity_review']['token'],'ein':ein,'state':'WA','candidate_id':card['id'],'action':action},'qa@example.test','fixture')
    accepted=decide(public,'accept');self.assertEqual(accepted['status'],row['status']);self.assertEqual(accepted['evidence_url'],ref);self.assertEqual(accepted['ein'],ein)
    rejected=decide(accepted,'reject');self.assertNotEqual(rejected.get('evidence_url'),ref);self.assertEqual(rejected['status'],'Not Registered')
    undone=decide(rejected,'clear');self.assertIn(undone['status'],['Review Required','Review required','Unable to Confirm','Needs Review'])
 def test_dc_failure_diagnostics_are_sanitized(self):
  def _read_status():raise TimeoutError('secret-cookie-do-not-log')
  try:_read_status()
  except Exception as exc:data=failure(exc,15,30,1)
  self.assertEqual(data['observed_phase'],'response_headers');self.assertNotIn('secret-cookie',json.dumps(data))
  self.assertEqual(failure(TimeoutError(),15,-1,2)['remaining_seconds'],0)

if __name__=='__main__':unittest.main(verbosity=2)
