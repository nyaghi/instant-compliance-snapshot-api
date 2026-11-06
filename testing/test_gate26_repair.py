import json,unittest,types,time,copy
from pathlib import Path
from unittest.mock import patch
import registry_snapshot_server as m
from deployment import dc_native_capture as dc,dc_boss_evidence as boss,dc_period_reconciliation as period
F=Path(__file__).parent/'fixtures/gate26'
class Repair(unittest.TestCase):
 def test_wa_actual_fundraiser_closed_does_not_override_active_charity(self):
  body=json.loads((F/'WA-OFFICIAL-DETAIL.json').read_text(encoding='utf-8'))['text']
  result=types.SimpleNamespace(ein='930792021');m.wa_apply_detail_master(result,body)
  self.assertEqual(result.status,'Upcoming Filing');self.assertEqual(result.matched_registry_identifier,'1122481')
  self.assertEqual(result.verified_registry_ein,'930792021')
 def test_wa_terminal_optional_pending_identity_controls(self):
  for status,optional,expected in [('Closed','', 'Closed / Withdrawn / Canceled'),('Involuntarily Closed','','Closed / Withdrawn / Canceled'),('Revoked','','Closed / Withdrawn / Canceled'),('Pending','','Pending'),('Active','Yes','Exempt'),('Active','','Current')]:
   with self.subTest(status=status,optional=optional):
    result=types.SimpleNamespace(ein='123456789');body=f'FEIN Number:\n123456789\nRegistration Number:\n1111111\nStatus:\n{status}\nRenewal Date:\n11/30/2030\nIs Optional Charities?:\n{optional}\nCOMMERCIAL FUNDRAISER\nOther Fundraiser (CLOSED)'
    m.wa_apply_detail_master(result,body);self.assertEqual(result.status,expected)
  result=types.SimpleNamespace(ein='123456789');m.wa_apply_detail_master(result,body.replace('123456789','987654321'));self.assertFalse(result.success)
 def test_dc_undated_admission_and_bound_original_fields(self):
  url="https://maps2.dcgis.dc.gov/dcgis/rest/services/FEEDS/DCRA/FeatureServer/0/query?where=CUSTOMERNUMBER%3D%2740003378%27&outFields=%2A&returnGeometry=false&f=pjson"
  base=dict(identifier='40003378',name='RAINFOREST ALLIANCE INC',raw_status='Expired',expiration='',license_category='Charitable Solicitation',url=url)
  for status,expiry,allowed in [('Expired','',True),('Closed','',True),('Active','',False),('Expired','2026-01-01',True),('Expired','bad',False)]:
   with self.subTest(status=status,expiry=expiry):self.assertEqual(dc.expected_record(dict(base,raw_status=status,expiration=expiry)) is not None,allowed)
  d=dict(state='DC',operation='detail',name=base['name'],identifier=base['identifier'],raw_status='Expired',expiration='')
  fields={'Licensee':base['name'],'Trade Name':'N/A','License Category':'Charitable Services','License Activity':'Charitable Solicitation','License Number':'40003378','Premise Address':'N/A','License Status':'Expired','Issue Date':'10/05/2010','Expiration Date':'N/A'}
  text='License Information\n'+'\n'.join(k+'\n'+fields[k]for k in boss.LABELS)+'\nLicensee Information\n'
  self.assertEqual(boss.fields(boss.DETAILS[0] if isinstance(boss.DETAILS,list) else next(iter(boss.DETAILS)),text,d),fields)
  for key,val in [('License Number','40003379'),('Licensee','WRONG ENTITY'),('License Activity','General Business'),('License Status','Active'),('Expiration Date','11/30/2027')]:
   with self.subTest(key=key):self.assertIsNone(boss.fields(next(iter(boss.DETAILS)),text.replace(key+'\n'+fields[key],key+'\n'+val),d))
if __name__=='__main__':unittest.main(verbosity=2)
