"""Registration metadata must not borrow dates or change matching/status."""
import copy, json, sys, unittest
from unittest.mock import patch, MagicMock
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
    def co_detail(self):
        return 'Charitable organization\nName\tExample Foundation\nExpires on\t02/15/2027\tInitial registration\t08/23/2004\nRegistration #\t123\tEstablished\t06/05/1907, New York\nEIN\t12-3456789\tForm\tCorporation\n'
    def wv_detail(self):
        return 'CHARITIES DETAILS\nID:\n123\nInitial Registration Date:\n03/06/2014\nLast Registration Date:\n05/11/2026\nOrganization Name:\nExample Foundation\nExpiration Date:\n05/11/2027\nLegally Established Date:\n06/05/1907\n'
    def test_co_initial_date_is_separate_from_establishment_and_expiration(self):
        data=cc.registration_date_metadata(self.result('CO'),body=self.co_detail())
        self.assertEqual(data['registration_date'],'2004-08-23')
        self.assertEqual(data['registration_date_source_label'],'Initial registration')
        # The established master may omit the CO ID; exact EIN + selected name
        # + a single detail registration number still bind this field.
        self.assertEqual(cc.registration_date_metadata(self.result('CO',matched_registry_identifier=''),body=self.co_detail())['registration_date'],'2004-08-23')
    def test_co_other_entity_or_conflicting_details_cannot_supply_date(self):
        for body in [self.co_detail().replace('12-3456789','98-7654321'),self.co_detail().replace('Example Foundation','Example Foundation - Local Chapter'),self.co_detail().replace('Registration #\t123','Registration #\t456'),self.co_detail()*2,self.co_detail().replace('Charitable organization','Search results')]:
            self.assertEqual(cc.registration_date_metadata(self.result('CO'),body=body)['registration_date'],'')
    def test_wv_initial_date_not_latest_renewal(self):
        data=cc.registration_date_metadata(self.result('WV'),body=self.wv_detail())
        self.assertEqual(data['registration_date'],'2014-03-06')
        self.assertEqual(data['registration_date_type'],'initial_registration_date')
    def test_wv_blank_initial_does_not_fall_through_to_last_registration(self):
        for empty in ['N/A','','Not available','2025','02/30/2025']:
            body=self.wv_detail().replace('03/06/2014',empty)
            self.assertEqual(cc.registration_date_metadata(self.result('WV'),body=body)['registration_date'],'')
    def test_wv_detail_identity_must_match_selected_record(self):
        for body in [self.wv_detail().replace('ID:\n123','ID:\n456'),self.wv_detail().replace('Example Foundation','Example Foundation - Local Chapter'),self.wv_detail()*2]:
            self.assertEqual(cc.registration_date_metadata(self.result('WV'),body=body)['registration_date'],'')
        self.assertEqual(cc.registration_date_metadata(self.result('WV',matched_registry_identifier=''),body=self.wv_detail())['registration_date'],'')
    def test_embedded_html_cannot_supply_a_missing_visible_date(self):
        for state,detail in [('CO',self.co_detail()),('WV',self.wv_detail())]:
            for marker in ['<!DOCTYPE html>','<html>']:
                self.assertEqual(cc.registration_date_metadata(self.result(state),body=marker+detail)['registration_date'],'')
    def test_all_states_keep_metadata_separate_from_status(self):
        for state in cc.SUPPORTED_STATES:
            r=self.result(state);before=copy.deepcopy(vars(r))
            data=cc.registration_date_metadata(r,body=self.co_detail()+self.wv_detail())
            self.assertEqual(vars(r),before,state)
            self.assertEqual(set(data),{p+s for p in ('registration_date','renewal_date') for s in ('','_type','_source_label','_source_url','_note')})
        for state,body in [('CO',self.co_detail()),('WV',self.wv_detail())]:
            for status in ['Not Registered','Site Not Reachable','Unable to Confirm','Unable to Verify','Needs Review','Unknown']:
                self.assertEqual(cc.registration_date_metadata(self.result(state),status,body)['registration_date'],'')
    def test_missing_dates_are_completely_blank_for_all_32_jurisdictions(self):
        self.assertEqual(len(cc.SUPPORTED_STATES),32)
        for state in cc.SUPPORTED_STATES:
            self.assertTrue(all(v == '' for v in cc.registration_date_metadata(self.result(state)).values()), state)
    def test_wv_last_registration_keeps_its_own_label(self):
        data=cc.registration_date_metadata(self.result('WV'),body=self.wv_detail())
        self.assertEqual(data['renewal_date'],'2026-05-11')
        self.assertEqual(data['renewal_date_source_label'],'Last Registration Date')
    def test_va_selected_registration_dates_and_current_issue(self):
        r=self.result('VA',_cc_registration_records=[{'registrationNumber':'123','initialIssueDate':'2010-01-01','issueDate':'2026-06-01','expirationDate':'2027-06-01'}, {'registrationNumber':'other','initialIssueDate':'1900-01-01','issueDate':'2026-08-01'}])
        data=cc.registration_date_metadata(r)
        self.assertEqual((data['registration_date'],data['renewal_date']),('2010-01-01','2026-06-01'))
        self.assertEqual(data['renewal_date_type'],'current_issue_date')
        r._cc_registration_records[0]['issueDate']='2010-01-01'
        self.assertEqual(cc.registration_date_metadata(r)['renewal_date'],'')
    def test_ct_effective_date_is_bound_to_public_charity_credential(self):
        r=self.result('CT',matched_registry_identifier='CHR.0001234',_cc_registration_date_detail='Registration CHR.0001234 Registration Type PUBLIC CHARITY Effective Date 06/01/2026 Expiration Date 05/31/2027')
        data=cc.registration_date_metadata(r)
        self.assertEqual(data['renewal_date'],'2026-06-01')
        self.assertEqual(data['registration_date'],'')
        self.assertEqual(data['renewal_date_type'],'current_effective_date')
        r.matched_registry_identifier='CHR.9999999'
        self.assertEqual(cc.registration_date_metadata(r)['renewal_date'],'')
    def test_ok_initial_and_latest_renewal_exclude_other_filings(self):
        body='Details\nFiling Number:\n123\nEntity Name:\nExample Foundation\nEntity Type:\nCharitable Organization\nOriginal Filing Date:\nDec 28 2016\nFILING HISTORY :\n1\tApplication for Registration\tDecember 28, 2016\t7\n2\tRenewal Registration\tJune 5, 2025\t9\n3\tRenewal Registration\tJune 5, 2026\t6\n4\tAmended Registration\tJuly 1, 2026\t1\n'
        data=cc.registration_date_metadata(self.result('OK'),body=body)
        self.assertEqual((data['registration_date'],data['renewal_date']),('2016-12-28','2026-06-05'))
        self.assertEqual(cc.registration_date_metadata(self.result('OK'),body=body.replace('Filing Number:\n123','Filing Number:\n456'))['renewal_date'],'')
    def test_ms_only_explicit_initial_date_in_selected_panel(self):
        body='Printer Friendly Version\nExample Foundation\nPurpose\nFiling Information\nInitial Date Filed:\t03/06/2014\nExpiration Date:\t05/15/2027'
        data=cc.registration_date_metadata(self.result('MS'),body=body)
        self.assertEqual(data['registration_date'],'2014-03-06')
        self.assertEqual(data['registration_date_type'],'initial_registration_filing_date')
        self.assertEqual(cc.registration_date_metadata(self.result('MS'),body=body.replace('Example Foundation','Different Foundation'))['registration_date'],'')
    def test_nm_submitted_registration_not_open_or_extension(self):
        r=self.result('NM',raw_status_text='Tax Year 2024 | Registration Submitted 4/21/2026 | Filed FYE: 06/30/2025 | Due: 12/31/2026')
        data=cc.registration_date_metadata(r)
        self.assertEqual(data['renewal_date'],'2026-04-21')
        self.assertEqual(data['renewal_date_type'],'annual_registration_submitted_date')
        for action in ['Registration Open','Extension Requested']:
            r.raw_status_text='Tax Year 2024 | '+action+' 4/21/2026'
            self.assertEqual(cc.registration_date_metadata(r)['renewal_date'],'')
    def test_retained_issue_evidence_must_match_selected_identifier_and_name(self):
        for state in ('FL','WI'):
            proof={'identifier':'123','name':'Example Foundation','initial':'03/06/2014','initial_label':'Granted','initial_type':'initial_credential_issue_date'}
            r=self.result(state,_cc_registration_date_evidence=proof)
            self.assertEqual(cc.registration_date_metadata(r)['registration_date'],'2014-03-06')
            for key,value in [('identifier','456'),('name','Other Foundation')]:
                r._cc_registration_date_evidence={**proof,key:value}
                self.assertEqual(cc.registration_date_metadata(r)['registration_date'],'')
    def test_fl_license_issue_is_not_expiration_or_other_credential(self):
        source='<table id="cpMainContent_MasterGv_dataTab_0"><tr><td><strong>Example Foundation</strong></td></tr></table><p>License Type License# Issued Expires Status Charitable Organization CH123 06/10/93 10/22/26 Registered </p>'
        proof=cc.fl_registration_issue_evidence(source,'CH123','Example Foundation')
        self.assertEqual(cc.registration_source_date(proof['initial']).isoformat(),'1993-06-10')
        self.assertEqual(cc.fl_registration_issue_evidence(source,'CH999','Example Foundation'),{})
        self.assertEqual(cc.fl_registration_issue_evidence(source,'CH123','Example Foundation Local Chapter'),{})
        self.assertEqual(cc.fl_registration_issue_evidence(source+source,'CH123','Example Foundation'),{})
    def test_fl_date_failure_cannot_change_primary_status_or_comments(self):
        r=self.result('FL',matched_registry_identifier='CH123',raw_status_text='Expiration Date 10/22/2026')
        before=copy.deepcopy(vars(r))
        with patch.object(cc.curl_requests,'Session',side_effect=TimeoutError('test timeout')),patch.object(cc,'fl_verified_registration_issue',return_value={}):
            cc.enrich_registration_date_sources(r,'Current')
        self.assertEqual({k:v for k,v in vars(r).items() if k not in {'_cc_registration_date_evidence','registration_date_diagnostics'}},before)
        self.assertEqual(r.registration_date_diagnostics[0]['reason'],'TimeoutError')
    def test_co_history_excludes_notices_and_binds_the_selected_record(self):
        summary=self.co_detail()+'''<html><form id="ccsaSummaryForm"><input type="hidden" name="javax.faces.ViewState" value="opaque"/><a onclick="mojarra.jsfcljs(document.getElementById('ccsaSummaryForm'),{'history':'history'},'')">History</a></form></html>'''
        history='<h1>History</h1><p>Name Example Foundation Registration # 123 Status Good</p><table><tr><td>Filed Date</td><td>Document #</td><td>Event</td></tr><tr><td>09/01/2026</td><td>10</td><td>Second notice of expired registration sent</td></tr><tr><td>08/01/2026</td><td>9</td><td>Extension</td></tr><tr><td>06/03/2026</td><td>8</td><td>Renewal view financial statement</td></tr><tr><td>06/03/2025</td><td>7</td><td>Renewal</td></tr></table>'
        page=MagicMock();page.url='https://www.coloradosos.gov/ccsa/pages/public/summary.xhtml'
        response=page.request.post.return_value;response.ok=True;response.url=page.url;response.text.return_value=history
        r=self.result('CO');before=copy.deepcopy(vars(r))
        proof=cc.co_registration_renewal_evidence(page,r,summary)
        self.assertEqual(proof['renewal'],'2026-06-03');self.assertEqual(vars(r),before)
        self.assertEqual(page.request.post.call_args.kwargs['timeout'],3000)
        response.text.return_value=history.replace('Registration # 123','Registration # 456')
        self.assertEqual(cc.co_registration_renewal_evidence(page,r,summary),{})
    def test_report_keeps_both_dates_and_missing_cells_blank(self):
        row={'organization_name':'Example Foundation','ein':'123456789','state':'WV','status':'Current',**cc.registration_date_metadata(self.result('WV'),body=self.wv_detail())}
        pdf=report.generate_report({'results':[row]},cc.SUPPORTED_STATES)
        text=' '.join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)
        self.assertIn('2014-03-06',text);self.assertIn('2026-05-11',text)
        row.update(cc.registration_date_metadata(self.result('OH')))
        clean=report.validate_results({'results':[row]},cc.SUPPORTED_STATES)[0]
        self.assertEqual(clean['registration_date'],'');self.assertEqual(clean['renewal_date'],'')
        row['renewal_date']='2026-05-11';row['renewal_date_type']='expiration_date'
        with self.assertRaises(ValueError):report.validate_results({'results':[row]},cc.SUPPORTED_STATES)
    def test_metadata_does_not_request_any_registry_or_change_names(self):
        with patch.object(cc.curl_requests,'Session',side_effect=AssertionError('network in pure metadata')):
            for state in cc.SUPPORTED_STATES:
                r=self.result(state); before=copy.deepcopy(vars(r))
                cc.registration_date_metadata(r)
                self.assertEqual(vars(r),before)
    def test_optional_dates_do_not_use_exhausted_primary_budgets(self):
        started=cc.time.perf_counter()-min(cc.BATCH_FANOUT_STATE_TIMEOUT_SECONDS,cc.BATCH_STATE_LOOKUP_TIMEOUT_SECONDS,cc.SINGLE_STATE_OVERFLOW_TIMEOUT_SECONDS)
        with patch.object(cc.curl_requests,'Session') as session:
            r=self.result('FL',matched_registry_identifier='CH123');before=copy.deepcopy(vars(r))
            cc.enrich_registration_date_sources(r,'Current',started)
            session.assert_not_called();self.assertEqual(vars(r),before)
        page=MagicMock()
        self.assertEqual(cc.co_registration_renewal_evidence(page,self.result('CO'),self.co_detail(),started),{})
        page.request.post.assert_not_called()
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
