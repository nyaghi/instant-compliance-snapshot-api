"""Confirmed exemptions, adverse exemption licenses and duplicate visibility."""
import sys, time, unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc

class DisputedLicenses(unittest.TestCase):
    def setUp(self):
        self.org=cc.checker.Organization('Example Foundation','123456789')
        self.deadline=time.monotonic()+20
        p=patch.object(cc,'reconciled_registry_address',return_value={'decision':'corroborated'});p.start();self.addCleanup(p.stop)
    def row(self,identifier='CH123',raw='Active',status='Current',expiry=None,**extra):
        return dict(name='Example Foundation',identifier=identifier,raw_status=raw,status=status,
                    expiration=expiry,location='Washington, DC',**extra)
    def test_ga_explicit_exemption_is_not_displaced_by_ordinary_filing_deadline(self):
        rows=[self.row(expiry=date.today()+timedelta(days=2),status='Upcoming Filing'),self.row('EXEMPT','Exempt','Exempt')]
        result=cc.licensed_charity_result(self.org,'GA',rows,self.deadline,'https://example.invalid')
        self.assertEqual(result.status,'Exempt');self.assertIn('CH123: Active',result.source_note)
        self.assertIn('retains Georgia',result.source_note)
        self.assertFalse(getattr(result,'computed_due_date',''))
    def test_explicit_exemption_does_not_hide_newer_revocation(self):
        rows=[self.row('EXEMPT','Exempt','Exempt'),self.row('CH123','Revoked','Revoked',date.today())]
        result=cc.licensed_charity_result(self.org,'GA',rows,self.deadline,'https://example.invalid')
        self.assertEqual(result.status,'Needs Review')
    def test_wrong_identity_exemption_never_overrides_registration(self):
        wrong=self.row('EXEMPT','Exempt','Exempt');wrong['name']='Unrelated Organization'
        result=cc.licensed_charity_result(self.org,'GA',[self.row(),wrong],self.deadline,'https://example.invalid')
        self.assertEqual(result.status,'Current')
    def test_dc_expired_exempt_category_is_not_current_exemption(self):
        row=self.row('400119000006','Expired - Enforcement','Delinquent',date(2022,11,30),license_category='Charitable Exempt')
        result=cc.licensed_charity_result(self.org,'DC',[row],self.deadline,'https://example.invalid')
        self.assertEqual(result.status,'Delinquent');self.assertIn('does not establish a current exemption',result.source_note)
    def test_dc_new_active_record_keeps_canceled_record_visible(self):
        rows=[self.row('OLD','Cancelled','Closed / Withdrawn / Canceled',date(2026,4,30)),self.row('NEW',expiry=date(2028,8,31))]
        result=cc.licensed_charity_result(self.org,'DC',rows,self.deadline,'https://example.invalid')
        self.assertEqual(result.status,'Current');self.assertIn('OLD: Cancelled',result.source_note)
    def test_ri_selection_policy_remains_latest_current_record(self):
        rows=[self.row('EXEMPT','Exempt','Exempt'),self.row('NEW',expiry=date.today()+timedelta(days=365))]
        result=cc.licensed_charity_result(self.org,'RI',rows,self.deadline,'https://example.invalid')
        self.assertEqual(result.status,'Current');self.assertNotIn('retains Georgia',result.source_note)

if __name__=='__main__':unittest.main()
