"""State-hosted group returns: explicit membership, same document, no discovery."""
import io
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c


class GroupReturnControls(unittest.TestCase):
    def setUp(self):
        c.HI_DOCUMENT_PERIOD_CACHE.clear()
        self.block = patch.object(c.urllib.request, 'urlopen', side_effect=AssertionError('Offline fixture only'))
        self.block.start(); self.addCleanup(self.block.stop)

    def url(self, ein='123456789', year=2024):
        return f'https://charity.ehawaii.gov/charity/attachments/irs/{ein}/{year}/return.pdf'

    def document(self, heading='Subordinates for Group Return', member='12-3456789',
                 footer='98-7654321', year=2024):
        out = io.BytesIO(); pdf = canvas.Canvas(out)
        for y, text in [(760,'Form 990 Return of Organization Exempt From Income Tax'),
                        (740,'Group Return EIN 98-7654321'),
                        (720,f'For the {year} calendar year, or tax year beginning 1/1/{year} and ending 12/31/{year}')]:
            pdf.drawString(30,y,text)
        pdf.showPage()
        for y, text in [(760,'Form 990 Item H'),(740,heading),
                        (720,'Name of organization Address EIN'),
                        (700,f'Independent Education Fund 1 Main Street {member}'),
                        (680,f'Group Return EIN {footer}')]:
            pdf.drawString(30,y,text)
        pdf.save(); return out.getvalue()

    def read(self, body, ein='123456789', label=2024):
        return c.hi_group_return_period(body, ein, label, self.url(ein,label), time.monotonic()+10)

    def test_independent_included_subordinate_uses_actual_group_period(self):
        evidence = self.read(self.document())
        self.assertEqual(evidence['ein'],'123456789')
        self.assertEqual(evidence['filing_ein'],'987654321')
        self.assertEqual(evidence['period_end'],'2024-12-31')
        self.assertFalse(evidence.get('period_assumed'))
        self.assertEqual(evidence['membership_pdf_page'],2)

    def test_real_state_attachment_includes_both_independent_subordinate_eins(self):
        body = (Path(__file__).parent/'fixtures/hi-group-return-2024.pdf').read_bytes()
        for ein in ['833051191','474444592']:
            with self.subTest(ein=ein):
                evidence = self.read(body,ein)
                self.assertEqual(evidence['group_return_member_ein'],ein)
                self.assertEqual(evidence['filing_ein'],'320534221')
                self.assertEqual(evidence['membership_pdf_page'],29)
                self.assertEqual(evidence['period_end'],'2024-12-31')
                self.assertTrue(evidence['period_assumed'])
                self.assertIn('estimates',evidence['period_basis'])

    def test_related_entities_or_excluded_subordinates_cannot_supply_period(self):
        for heading in ['Schedule R Related Organizations','Subordinates not included for Group Return',
                        'Subordinates for Group Return - Excluded', 'Other organization EIN references']:
            with self.subTest(heading=heading): self.assertFalse(self.read(self.document(heading=heading)))

    def test_missing_member_or_different_group_footer_is_not_accepted(self):
        self.assertFalse(self.read(self.document(member='12-3456780')))
        self.assertFalse(self.read(self.document(footer='98-7654320')))

    def test_a_second_bundled_return_cannot_share_membership_with_the_first(self):
        from pypdf import PdfReader, PdfWriter
        writer=PdfWriter()
        for document in [self.document(),self.document(year=2023)]:
            for page in PdfReader(io.BytesIO(document)).pages: writer.add_page(page)
        out=io.BytesIO();writer.write(out)
        self.assertFalse(self.read(out.getvalue()))

    def test_wrong_source_identity_year_and_deadline_remain_inconclusive(self):
        body=self.document()
        for url in ['https://example.org/return.pdf',self.url('123456780'),self.url(year=2023)]:
            self.assertFalse(c.hi_group_return_period(body,'123456789',2024,url,time.monotonic()+10))
        self.assertFalse(c.hi_group_return_period(body,'123456789',2024,self.url(),time.monotonic()-1))
        with self.assertRaises(c.FilingPeriodReadIncomplete): self.read(self.document(year=2023))

    def test_hawaii_recovery_fetches_once_and_keeps_existing_date_rules(self):
        ein='833051191'; body=(Path(__file__).parent/'fixtures/hi-group-return-2024.pdf').read_bytes()
        source=f'<div id="irs_2024"></div><a rel="/charity/attachments/irs/{ein}/2024/return.pdf">IRSForm_990</a>'
        page=type('Page',(),{'content':lambda self:source,'url':f'https://charity.ehawaii.gov/charity/{ein}/details.html'})()
        with patch.object(c,'identity_fetch',return_value=body) as fetch, \
             patch.object(c,'irs_period_for_label',side_effect=AssertionError('No supplemental IRS call needed')):
            evidence=c.hi_public_filing_period(page,ein)
        self.assertEqual(fetch.call_count,1)
        self.assertEqual(evidence['membership_pdf_page'],29)
        result=c.checker.StateResult('MS GIFT CURES, INC.',ein,'HI','Current','https://charity.ehawaii.gov/')
        result.raw_status_text='Registration Status: Active | Tax Year: 2024'
        c.annotate_irs_based_state_period(result,evidence)
        self.assertEqual(result.status,'Delinquent')
        self.assertTrue(result.tax_period_evidence['period_assumed'])


if __name__=='__main__': unittest.main(verbosity=2)
