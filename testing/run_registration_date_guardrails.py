"""Registration metadata must not borrow dates or change matching/status."""
import copy, json, sys, unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc
import charity_clarity_report as report
from io import BytesIO
from pypdf import PdfReader

class RegistrationDates(unittest.TestCase):
    def result(self,state='AR',**kwargs):
        value=cc.checker.StateResult('Example Foundation','12-3456789',state,'Current','https://registry.example/selected-record')
        value.success=True;value.matched_registry_name='Example Foundation';value.matched_registry_identifier='123'
        for key,item in kwargs.items():setattr(value,key,item)
        return value
    def test_ar_selected_row_retains_generic_meaning(self):
        r=self.result(raw_status_text='Type: Charity | Status: Current | Registration Date: 2014-02-03')
        before=copy.deepcopy(vars(r)); data=cc.registration_date_metadata(r)
        self.assertEqual(data['registration_date'],'2014-02-03')
        self.assertEqual(data['registration_date_type'],'registry_registration_date')
        self.assertEqual(vars(r),before)
    def test_other_dates_never_substituted(self):
        for state in cc.SUPPORTED_STATES:
            r=self.result(state,raw_status_text='Renewal Date: 2026-04-01 | Expiration Date: 2027-04-01 | Fiscal Year End: 2025-12-31',_cc_detail_body='Original Issue Date: 2/3/2014\nIncorporation Date: 2/3/1990')
            self.assertEqual(cc.registration_date_metadata(r)['registration_date'],'',state)
    def test_uncertain_or_unmatched_rows_never_supply_date(self):
        for status in ['Not Registered','Site Not Reachable','Unable to Confirm','Unable to Verify','Needs Review','Unknown']:
            self.assertEqual(cc.registration_date_metadata(self.result(raw_status_text='Registration Date: 2014-02-03'),status)['registration_date'],'')
        self.assertEqual(cc.registration_date_metadata(self.result(matched_registry_name='',raw_status_text='Registration Date: 2014-02-03'))['registration_date'],'')
    def test_nd_only_exact_selected_detail_label(self):
        r=self.result('ND',_cc_detail_body='registration date: 2/3/2014\nrenewal date: 2/3/2026')
        self.assertEqual(cc.registration_date_metadata(r)['registration_date'],'2014-02-03')
        r._cc_detail_body='initial renewal registration date: 2/3/2014'
        self.assertEqual(cc.registration_date_metadata(r)['registration_date'],'')
    def test_ca_date_tied_to_selected_registration_identifier(self):
        r=self.result('CA',_cc_registration_records=[{'registrationNumber':'other','initialRegistrationDate':'1999-01-01'}, {'registrationNumber':'123','initialRegistrationDate':'2014-02-03','currentExpirationDate':'2027-01-01'}])
        data=cc.registration_date_metadata(r)
        self.assertEqual(data['registration_date'],'2014-02-03');self.assertEqual(data['registration_date_type'],'initial_registration_date')
        r._cc_registration_records.append({'registrationNumber':'123','initialRegistrationDate':'2015-02-03'})
        self.assertEqual(cc.registration_date_metadata(r)['registration_date'],'')
    def test_invalid_future_and_placeholder_dates_unavailable(self):
        for date in ['2025-02-29','9999-01-01','0000-00-00','2026-13-01','', 'Unknown']:
            r=self.result(raw_status_text='Registration Date: '+date)
            self.assertEqual(cc.registration_date_metadata(r)['registration_date'],'')
    def test_report_preserves_meaning_and_rejects_expiration_substitution(self):
        row={'organization_name':'Example Foundation','ein':'123456789','state':'AR','status':'Current',**cc.registration_date_metadata(self.result(raw_status_text='Registration Date: 2014-02-03'))}
        clean=report.validate_results({'results':[row]},cc.SUPPORTED_STATES)[0]
        self.assertEqual(clean['registration_date_type'],'registry_registration_date')
        pdf=report.generate_report({'results':[row]},cc.SUPPORTED_STATES)
        text=' '.join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)
        self.assertIn('2014-02-03',text)
        self.assertIn('does not specify',text)
        row['registration_date_type']='expiration_date'
        with self.assertRaises(ValueError):report.validate_results({'results':[row]},cc.SUPPORTED_STATES)

if __name__=='__main__':unittest.main()
