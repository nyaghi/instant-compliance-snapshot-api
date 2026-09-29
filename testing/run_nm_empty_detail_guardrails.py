"""A blank detail response is not proof of non-registration."""
import sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class EmptyDetailControls(unittest.TestCase):
    def setUp(self):
        self.m=c.load_wa_nm_module()
        self.org=c.checker.Organization('Example Foundation','012345678')

    def first(self):
        r=c.checker.StateResult(self.org.organization_name,self.org.ein,'NM','Not Registered',self.m.NM_SEARCH_URL)
        r.raw_status_text='No New Mexico charity registration name found for this FEIN.'
        r.source_note='New Mexico returned a FEIN detail shell, but it did not expose a charity name.'
        r.success=True
        return r

    def html(self,ein='01-2345678',history=None):
        history=history or [(2025,'Registration Submitted 20250000123456789','1/15/2026')]
        rows=''.join(f'<tr><td>{year}</td><td>{detail}</td><td>{when}</td></tr>' for year,detail,when in history)
        return (f'<span id="MainContent_FormViewCharityDetail_LabelCharityName">Example Foundation ({ein})</span>'
            f'<table id="MainContent_GridViewStatuses">{rows}</table><a>2025-FYE20251231.pdf</a>')

    def confirm(self,html='',error=''):
        with patch.object(self.m,'nm_fetch_detail_html',return_value=(html,error)) as read:
            result=c.nm_confirm_empty_detail(self.org,self.m,self.first())
            read.assert_called_once_with(self.org.ein,timeout_seconds=12)
            return result

    def test_same_ein_history_recovers_without_accepting_initial_negative(self):
        r=self.confirm(self.html())
        self.assertEqual(r.status,'Current');self.assertTrue(r.success)
        self.assertEqual(r.matched_registry_name,'Example Foundation')
        self.assertEqual(r.matched_registry_identifier,'01-2345678')
        self.assertIn('Due: 06/30/2027',r.raw_status_text)
        self.assertEqual(r.source_attempts[-1]['outcome'],'ein_matched_history')

    def test_extension_evidence_preserves_existing_master_interpretation(self):
        html=self.html(history=[(2025,'Extension Granted','6/26/2026'),(2024,'Registration Submitted 20240000123456789','11/3/2025')]).replace('2025-FYE20251231','2024-FYE20241231')
        r=self.confirm(html)
        self.assertEqual(r.status,'Upcoming Filing');self.assertIn('Due: 12/31/2026',r.raw_status_text)

    def test_completed_explicit_empty_response_remains_negative(self):
        r=self.confirm('<h2>Status History</h2><p>Charity Registration Status is unknown.</p><h2>Financials</h2>')
        self.assertEqual(r.status,'Not Registered');self.assertTrue(r.success)
        self.assertEqual(r.reason_code,'NM_COMPLETED_EMPTY_FEIN_CONFIRMATION')
        self.assertIn('explicit',c.comments_for_result(r,'',r.status))

    def test_blank_and_loading_documents_are_not_negative(self):
        for html in ['', '<html>Charity Detail</html>', '<p>Loading charity record...</p>']:
            with self.subTest(html=html):
                r=self.confirm(html);self.assertEqual(r.status,'Unable to Confirm');self.assertFalse(r.success)
                self.assertFalse(getattr(r,'matched_registry_name',''))
                self.assertIn('bounded official-page confirmation',c.comments_for_result(r,'',r.status))

    def test_open_tax_year_or_named_identity_blocks_empty_inference(self):
        for html in ['Charity Registration Status is unknown. Tax Year Registration Open',
                     '<span id="MainContent_FormViewCharityDetail_LabelCharityName">Example Foundation (01-2345678)</span> Charity Registration Status is unknown.']:
            r=self.confirm(html);self.assertEqual(r.status,'Unable to Confirm');self.assertFalse(r.success)

    def test_different_or_absent_header_ein_is_not_recovered(self):
        for html in [self.html('98-7654321'),self.html().replace('(01-2345678)','')]:
            r=self.confirm(html);self.assertEqual(r.status,'Unable to Confirm');self.assertFalse(r.success)

    def test_access_failure_and_exception_are_not_negative(self):
        r=self.confirm('', 'HTTP 503');self.assertEqual(r.status,'Unable to Confirm');self.assertFalse(r.success)
        with patch.object(self.m,'nm_fetch_detail_html',side_effect=TimeoutError()):
            r=c.nm_confirm_empty_detail(self.org,self.m,self.first())
        self.assertFalse(r.success);self.assertEqual(r.reason_code,'NM_DETAIL_CONFIRMATION_INCOMPLETE')

    def test_existing_success_and_explicit_negative_do_not_add_confirmation_request(self):
        for status,raw in [('Current','Due: 06/30/2027'),('Not Registered','No New Mexico charity registration status-history rows found for this FEIN.')]:
            external=self.m.SearchResult(self.org.organization_name,self.org.ein,'NM',status,raw,self.m.NM_SEARCH_URL,'')
            external.success=True
            with patch.object(c,'search_nm_status_history_fallback',return_value=external),patch.object(c,'nm_confirm_empty_detail') as confirmation:
                r=c.search_wa_nm_state(self.org,'NM')
                confirmation.assert_not_called();self.assertEqual(c.public_status(r),status)

    def test_empty_detail_rule_is_applied_at_master_boundary(self):
        first=self.first()
        with patch.object(c,'search_nm_status_history_fallback',return_value=first),patch.object(c,'nm_confirm_empty_detail',return_value='confirmed') as confirmation:
            self.assertEqual(c.search_wa_nm_state(self.org,'NM'),'confirmed')
            confirmation.assert_called_once()

    def test_adapter_keeps_existing_default_and_accepts_bounded_confirmation(self):
        response=Mock(status_code=200,text='complete public response')
        with patch.object(self.m.curl_requests,'get',return_value=response) as get:
            self.m.nm_fetch_detail_html(self.org.ein);self.assertEqual(get.call_args.kwargs['timeout'],35)
            self.m.nm_fetch_detail_html(self.org.ein,timeout_seconds=12);self.assertEqual(get.call_args.kwargs['timeout'],12)

if __name__=='__main__':unittest.main(verbosity=2)
