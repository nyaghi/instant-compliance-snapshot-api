"""A source's indexing year cannot displace an actual verified filing period."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c


class IndexedScanControls(unittest.TestCase):
    def text(self, start='1/1/2020', end='12/31/2020', ein='46-1723968', account='059129'):
        return f'Form PC Attorney General Account # {account} Federal ID # {ein} Report for the Fiscal Period: {start} to {end}'

    def test_older_period_is_opt_in_and_requires_one_exact_ein(self):
        self.assertFalse(c.ma_scanned_form_pc_evidence(self.text(),2022,'059129','461723968'))
        result=c.ma_scanned_form_pc_evidence(self.text(),2022,'059129','461723968',allow_older_period=True)
        self.assertEqual(result['filing_year'],2020);self.assertEqual(result['source_year_label'],2022)
        for text in [self.text(ein='46-1723960'),self.text(account='059120'),
                     self.text()+' Different EIN 98-7654321',
                     self.text(start='1/1/2023',end='12/31/2023')]:
            with self.subTest(text=text):
                self.assertFalse(c.ma_scanned_form_pc_evidence(text,2022,'059129','461723968',allow_older_period=True))

    def test_independent_older_scan_is_reconciled_by_actual_period(self):
        text=self.text(ein='12-3456789',account='012345')
        older=c.ma_scanned_form_pc_evidence(text,2022,'012345','123456789',allow_older_period=True)
        current=dict(filing_year=2022,period_start='1/1/2022',period_end='12/31/2022',
                     filing_status='Submitted',ago_account='012345')
        self.assertEqual(c.ma_latest_distinct_fiscal_period([current,older])['period_end'],'12/31/2022')
        # Genuine overlapping or unreadable periods retain the existing guard.
        self.assertFalse(c.ma_latest_distinct_fiscal_period([current,{**current}]))
        self.assertFalse(c.ma_latest_distinct_fiscal_period([current,{}]))

    def test_real_scan_has_actual_2020_period_despite_2022_index(self):
        page=Mock();response=page.context.request.get.return_value
        response.ok=True;response.body.return_value=(Path(__file__).parent/'fixtures/ma-older-indexed-form-pc.tiff').read_bytes()
        completed={'record':{'ago_account':'059129','ein':'461723968'},
            'filings':{'059129':{'annual_scans':[]}},
            'registration_documents':{'059129':{'annual_scans':[{'year':'2022','title':'FY2022 PC - Form PC/Annual RPT.tiff',
                'url':'https://masscharities.my.site.com/FilingSearch/sfc/servlet.shepherd/document/download/069000000000000AAA'}]}}}
        result=c.ma_read_legacy_form_pc(page,completed,'059129',allow_older_period=True)
        self.assertEqual(result['period_end'],'12/31/2020')
        self.assertEqual(result['filing_year'],2020);self.assertEqual(result['source_year_label'],2022)

    def test_electronic_period_is_not_lost_to_verified_older_paper_index(self):
        page=MagicMock();page.get_by_role.return_value.all_inner_texts.return_value=['2022 Form-PC Data']
        detail=page.expect_popup.return_value.__enter__.return_value.value
        detail.locator.return_value.inner_text.return_value=('AG Charity Number 059129 Filing Year 2022 Filing Status Submitted '
            'Current Fiscal Period Start Date 1/1/2022 Current Fiscal Period End Date 12/31/2022')
        detail.url='https://masscharities.my.site.com/FilingSearch/s/detail/fixture'
        completed={'registration_documents':{'059129':{'annual_scans':[{'year':'2022'}]}}}
        older=c.ma_scanned_form_pc_evidence(self.text(),2022,'059129','461723968',allow_older_period=True)
        with patch.object(c,'ma_read_legacy_form_pc',return_value=older) as read:
            result=c.ma_read_latest_form_pc(page,Mock(),'AG Account Number 059129',completed)
        read.assert_called_once_with(page,completed,'059129',allow_older_period=True)
        self.assertEqual(result['period_end'],'12/31/2022')
        self.assertEqual(result['reconciled_legacy_documents'][0]['filing_year'],2020)


if __name__=='__main__': unittest.main(verbosity=2)
