import sys,unittest,json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class RemainingTests(unittest.TestCase):
 def test_nh_real_wrapped_rows(self):
  rows,_=c.nh_live_pdf_records();rows={r['registry_id']:r for r in rows}
  for key,due in [('14213','5/15/2027'),('5862','11/15/2026')]:
   self.assertEqual(rows[key]['status_code'],'G');self.assertEqual(rows[key]['due_raw'],due)
  for name,ein,expected in [('Firehouse Subs Public Safety Foundation, Inc.','203588745','Current'),('Accion International','132535763','Upcoming Filing')]:
   self.assertEqual(c.search_nh_live_pdf(c.checker.Organization(name,ein)).status,expected)
 def test_wa_waits_for_complete_fields(self):
  page=Mock();full='FEIN Number:\n123456789\nStatus:\nActive\nRenewal Date:\n12/31/2027'
  page.locator.return_value.inner_text.side_effect=['ORGANIZATION SUMMARY','FEIN Number:\n123456789',full]
  with patch.object(c.time,'sleep'):
   self.assertEqual(c.wa_read_completed_detail(page,SimpleNamespace(ein='123456789')),full)
  self.assertEqual(page.locator.return_value.inner_text.call_count,3)
 def test_wa_conflicting_ein_still_rejected(self):
  r=SimpleNamespace(ein='123456789')
  c.wa_apply_detail_master(r,'FEIN Number:\n987654321\nStatus:\nActive\nRenewal Date:\n12/31/2027')
  self.assertEqual(r.status,'Unable to Confirm');self.assertFalse(r.success)
 def test_wa_missing_identity_is_not_conflict_or_negative(self):
  r=SimpleNamespace(ein='123456789');c.wa_apply_detail_master(r,'ORGANIZATION SUMMARY')
  self.assertEqual(r.status,'Unable to Confirm');self.assertIn('did not finish loading',r.raw_status_text)
 def test_scanned_form_requires_identity_and_labeled_fiscal_period(self):
  t='Form PC\n09/01/2020 to 08/31/2021\nReport for the Fiscal Period:\n027670\nAttorney General Account:\n86-0481941\nFederal ID'
  e=c.ma_scanned_form_pc_evidence(t,2021,'027670','860481941');self.assertEqual(e['period_end'],'8/31/2021')
  for text,year,account,ein in [(t,2022,'027670','860481941'),(t,2021,'027671','860481941'),(t,2021,'027670','123456789'),(t.replace('Form PC','Form 10A'),2021,'027670','860481941'),(t.replace('Report for the Fiscal Period','Date received'),2021,'027670','860481941')]:
   self.assertFalse(c.ma_scanned_form_pc_evidence(text,year,account,ein))
 def test_miscellaneous_attachments_cannot_be_selected(self):
  response=Mock();response.url='https://masscharities.my.site.com/aura';response.request.post_data='message='+c.quote(json.dumps({'actions':[{'id':'1','params':{'classname':'AeS_Apex_Controller_Class','method':'get_ALL_FILINGS_ATTACHMENTS_FOR_PUBLICUSERS','params':{'agoNumber':'027670'}}}]}))
  response.json.return_value={'actions':[{'id':'1','state':'SUCCESS','returnValue':{'returnValue':[{'filingYear':'2022','nameforURL':'FY2022 PC - Other/Misc.tiff','url':'ignored'}]}}]}
  ev={};c.ma_capture_completed_response(response,c.checker.Organization('Control','123456789'),ev)
  self.assertFalse(ev['filings']['027670']['empty']);self.assertEqual(ev['filings']['027670']['annual_scans'],[])

if __name__=='__main__':unittest.main()
