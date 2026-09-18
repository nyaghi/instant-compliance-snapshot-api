"""Saved official records plus identity, freshness, and failure boundaries."""
import json, sys, unittest
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import date
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c
F = Path(__file__).parent/'fixtures/or-ma-live-period'
class Today(date):
    @classmethod
    def today(cls): return cls(2026,9,17)
class Controls(unittest.TestCase):
    def setUp(self):
        self.org = c.checker.Organization('National Credit Union Foundation, Inc.', '39-1383650')
        self.row = ['8122','19363','','','391383650','','National Credit Union Foundation, Inc.','','4703 Madison Yards Way, Suite 300','','Madison','WI','53705','','01/01/2024','12/31/2024']
        self.source = (F/'oregon-detail.html').read_text(encoding='utf-8')
        p=patch.object(c,'date',Today);p.start();self.addCleanup(p.stop)
        p=patch.object(c,'or_snapshot_row_for_ein',return_value=self.row);p.start();self.addCleanup(p.stop)
    def run_live(self, source=None, failure=False):
        result=c.or_snapshot_result_for_ein(self.org)
        response=Mock(url='https://justice.oregon.gov/Charities/Charity/details?charityID=8122')
        response.read.return_value=(source if source is not None else self.source).encode()
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        with patch.object(c.urllib.request,'urlopen',side_effect=TimeoutError() if failure else None,return_value=response) as request:
            actual=c.or_confirm_snapshot_delinquency(self.org,result)
        return actual,request
    def test_reported_new_live_filing_overrides_export_through_final_comment(self):
        r,_=self.run_live()
        self.assertEqual(r.status,'Current')
        self.assertEqual(c.true_status_from_body(r,''),'Current')
        self.assertEqual(r.computed_due_date,'5/15/2027')
        self.assertEqual(c.filing_context(r,'')['due_date'],date(2027,5,15))
        self.assertEqual(r.or_live_evidence['address'],'Mailing Address: 4703 Madison Yards Way, Suite 300 Madison, WI 53705')
        comment=c.comments_for_result(r,'',r.status)
        self.assertIn('12/31/2025',comment);self.assertIn('live record',comment)
        self.assertNotIn('Scheduled OR dataset last downloaded',comment)
    def test_current_export_does_not_add_network_work(self):
        self.row[15]='12/31/2025'
        r,request=self.run_live();self.assertEqual(r.status,'Current');request.assert_not_called()
    def test_temporary_live_read_failure_recovers_same_identity(self):
        result=c.or_snapshot_result_for_ein(self.org)
        response=Mock(url='https://justice.oregon.gov/Charities/Charity/details?charityID=8122')
        response.read.return_value=self.source.encode();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        with patch.object(c.urllib.request,'urlopen',side_effect=[TimeoutError('slow'),response]) as request:
            result=c.or_confirm_snapshot_delinquency(self.org,result)
        self.assertEqual(result.status,'Current');self.assertEqual(request.call_count,2)
        self.assertTrue(any('TimeoutError' in attempt for attempt in result.source_attempts))
    def test_newer_overdue_export_with_older_live_history_keeps_newer_period(self):
        self.row[14]='5/1/2024';self.row[15]='4/30/2025'
        source=self.source.replace('1/1/2025 and Ending 12/31/2025','1/1/2024 and Ending 12/31/2024')
        result,_=self.run_live(source)
        self.assertEqual(result.status,'Delinquent');self.assertTrue(result.source_truth_conflict)
        self.assertEqual(result.status_reason,'OR_OVERDUE_UNDER_BOTH_CONFIRMED_PERIODS')
        comment=c.comments_for_result(result,'',c.true_status_from_body(result,''))
        self.assertIn('4/30/2025',comment);self.assertIn('12/31/2024',comment)
        self.assertIn('9/15/2026',comment)
    def test_confirmed_overdue_record_stays_delinquent(self):
        source=self.source.replace('1/1/2025 and Ending 12/31/2025','1/1/2024 and Ending 12/31/2024')
        r,_=self.run_live(source);self.assertEqual(r.status,'Delinquent');self.assertEqual(r.computed_due_date,'5/15/2026')
    def test_noncalendar_period_uses_actual_end(self):
        source=self.source.replace('1/1/2025 and Ending 12/31/2025','7/1/2024 and Ending 6/30/2025')
        r,_=self.run_live(source);self.assertEqual(r.computed_due_date,'11/15/2026');self.assertEqual(r.status,'Upcoming Filing')
    def test_incomplete_identity_period_or_outage_cannot_prove_delinquency(self):
        for source in (self.source.replace('39-1383650','39-1383651'),self.source.replace('#19363','#99999'),
                       self.source.replace('class="reportperiod"','class="unrecognized"'),
                       self.source.replace('1/1/2025 and Ending 12/31/2025','1/1/2025 and Ending 12/31/2030'),
                       self.source.replace('>Registered</abbr>','>Unknown</abbr>'),'<html>temporarily unavailable</html>'):
            r,_=self.run_live(source);self.assertEqual(r.status,'Unable to Confirm')
            self.assertIsNone(c.filing_context(r,'')['due_date'])
        r,_=self.run_live(failure=True);self.assertEqual(r.status,'Unable to Confirm')
    def test_exact_ein_and_registration_preserve_identity_after_address_change(self):
        r,_=self.run_live(self.source.replace('Madison, WI 53705','Chicago, IL 60601'))
        self.assertEqual(r.status,'Current');self.assertIn('Chicago',r.or_live_evidence['address'])
    def test_visible_adverse_state_status_overrides_new_filing(self):
        r,_=self.run_live(self.source.replace('>Registered</abbr>','>Suspended</abbr>'))
        self.assertEqual(c.true_status_from_body(r,''),'Suspended')
        self.assertEqual(r.computed_due_date,'')
    def test_actual_ma_multiple_legacy_uploads(self):
        completed=json.loads((F/'ma-completed.json').read_text())
        p=Mock();p.locator.return_value.inner_text.return_value='AG Account Number 055690'
        p.get_by_role.return_value.all_inner_texts.return_value=['2013 FY2013 PC - Form PC/Annual RPT.tiff']
        r=c.checker.StateResult('Partnership for Civil Justice Fund','26-2851211','MA','Current','')
        e=c.ma_read_latest_form_pc(p,r,'AG Account Number 055690',completed)
        self.assertTrue(e['completed_history_inferred_delinquent']);self.assertEqual(e['latest_public_document_year'],2016)
        r=c.annotate_ma_visible_form_pc_due(r,e)
        self.assertEqual(r.status,'Delinquent');self.assertEqual(r.computed_due_date,'')
        p.context.request.get.assert_not_called()
if __name__=='__main__':unittest.main(verbosity=2)
