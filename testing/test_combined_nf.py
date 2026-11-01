import copy,io,json,socket,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image,ImageDraw
from pypdf import PdfReader
from reportlab.pdfgen import canvas
import registry_snapshot_server as m
from deployment import short_alias_identity as alias,dc_boss_evidence as boss,dc_period_reconciliation as period
from deployment import oh_detail_evidence as oh,ok_certificate_evidence as ok,state_snapshots as snapshots

ROOT=Path(__file__).resolve().parents[1]
F=json.loads((ROOT/'testing/fixtures/combined-nf-retained.json').read_text(encoding='utf-8'))

class CombinedNF(unittest.TestCase):
 def setUp(self):
  p=patch.object(socket,'create_connection',side_effect=AssertionError('No external requests in local controls'));p.start();self.addCleanup(p.stop)
  token=m.REVIEWED_NAME_CONTEXT.set({'410832903':['NAF']});self.addCleanup(m.REVIEWED_NAME_CONTEXT.reset,token)
  token=m.USER_IDENTITY_CONTEXT.set({});self.addCleanup(m.USER_IDENTITY_CONTEXT.reset,token)
  self.org=SimpleNamespace(organization_name='National Ataxia Foundation Inc.',ein='410832903')
 def test_actual_five_wrong_alias_results_require_review_without_changing_record_fields(self):
  for row in F['alias_rows']:
   r=SimpleNamespace(**copy.deepcopy(row));identity=(r.matched_registry_name,r.matched_registry_identifier)
   alias.apply(r,self.org,'',m)
   self.assertFalse(r.success);self.assertEqual(r.status,'Needs Review')
   self.assertEqual(identity,(r.matched_registry_name,r.matched_registry_identifier))
   self.assertEqual(r._cc_identity_review['records'][0]['status'],row['status'])
   self.assertFalse(r._cc_identity_review['search_complete'])
 def test_thirty_ein_confirmed_and_corroborated_acronyms_and_other_states_are_unchanged(self):
  for i in range(30):
   for proof in [{'verified_registry_ein':'410832903'},{'address_evidence':{'decision':'corroborated'}}]:
    r=SimpleNamespace(**{**copy.deepcopy(F['alias_rows'][i%5]),**proof});before=copy.deepcopy(vars(r));alias.apply(r,self.org,'',m);self.assertEqual(vars(r),before)
   r=SimpleNamespace(**{**copy.deepcopy(F['alias_rows'][i%5]),'state':['AL','NC','NV','TN','GA','IL','AR','ND','CA','OH'][i%10]});before=copy.deepcopy(vars(r));alias.apply(r,self.org,'',m);self.assertEqual(vars(r),before)
 def test_unverified_full_names_and_entered_short_names_keep_existing_rules(self):
  r=SimpleNamespace(**{**copy.deepcopy(F['alias_rows'][0]),'matched_registry_name':self.org.organization_name});before=copy.deepcopy(vars(r));alias.apply(r,self.org,'',m);self.assertEqual(vars(r),before)
  r=SimpleNamespace(**copy.deepcopy(F['alias_rows'][0]));org=SimpleNamespace(organization_name='NAF',ein='410832903');before=copy.deepcopy(vars(r));alias.apply(r,org,'',m);self.assertEqual(vars(r),before)
 def test_different_ein_never_creates_an_overridable_review(self):
  r=SimpleNamespace(**{**copy.deepcopy(F['alias_rows'][0]),'verified_registry_ein':'111111111'});alias.apply(r,self.org,'',m);self.assertFalse(r.success);self.assertEqual(r.reason_code,'SHORT_ALIAS_EIN_CONFLICT');self.assertFalse(hasattr(r,'_cc_identity_review'))
 def test_me_active_enrichment_cannot_erase_conflict_or_existing_review(self):
  for extra in [{'status_reason':'REGISTRY_ADDRESS_CONFLICT'},{'_cc_identity_review':{'records':[{}]}}]:
   r=SimpleNamespace(status='Unable to Confirm',raw_status_text='Identity not confirmed',source_note='Review identity',error='',success=False,**extra);before=copy.deepcopy(vars(r))
   m.enrich_me_result_from_body(r,'License Number: CO9076 Status: Active Expiration Date: 11/30/2026');self.assertEqual(vars(r),before)
 def test_me_conflict_plus_html_detail_stays_reviewable_without_becoming_current(self):
  row=next(x for x in F['alias_rows'] if x['state']=='ME');r=SimpleNamespace(**copy.deepcopy(row));r.status='Unable to Confirm';r.status_reason='REGISTRY_ADDRESS_CONFLICT';r.success=False
  body='<html><body><h1>NATIONAL ACADEMY FOUNDATION</h1><table><tr><td>License Number:</td><td>CO9076</td></tr><tr><td>Status:</td><td>Active</td></tr><tr><td>Expiration Date:</td><td>11/30/2026</td></tr></table></body></html>'
  m.enrich_me_result_from_body(r,body);self.assertEqual(r.status,'Unable to Confirm');alias.apply(r,self.org,body,m);self.assertEqual(r.status,'Needs Review');self.assertFalse(r.success);self.assertEqual(r._cc_identity_review['records'][0]['expiration'],'11/30/2026')
 def test_five_signed_candidate_statuses_ownership_tampering_and_decisions(self):
  with patch.object(m,'APP_VERSION','2026.09.29.2NF-staging'),patch.object(m,'NY_CONNECTOR_SIGNING_KEY','local-only-key-'*4),patch.object(m,'trial_identity',return_value=None):
   for row in F['alias_rows']:
    r=SimpleNamespace(**copy.deepcopy(row));alias.apply(r,self.org,'',m)
    data={**row,'status':'Needs Review','success':False};m.attach_identity_review(data,r._cc_identity_review)
    view=data['identity_review'];record=m.identity_review_unpack(view['token'],'local@example.test','device-a')
    self.assertEqual(m.identity_review_state_status(row['state'],record['records'][0]),row['status'])
    self.assertEqual(record['records'][0]['identifier'],row['matched_registry_identifier'])
    with self.assertRaises(ValueError):m.identity_review_unpack(view['token'][:-1]+('a'if view['token'][-1]!='a'else'b'),'local@example.test','device-a')
    # Real token + real decision function, on local fixture tokens only.
    payload={'token':view['token'],'state':row['state'],'ein':row['ein'],'candidate_id':record['records'][0]['id'],'action':'accept'}
    if row['state']=='KY':
     with patch.object(m,'run_state_lookup',return_value=copy.deepcopy(row)) as call:accepted=m.resolve_identity_review(payload,'local@example.test','device-a');self.assertEqual(call.call_count,1)
    else:accepted=m.resolve_identity_review(payload,'local@example.test','device-a')
    self.assertEqual(accepted['status'],row['status']);self.assertEqual(accepted['matched_registry_identifier'],row['matched_registry_identifier'])
    token=accepted['identity_review']['token']
    with self.assertRaises(ValueError):m.identity_review_unpack(token,'other@example.test','device-b')
    with patch.object(m,'run_state_lookup',return_value={'state':row['state'],'ein':row['ein'],'status':'Unable to Confirm','success':False,'comments':'Incomplete confirmation','organization_name':self.org.organization_name}):
     rejected=m.resolve_identity_review({**payload,'action':'reject'},'local@example.test','device-a')
    self.assertNotEqual(rejected['status'],'Current')
 def test_ky_explicit_signed_row_decision_is_not_sent_back_into_review(self):
  row=next(r for r in F['alias_rows'] if r['state']=='KY');r=SimpleNamespace(**copy.deepcopy(row))
  token=m.USER_IDENTITY_CONTEXT.set({'ein':m.canonical_ein_digits(r.ein),'state':'KY','accepted':{'name':r.matched_registry_name,'identifier':str(r.matched_registry_identifier)}})
  try:before=copy.deepcopy(vars(r));alias.apply(r,self.org,'',m);self.assertEqual(vars(r),before)
  finally:m.USER_IDENTITY_CONTEXT.reset(token)
 def test_wv_complete_short_record_keeps_candidate_and_original_fields(self):
  fix=ROOT/'testing/fixtures/wv-direct-public';form=(fix/'search.html').read_text(encoding='utf-8');rows=(fix/'comic-search-all.html').read_text(encoding='utf-8').replace('Comic Relief, Inc.','NAF');detail=(fix/'comic-detail.html').read_text(encoding='utf-8').replace('Comic Relief, Inc.','NAF')
  def read(transport,path,fields=None):
   text=detail if path=='CharitiesInformation' else rows if fields else form;transport.body=transport.text(text);return text
  with patch.object(m.WestVirginiaPublicLookup,'read',read),patch.object(m,'reconciled_registry_address',return_value={'decision':'conflict','registry_location':'New York, NY','ein_linked_location':'Minneapolis, MN'}):
   value=m.search_wv_public_details(m.checker.Organization(self.org.organization_name,self.org.ein))
  self.assertIsNotNone(value);r,body=value;self.assertEqual(r.reason_code,'WV_SHORT_NAME_IDENTITY_UNCONFIRMED');self.assertFalse(r.success);self.assertEqual(r.matched_registry_identifier,'5533');self.assertTrue(r._cc_identity_review['records']);self.assertIn('NAF',body)
 def test_actual_dc_details_accept_only_proven_separate_period_date(self):
  for case in F['dc']:
   result=copy.deepcopy(case['result']);request=result['_worker_desktop_evidence'];request.update(issued_at=time.time()-1,expires_at=time.time()+100,prior_renewal_date_type='current_effective_date');source=case['source']
   fields=boss.fields(source['url'],source['text'],request);self.assertIsNotNone(fields)
   legacy={k:v for k,v in request.items() if k!='prior_renewal_date_type'};self.assertIsNone(boss.fields(source['url'],source['text'],legacy))
   payload={'request':request,'url':source['url'],'public_text':source['text'],'source_fields':fields,'captured_at':time.time()}
   update=period.completed_update(result,payload)
   self.assertEqual(update['renewal_date'],result['renewal_date']);self.assertEqual(update['renewal_filing_value'],result['renewal_filing_value']);self.assertEqual(update['renewal_filing_source_url'],result['renewal_filing_source_url']);self.assertEqual(update['computed_due_date'],request['expiration']);self.assertEqual(update['status'],result['status'])
   for key,value in [('License Number','999999999'),('Licensee','Wrong Organization'),('License Activity','Charitable Exempt'),('License Status','Revoked'),('Issue Date','01/01/2035'),('Expiration Date','01/01/2025')]:
    text=source['text'].replace(fields[key],value);self.assertIsNone(boss.fields(source['url'],text,request))
 def test_oh_actual_bound_detail_precedes_newer_grid_and_wrong_records_do_not(self):
  run=SimpleNamespace(state='OH',ein='860481941',visual_adapter_facts=[]);row={'matched_registry_identifier':'221678'}
  text='Organization Name Make-A-Wish Foundation of America Employer Identification Number (EIN): 86-0481941 Fiscal Year End August Registration Status Registered'
  detail=('https://charitableregistration.ohioago.gov/Charities/OrganizationDetails?Id=221678',b'original-detail','image',text,1,'Original detail')
  grid=('https://charitableregistration.ohioago.gov/Charities/ResearchCharities',b'original-grid','image','86-0481941',2,'Original grid')
  self.assertEqual(oh.select(run,[grid,detail],row),[detail,grid])
  for bad in [detail[:3]+(text.replace('86-0481941','11-1111111'),)+detail[4:],('https://other.example/detail',)+detail[1:],detail[:3]+('Server Error Runtime Error',)+detail[4:]]:
   self.assertEqual(oh.select(run,[grid,bad],row),[grid,bad])
 def test_available_ok_certificate_is_bound_and_attached_as_original_page_two(self):
  out=io.BytesIO();p=canvas.Canvas(out);p.drawString(20,800,'LOCAL MODELED FIXTURE - NOT STATE EVIDENCE');p.drawString(20,770,'CERTIFICATE OF REGISTRATION');p.drawString(20,740,'Registration of EXAMPLE FOUNDATION has been filed');p.save();certificate=out.getvalue()
  run=SimpleNamespace(state='OK',visual_adapter_facts=[]);url='https://www.sos.ok.gov/corp/charityDetail.aspx?id=12345';ok.retain_certificate(run,url,'999000111','EXAMPLE FOUNDATION',certificate)
  raw=io.BytesIO();Image.new('RGB',(800,600),'white').save(raw,format='PNG')
  original=(url,raw.getvalue(),'image','EXAMPLE FOUNDATION 12345 999000111',time.time(),'LOCAL MODELED ORIGINAL')
  row={'success':True,'status':'Current','matched_registry_identifier':'12345','matched_registry_name':'EXAMPLE FOUNDATION','raw_status_text':'999000111 Renewal Registration'}
  joined=ok.pair_selected_certificate(run,[original],row);self.assertEqual(joined[0][2],'source_pdf');pdf=PdfReader(io.BytesIO(joined[0][1]));self.assertEqual(len(pdf.pages),2);self.assertEqual(pdf.pages[1].extract_text(),PdfReader(io.BytesIO(certificate)).pages[0].extract_text())
  for change in [{'matched_registry_identifier':'54321'},{'matched_registry_name':'OTHER FOUNDATION'},{'raw_status_text':'222333444 Renewal'},{'success':False},{'status':'Unable to Confirm'}]:self.assertEqual(ok.pair_selected_certificate(run,[original],{**row,**change}),[original])

if __name__=='__main__':unittest.main()
