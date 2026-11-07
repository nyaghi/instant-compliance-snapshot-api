import sys,unittest,time,hashlib,tempfile,io,copy
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as m
from deployment import state_snapshots as s,ca_accepted_renewal as ca
from testing.test_gates22_23_capture_budget import fixture_image
from pypdf import PdfReader
class Followup(unittest.TestCase):
 def test_tn_transport_and_parser_join(self):
  query={'state':'TN','operation':'detail','identifier':'CO2787'}
  fields={'Name':'CHILDREN INTERNATIONAL','CO Number':'CO2787','Status':'Active','Registration Date':'03/19/1996','Expiration Date':'11/27/2026','Address':'2000 E. RED BRIDGE RD. KANSAS CITY MO 64131','Purpose':'Public charitable purpose. '*150}
  payload={'query':query,'complete':True,'fields':fields}
  clean=m.final_four_clean_evidence(payload,query)
  row=m.tn_charity_detail_evidence(clean['fields'],'CO2787',{'name':fields['Name'],'city':'KANSAS CITY','region':'MO'})
  self.assertEqual(row['purpose'],fields['Purpose']);self.assertEqual(row['identifier'],'CO2787')
  for bad in [fields|{'Purpose':'x'*6001},fields|{'Name':'x'*1501},fields|{'private_field':'x'},fields|{'CO Number':'CO123'}]:
   with self.subTest(bad=list(bad)):
    with self.assertRaises(ValueError):m.final_four_clean_evidence(payload|{'fields':bad},query)
  self.assertEqual(m.final_four_clean_evidence(payload|{'fields':{k:v for k,v in fields.items()if k!='Purpose'}},query)['fields']['Name'],fields['Name'])
 def test_ca_two_originals_through_archive_pdf(self):
  name='LUTHERAN WORLD RELIEF INC.';ein='132574963';ident='078450'
  header='https://ca-rcf.evokeplatform.com/app/publicPortal/charity/fixture'
  renewal='https://ca-rcf.evokeplatform.com/app/publicPortal/requestDetailsRenewal/fixture'
  proof={'ein':ein,'name':name,'registration':ident,'url':renewal}
  run=s.CaptureRun(name,ein,'CA');run.remember_detail(ident,name,header);run.source_detail_hints[ident]['accepted_renewal']=proof
  first=name+' Registration '+ident+' EIN '+ein+' Registered Reporting';second=name+' '+ident+' '+ein+' Renewal Form RRF-1 Accepted'
  raw1=fixture_image(first);raw2=fixture_image(second)
  run.document(header,raw1,'image',first);run.document(renewal,raw2,'image',second)
  run.ca_renewal_image_binding=(hashlib.sha256(raw2).hexdigest(),proof)
  row={'state':'CA','ein':ein,'organization_name':name,'matched_registry_name':name,'matched_registry_identifier':ident,'status':'Upcoming Filing','success':True,'source_url':header}
  paired=ca.pair_originals(run,run.documents,row);self.assertEqual(len(paired),1);self.assertEqual(paired[0][2],'image_pages')
  for changed in [row|{'matched_registry_identifier':'999'},row|{'matched_registry_name':'OTHER'}]:
   self.assertEqual(ca.pair_originals(run,run.documents,changed),run.documents)
  with tempfile.TemporaryDirectory()as folder:
   store=s.SQLiteStore(Path(folder)/'ca.sqlite')
   result=s.persist_worker_result(None,run.finish(row),{'state':'CA','payload':{'ein':ein}},store=store)
   ref=result.get('evidence_url') or result.get('snapshot_url');self.assertTrue(ref,result)
   pdf=s.saved_pdf(ref.split('/')[-1][:-4],store)[1]
   self.assertEqual(len(PdfReader(io.BytesIO(pdf)).pages),2)
 def test_mi_alias_opens_owned_detail_and_rejects_foreign_ein(self):
  from contextlib import ExitStack
  org=m.checker.Organization('Lutheran World Relief','132574963')
  page=Mock();page._cc_mi_lookup_deadline=time.perf_counter()+30;page._cc_mi_search_progress=None
  page.expect_navigation.return_value.__enter__=Mock();page.expect_navigation.return_value.__exit__=Mock(return_value=False)
  frame=Mock();detail=Mock();link=Mock();href="javascript:__doPostBack('ctl00$MainContent$GridView1$ctl03$btnOrgName','')"
  link.get_attribute.return_value=href
  values={'lblLegalName':'CORUS INTERNATIONAL INC','lblEIN':'84-3236198','lblFileNo':'63746'}
  detail.locator.side_effect=lambda selector:Mock(inner_text=Mock(return_value=values[selector.split('_')[-1]]))
  module=Mock(MI_SEARCH_URL='https://www.ag.state.mi.us/CharitableTrust/')
  module.body_text.side_effect=lambda f,**kw:'1 record(s) found CORUS INTERNATIONAL INC' if f is frame else 'CORUS INTERNATIONAL INC 84-3236198'
  module.find_results_frame.return_value=frame;module.extract_legal_name.return_value='CORUS INTERNATIONAL INC'
  module.find_detail_frame.side_effect=lambda p:detail if module.click_result_link.called else None
  with ExitStack()as stack:
   for name,value in [('state_extension_module',module),('patch_mi_module_for_fast_lookups',None),('organization_match_target_variants',['Lutheran World Relief','Corus International']),('mi_name_fallback_queries',['Corus International']),('mi_choose_result_link',(1,'CORUS INTERNATIONAL INC',link,href)),('mi_name_fallback_candidate_is_safe',True),('target_name_score',500)]:
    stack.enter_context(patch.object(m,name,return_value=value))
   stack.enter_context(patch.object(m.time,'sleep'))
   result=m.search_mi_name_fallback(page,org)
  module.click_result_link.assert_called_once_with(frame,link,href)
  link.click.assert_not_called()
  self.assertTrue(result.success,result.source_note)
  self.assertEqual(result.reason_code,'MI_COMPLETED_EIN_AND_NAME_SEARCH')
  self.assertTrue(any('labeled EIN differs' in x for x in result.source_attempts))

 def test_ky_generated_name_retains_owned_original_context(self):
  from types import SimpleNamespace
  original=m.checker.Organization('Food for the Poor Inc.','592174510')
  org=m.org_with_name(original,'Food for the Poor')
  run=s.CaptureRun(original.organization_name,original.ein,'KY')
  tokens=[(s.CURRENT,s.CURRENT.set(run)),(s.DEADLINE,s.DEADLINE.set(time.monotonic()+300)),(m.LAB_LOOKUP_MODE_CONTEXT,m.LAB_LOOKUP_MODE_CONTEXT.set('standard'))]
  try:
   with patch.object(m,'trial_identity',return_value=True),patch.object(m,'irs_period_for_label',return_value={})as read:
    m.ky_filed_period_evidence(org,2025)
    self.assertTrue(read.call_args.kwargs.get('ky_cover_scan'))
    self.assertLessEqual(read.call_args.kwargs['scanned_deadline']-read.call_args.args[-1],14.01)
    org.original_organization_name='Different Organization'
    m.ky_filed_period_evidence(org,2025);self.assertEqual(read.call_args.kwargs,{})
  finally:
   for var,token in reversed(tokens):var.reset(token)

if __name__=='__main__':unittest.main(verbosity=2)

