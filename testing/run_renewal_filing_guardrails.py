"""Two-column display controls: verified source meanings and no lookup changes."""
import copy, json, sys, unittest
from pathlib import Path
from unittest.mock import patch
from io import BytesIO
from pypdf import PdfReader
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc
import charity_clarity_report as report


class RenewalFiling(unittest.TestCase):
    def result(self, state='MA', raw='', **attrs):
        r = cc.checker.StateResult('Example Foundation', '12-3456789', state, 'Current', 'https://registry.example/selected')
        r.success = True
        r.matched_registry_name = 'Example Foundation'
        r.matched_registry_identifier = '123'
        r.raw_status_text = raw
        for k, v in attrs.items(): setattr(r, k, v)
        return r

    def metadata(self, r, dates=None, **kwargs):
        return cc.renewal_filing_metadata(r, dates or {}, **kwargs)

    def test_renewal_wins_and_retains_meaning(self):
        meanings = {'renewal_filing_date':'Renewal filed', 'last_registration_date':'Last registration date',
                    'current_issue_date':'Current registration issued', 'current_effective_date':'Current period effective',
                    'annual_registration_submitted_date':'Registration submitted'}
        for kind, label in meanings.items():
            old = {'renewal_date':'2026-06-01','renewal_date_type':kind,'renewal_date_source_url':'https://registry.example/renewal','renewal_date_note':'State source'}
            before = old.copy()
            out = self.metadata(self.result(raw='Latest Filed Fiscal Period End: 12/31/2025'), old)
            self.assertEqual((out['renewal_filing_value'],out['renewal_filing_label']),('2026-06-01',label))
            self.assertEqual(out['renewal_filing_source_url'],old['renewal_date_source_url'])
            self.assertEqual(old,before)

    def test_selected_period_labels(self):
        for state, raw in [('MA','Latest Filed Fiscal Period End: 6/30/2025'),('MN','Fiscal Year Ending 6/30/2025'),
                           ('NY','Latest FYE: 2025-06-30'),('OR','Fiscal Period End: 6/30/2025')]:
            out = self.metadata(self.result(state,'Active | '+raw+' | Next Required Period: 6/30/2026'))
            self.assertEqual(out['renewal_filing_value'],'2025-06-30',state)
            self.assertEqual(out['renewal_filing_label'],'Filed period ending')

    def test_conflicting_or_invalid_periods_not_used(self):
        for raw in ['Latest FYE: 2025-02-30','Latest FYE: 2099-12-31','Latest FYE: 2024-06-30 | Latest FYE: 2025-06-30']:
            self.assertFalse(self.metadata(self.result('NY',raw))['renewal_filing_value'])

    def test_next_deadline_and_month_day_cannot_be_used_as_last_filing(self):
        for state in cc.SUPPORTED_STATES:
            r = self.result(state,'Next Required Period: 6/30/2026 | Due Date: 11/15/2026 | Fiscal Year End: 12/31 | Expiration Date: 2026-04-01')
            self.assertFalse(self.metadata(r)['renewal_filing_value'],state)

    def tax_result(self, state='HI', **evidence):
        return self.result(state,last_year_on_record='2024',status_reason=state+'_CONFIRMED_TAX_PERIOD',
                           tax_period_evidence={'ein':'123456789','tax_year_label':'2024','period_end':'2025-06-30',
                                                'period_basis':'State filing attachment',**evidence})

    def test_tax_label_and_actual_fiscal_period_differ(self):
        for state in ('HI','KY'):
            out=self.metadata(self.tax_result(state))
            self.assertEqual(out['renewal_filing_value'],'2025-06-30')
            self.assertIn('tax year 2024',out['renewal_filing_note'])

    def test_downloaded_tax_record_retains_its_state_source_link(self):
        r=self.tax_result('KY',state_source_url='https://registry.example/charities.pdf',source_url='https://registry.example/return.pdf')
        r.source_url=''
        self.assertEqual(self.metadata(r)['renewal_filing_source_url'],'https://registry.example/charities.pdf')

    def test_assumed_period_displays_only_source_year(self):
        for flag in ('period_assumed','period_unconfirmed'):
            out=self.metadata(self.tax_result(**{flag:True}))
            self.assertEqual(out['renewal_filing_value'],'2024')
            self.assertEqual(out['renewal_filing_label'],'Filed tax year')

    def test_tax_evidence_must_match_ein_and_year(self):
        for changes in [{'ein':'987654321'},{'tax_year_label':'2023'}]:
            self.assertFalse(self.metadata(self.tax_result(**changes))['renewal_filing_value'])
        r=self.tax_result();r.status_reason='HI_UNCONFIRMED_TAX_PERIOD'
        self.assertFalse(self.metadata(r)['renewal_filing_value'])

    def test_state_year_only_stays_a_year(self):
        for state,raw,label in [('OH','Most Recent Report Filing Year: 2025','Filed year'),
                                ('KY','Yr Last Filed: 2024','Filed tax year'),
                                ('HI','Last Year on Record: 2024','Filed tax year'),
                                ('MN','Fiscal Year Ending 2025','Filed year'),
                                ('MA','Last Year on Record: 2025','Filed year')]:
            out=self.metadata(self.result(state,raw))
            self.assertEqual(len(out['renewal_filing_value']),4)
            self.assertEqual(out['renewal_filing_label'],label)

    def test_ma_legacy_reporting_period_is_not_a_new_renewal(self):
        r=self.result('MA','Document: Unified Registration Statement | Reporting period end: 12/31/2022 | No later annual report in completed filing list | Delinquency inferred',status_reason='MA_LEGACY_URS_NO_LATER_ANNUAL')
        out=self.metadata(r)
        self.assertEqual(out['renewal_filing_value'],'2022-12-31')
        self.assertEqual(out['renewal_filing_type'],'filed_period_end')

    def test_sc_uses_completed_period_not_next_report(self):
        out=self.metadata(self.result('SC','Fiscal Year: 7/1/2024 - 6/30/2025 | Next Report: 07/01/2025 - 06/30/2026'))
        self.assertEqual(out['renewal_filing_value'],'2025-06-30')
        self.assertFalse(self.metadata(self.result('SC','Fiscal Year: 7/1/2025 - 6/30/2024'))['renewal_filing_value'])

    def test_nj_selected_field_and_year_only(self):
        r=self.result('NJ',status_reason='NJ_STATUS_FROM_REGISTRY_FILING_PERIOD',last_year_on_record=2025)
        body='<input value="2025-06-30T00:00:00.0000000" id="crsm_fiscalyearenddate">'
        self.assertEqual(self.metadata(r,body=body)['renewal_filing_value'],'2025-06-30')
        body='<input id="crsm_fiscalyearenddate" value=""> Renewal Due 2026-06-30'
        self.assertEqual(self.metadata(r,body=body)['renewal_filing_value'],'2025')
        r.last_year_on_record='';r.status_reason=''
        self.assertFalse(self.metadata(r,body=body)['renewal_filing_value'])

    def md_entry(self, identifier='123', ein='12-3456789', year='2024', escaped=False):
        fields={key:f'<p><strong>{key}:</strong> <var>{val}</var></p>' for key,val in
                [('Charity ID',identifier),('Charity EIN',ein),('Year Represented',year)]}
        if escaped: fields={k:v.replace('<',r'\u003c').replace('>',r'\u003e') for k,v in fields.items()}
        return {'view_data':{'content_element_data':fields}}

    def test_md_uses_selected_id_and_ein_not_other_entry(self):
        body=json.dumps({'entries':[self.md_entry('999',year='2025'),self.md_entry(escaped=True)]})
        out=self.metadata(self.result('MD'),body=body)
        self.assertEqual(out['renewal_filing_value'],'2024')
        for entries in [[self.md_entry(ein='98-7654321')],[self.md_entry('999')],
                        [self.md_entry(),self.md_entry(year='2025')]]:
            self.assertFalse(self.metadata(self.result('MD'),body=json.dumps({'entries':entries}))['renewal_filing_value'])

    def test_ca_excludes_pending_and_not_submitted_years(self):
        body='Annual Renewal Data Status of Filing: Accepted Accounting Period End Date: 06/30/2024 Filing Received Date: 05/01/2025 Status of Filing: Not Submitted Accounting Period End Date: 06/30/2025'
        self.assertEqual(self.metadata(self.result('CA'),body=body)['renewal_filing_value'],'2024')
        self.assertFalse(self.metadata(self.result('CA'),body=body.replace('Accepted','Pending'))['renewal_filing_value'])

    def test_unconfirmed_no_record_and_unmatched_rows_blank(self):
        for status in ('Not Registered','Site Not Reachable','Unknown','Needs Review','Unable to Confirm','Unable to Verify'):
            self.assertFalse(any(self.metadata(self.result(raw='Latest Filed Fiscal Period End: 6/30/2025'),final_status=status).values()))
        for attrs in ({'success':False},{'matched_registry_name':''}):
            self.assertFalse(any(self.metadata(self.result(raw='Latest Filed Fiscal Period End: 6/30/2025',**attrs)).values()))

    def test_all_30_states_pure_no_requests_and_missing_values_blank(self):
        with patch.object(cc.curl_requests,'Session',side_effect=AssertionError('Unexpected I/O')):
            for state in cc.SUPPORTED_STATES:
                r=self.result(state);before=copy.deepcopy(vars(r))
                out=self.metadata(r)
                self.assertEqual(vars(r),before)
                self.assertEqual(len(out),5)
                self.assertFalse(any(out.values()),state)

    def report_row(self, value='2024', kind='filed_year', label='Filed year'):
        return {'organization_name':'Example Foundation','ein':'123456789','state':'OH','status':'Current',
                'renewal_filing_value':value,'renewal_filing_type':kind,'renewal_filing_label':label}

    def test_report_keeps_year_and_labeled_period(self):
        for value,kind,label in [('2024','filed_year','Filed year'),('2025-06-30','filed_period_end','Filed period ending')]:
            payload={'results':[self.report_row(value,kind,label)]}
            clean=report.validate_results(payload,cc.SUPPORTED_STATES)[0]
            self.assertEqual(clean['renewal_filing_value'],value)
            pdf=report.generate_report(payload,cc.SUPPORTED_STATES)
            text=' '.join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)
            self.assertIn('Initial Registration Date',text)
            self.assertIn('Last Renewal / Filed Year',text)
            self.assertIn(value,text);self.assertIn(label,text)
            self.assertNotIn('2024-12-31',text)

    def test_report_rejects_mislabeled_or_future_values(self):
        for value,kind,label in [('2024','filed_period_end','Filed period ending'),('2025-06-30','filed_year','Filed year'),
                               ('2099','filed_year','Filed year'),('2025-02-30','filed_period_end','Filed period ending'),
                               ('2024','expiration_date','Expired'),('2024','filed_year','')]:
            with self.assertRaises(ValueError):report.validate_results({'results':[self.report_row(value,kind,label)]},cc.SUPPORTED_STATES)

    def test_report_missing_remains_blank_and_old_snapshot_works(self):
        row=self.report_row('')
        clean=report.validate_results({'results':[row]},cc.SUPPORTED_STATES)[0]
        self.assertTrue(all(not v for k,v in clean.items() if k.startswith('renewal_filing_')))
        row.update(renewal_date='2026-06-01',renewal_date_type='renewal_filing_date',renewal_date_source_label='Filed Date')
        clean=report.validate_results({'results':[row]},cc.SUPPORTED_STATES)[0]
        self.assertEqual(clean['renewal_filing_value'],'2026-06-01')

if __name__=='__main__':unittest.main()
