"""Hawaii transport shortcut must preserve identity, filing rules and fallback."""
from pathlib import Path
import unittest
from unittest.mock import patch
import registry_snapshot_server as c

ROOT = Path(__file__).resolve().parents[1] / 'fixtures/hi-direct-public'

class HawaiiDirectTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT/'good-sports-detail.html').read_text(encoding='utf-8')
        self.org = c.checker.Organization('Good Sports', '75-3138664')
        self.url = 'https://charity.ehawaii.gov/charity/753138664/details.html'

    def parse(self, source=None):
        with patch.object(c, 'hi_public_filing_period', return_value={}) as period:
            value = c.hi_direct_details_from_source(self.org, source or self.source, self.url)
        return value, period

    def test_complete_ein_detail_keeps_original_filing_reader(self):
        value, period = self.parse()
        result, body = value
        self.assertTrue(result.success)
        self.assertEqual(c.canonical_ein_digits(result.matched_registry_identifier), '753138664')
        self.assertIn('GOOD SPORTS', result.matched_registry_name.upper())
        self.assertEqual(result.raw_status_text, 'Registration Status: Active | Registration Type: Registered')
        document, ein = period.call_args.args
        self.assertEqual(document.content(), self.source)
        self.assertEqual(document.url, self.url)
        self.assertEqual(ein, self.org.ein)
        self.assertIn('2025', body)
        self.assertNotIn('function(', body)

    def test_mismatched_missing_or_duplicate_identity_falls_back(self):
        for source in (self.source.replace('75-3138664', '11-1111111'),
                       self.source.replace('FEIN', 'Missing label'),
                       self.source.replace('</html>', '<dt>FEIN</dt><dd>753138664</dd></html>'),
                       self.source.replace('</html>', ''),
                       self.source.replace('Documents', 'Not loaded')):
            with self.subTest(source=source[-70:]):
                value, period = self.parse(source)
                self.assertIsNone(value)
                period.assert_not_called()

    def test_incomplete_tax_period_remains_inconclusive(self):
        with patch.object(c, 'hi_public_filing_period', return_value={
                'period_unconfirmed': True, 'period_read_failure': 'attachment not complete'}):
            result, _ = c.hi_direct_details_from_source(self.org, self.source, self.url)
        self.assertEqual(result.status, 'Unable to Confirm')
        self.assertEqual(result.period_read_failure, 'attachment not complete')

    def test_current_year_attachment_uses_existing_period_rules(self):
        evidence={'ein':'753138664','tax_year_label':2025,'period_begin':'2025-01-01',
                  'period_end':'2025-12-31','source_url':self.url}
        expected=c.checker.StateResult(self.org.organization_name,self.org.ein,'HI','Active',self.url)
        expected.raw_status_text='Registration Status: Active | Registration Type: Registered'
        c.annotate_irs_based_state_period(expected,evidence)
        with patch.object(c, 'hi_public_filing_period', return_value=evidence):
            result, _ = c.hi_direct_details_from_source(self.org,self.source,self.url)
        for key in ('status','last_year_on_record','fiscal_year_end','computed_due_date','tax_period_evidence'):
            self.assertEqual(getattr(result,key),getattr(expected,key))

    def test_missing_history_does_not_invent_period(self):
        source=(ROOT/'541517707.html').read_text(encoding='utf-8')
        org=c.checker.Organization("America's Charities",'54-1517707')
        with patch.object(c,'hi_attachment_period',side_effect=AssertionError('No annual attachment')), \
             patch.object(c,'irs_period_for_label',side_effect=AssertionError('No state year')):
            result,body=c.hi_direct_details_from_source(org,source,self.url)
        self.assertFalse(getattr(result,'tax_period_evidence',None))
        self.assertIn('2025',body)

    def test_no_ein_or_http_failure_never_becomes_negative(self):
        with patch.object(c,'identity_fetch',side_effect=TimeoutError('public source')) as fetch:
            self.assertIsNone(c.search_hi_direct_details(c.checker.Organization('Control','')))
            fetch.assert_not_called()
            self.assertIsNone(c.search_hi_direct_details(self.org))

    def test_exempt_and_inactive_labels_are_preserved(self):
        source=self.source.replace('<dd>Registered</dd>', '<dd>Exempt</dd>')
        value,period=self.parse(source)
        self.assertIn('Registration Type: Exempt',value[0].raw_status_text)
        period.assert_not_called()
        source=self.source.replace('id="status-holder">Active', 'id="status-holder">Inactive')
        with patch.object(c,'hi_public_filing_period',return_value={
                'ein':'753138664','tax_year_label':2025,'period_begin':'2025-01-01','period_end':'2025-12-31'}):
            result,_=c.hi_direct_details_from_source(self.org,source,self.url)
        self.assertEqual(result.status,'Inactive')

    def test_source_capture_uses_original_browser(self):
        with patch.object(c,'search_hi_direct_details',side_effect=AssertionError('Capture needs browser')) as direct, \
             patch.object(c.checker,'sync_playwright',side_effect=RuntimeError('original capture browser')):
            with self.assertRaisesRegex(RuntimeError,'original capture browser'):
                c.run_state_lookup(self.org.organization_name,self.org.ein,'HI',capture_source_snapshot=True)
        direct.assert_not_called()

    def test_complete_direct_detail_skips_browser(self):
        value,_=self.parse()
        with patch.object(c,'search_hi_direct_details',return_value=value), \
             patch.object(c,'response_data_for_lookup',side_effect=lambda r,*args:r), \
             patch.object(c.checker,'sync_playwright',side_effect=AssertionError('Unneeded browser')):
            self.assertIs(c.run_state_lookup(self.org.organization_name,self.org.ein,'HI'),value[0])

    def test_incomplete_direct_detail_keeps_existing_browser_fallback(self):
        # The sentinel proves the original browser branch is reached; no false
        # negative can be produced from the absent direct URL alone.
        with patch.object(c,'search_hi_direct_details',return_value=None), \
             patch.object(c.checker,'sync_playwright',side_effect=RuntimeError('original browser fallback')) as browser:
            with self.assertRaisesRegex(RuntimeError,'original browser fallback'):
                c.run_state_lookup(self.org.organization_name,self.org.ein,'HI')
        browser.assert_called_once()

if __name__=='__main__': unittest.main()
