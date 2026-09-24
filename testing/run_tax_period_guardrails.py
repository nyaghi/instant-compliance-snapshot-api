import io,sys,unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c
from reportlab.pdfgen import canvas

def evidence(ein='131624103',start='2024-07-01',end='2025-06-30'):
    return {'ein':ein,'tax_year_label':2024,'period_begin':start,'period_end':end,'source_url':'https://filing',
            'period_basis':'Corresponding return','state_source_url':'https://state'}
def result(state='HI',status='Current'):
    r=c.checker.StateResult('YWCA USA','13-1624103',state,status,'https://state')
    r.raw_status_text='Registration Status: Active' if state=='HI' else 'Yr Last Filed: 2024 | Next Filing Due: 11/15/2025'
    r.matched_registry_name='YWCA USA';r.success=True;return r

class PeriodTests(unittest.TestCase):
    def test_fiscal_year_label_is_not_end_year(self):
        r=c.annotate_irs_based_state_period(result(),evidence())
        self.assertEqual(r.fiscal_year_end,'6/30/2025');self.assertEqual(r.next_required_period,'6/30/2026')
        self.assertEqual(r.computed_due_date,'11/16/2026');self.assertFalse(r.tax_period_evidence['extension_applied'])
    def test_calendar_year_stays_same_period(self):
        r=c.annotate_irs_based_state_period(result('KY'),evidence(start='2024-01-01',end='2024-12-31'))
        self.assertEqual(r.computed_due_date,'5/15/2026')
    def test_source_ein_mismatch_rejected(self):
        self.assertFalse(hasattr(c.annotate_irs_based_state_period(result(),evidence(ein='999999999')),'tax_period_evidence'))
    def test_short_year_does_not_invent_next_calendar(self):
        r=c.annotate_irs_based_state_period(result(),evidence(start='2024-10-01',end='2024-12-31'))
        self.assertFalse(hasattr(r,'tax_period_evidence'));self.assertEqual(c.true_status_from_body(r,''),'Unable to Confirm')
    def test_unreadable_hi_period_does_not_restore_old_year_inference(self):
        r=c.annotate_irs_based_state_period(result(),{'tax_year_label':2024,'period_unconfirmed':True})
        self.assertEqual(c.true_status_from_body(r,''),'Unable to Confirm')
        self.assertIn('Hawaii lists',c.comments_for_result_base(r,'','Unable to Confirm'))
        r=result();r.raw_status_text='Registration Status: Delinquent'
        c.annotate_irs_based_state_period(r,{'tax_year_label':2024,'period_unconfirmed':True})
        self.assertNotEqual(getattr(r,'status_reason',''),'HI_TAX_PERIOD_UNCONFIRMED')
    def test_explicit_adverse_exemption_statuses_preserved(self):
        for status in ['Exempt','Pending','Revoked','Suspended','Not Registered','Closed / Withdrawn / Canceled']:
            r=c.annotate_irs_based_state_period(result(status=status),evidence());self.assertEqual(r.status,status)
        r=result();r.raw_status_text='Registration Status: Delinquent'
        self.assertFalse(hasattr(c.annotate_irs_based_state_period(r,evidence()),'tax_period_evidence'))
    def test_ky_old_due_is_replaced_not_left_in_comment(self):
        r=c.annotate_irs_based_state_period(result('KY'),evidence())
        self.assertNotIn('11/15/2025',r.raw_status_text)
        comment=c.comments_for_result_base(r,'','Upcoming Filing')
        self.assertIn('No IRS extension has been assumed',comment);self.assertIn('state copy when',comment)
    def test_hi_comment_separates_irs_from_state_requirement(self):
        r=c.annotate_irs_based_state_period(result(),evidence())
        comment=c.comments_for_result_base(r,'','Upcoming Filing')
        self.assertIn('10 business days after',comment);self.assertIn('not a separately confirmed Hawaii deadline',comment)
    def test_pdf_8879_period_verified_with_ein(self):
        buffer=io.BytesIO();pdf=canvas.Canvas(buffer)
        pdf.drawString(25,770,'Form 8879-TE')
        pdf.drawString(25,740,'For fiscal year beginning JUL 1, 2024, and ending JUN 30, 2025')
        pdf.drawString(25,710,'YWCA USA INC   EIN 13-1624103');pdf.save()
        r=c.form990_pdf_period(buffer.getvalue(),'13-1624103',2024,'https://state')
        self.assertEqual(r['period_end'],'2025-06-30')
        self.assertEqual(c.form990_pdf_period(buffer.getvalue(),'99-9999999',2024,'https://state'),{})
        self.assertEqual(c.form990_pdf_period(buffer.getvalue(),'13-1624103',2023,'https://state'),{})
    def test_scanned_header_ending_ocr_and_form_title(self):
        buffer=io.BytesIO();pdf=canvas.Canvas(buffer)
        pdf.drawString(25,770,'Return of Organization Exempt From Income Tax')
        pdf.drawString(25,740,'For the 2024 calendar year, or tax year beginning OCT 1, 2024 and endinq SEP 30, 2025')
        pdf.drawString(25,710,'National Marrow Donor Program EIN 84-0865803');pdf.save()
        r=c.form990_pdf_period(buffer.getvalue(),'84-0865803',2024,'https://state')
        self.assertEqual(r['period_end'],'2025-09-30')
    def test_actual_layered_calendar_return_header(self):
        body=(Path(__file__).parent/'fixtures/hi-good-sports-2025/form990-first-page.pdf').read_bytes()
        r=c.form990_pdf_period(body,'75-3138664',2025,'https://state')
        self.assertEqual((r['period_begin'],r['period_end']),('2025-01-01','2025-12-31'))
        self.assertEqual(c.form990_pdf_period(body,'99-9999999',2025,'https://state'),{})
        self.assertEqual(c.form990_pdf_period(body,'75-3138664',2024,'https://state'),{})
    def test_blank_calendar_header_cannot_hide_fiscal_override(self):
        text='Form 990 EIN 75-3138664'
        for line in ['For the 2025 calendar year, or tax year beginning JAN 1 and ending',
                     'For the 2025 calendar year, or tax year beginning and ending DEC 31',
                     'For the 2025 calendar year, or tax year beginning ??? and ending ???',
                     'Tax year 2025']:
            self.assertEqual(c.form990_header_period(text,line,'75-3138664',2025,'https://state'),{})
        line='For the 2025 calendar year, or tax year beginning JUL 1, 2025 and ending JUN 30, 2026'
        self.assertEqual(c.form990_header_period(text,line,'75-3138664',2025,'https://state')['period_end'],'2026-06-30')
    def test_actual_numeric_layered_dates_and_990ez_blank_calendar(self):
        root=Path(__file__).parent/'fixtures/irs-header-formats'
        for file,ein,end in [('camp-kesem-layered.pdf','51-0454157','2025-09-30'),('chemical-coaters-990ez.pdf','83-2985088','2024-12-31')]:
            body=(root/file).read_bytes();r=c.form990_pdf_period(body,ein,2024,'https://state')
            self.assertEqual(r['period_end'],end)
            self.assertEqual(c.form990_pdf_period(body,'99-9999999',2024,'https://state'),{})
    def test_actual_scanned_header_uses_same_row_dates(self):
        from PIL import Image
        path=Path(__file__).parent/'fixtures/irs-header-formats/cnas-8879-header.png'
        r=c.irs_scanned_header_period([(35,Image.open(path))],'208084828',2024,'https://state',c.time.monotonic()+20)
        self.assertEqual((r['period_begin'],r['period_end'],r['pdf_page']),('2024-10-01','2025-09-30',36))
    def test_full_scanned_hawaii_attachment_does_not_assume_calendar_year(self):
        from types import SimpleNamespace
        body=(Path(__file__).parent/'fixtures/irs-header-formats/cnas-2024-full.pdf').read_bytes()
        html='<span id="irs_2024"></span><a rel="/charity/attachments/irs/208084828/2024/return.pdf">Attachment_IRSForm_1</a>'
        page=SimpleNamespace(content=lambda:html,url='https://charity.ehawaii.gov/charity/208084828/details.html')
        # The actual return is on page 36, after scanned cover/financial pages.
        # A single cropped header fixture cannot reveal the cold scan timeout.
        with patch.object(c,'IRS_HEADER_OCR',None),patch.object(c,'IRS_HEADER_TITLE_OCR',None),patch.object(c,'identity_fetch',return_value=body),patch.object(c,'irs_period_for_label',return_value={}) as fallback:
            r=c.hi_public_filing_period(page,'20-8084828')
        self.assertEqual((r['period_begin'],r['period_end'],r['pdf_page']),('2024-10-01','2025-09-30',36))
        self.assertFalse(r.get('period_assumed'));fallback.assert_not_called()
    def test_ocr_deadline_and_low_confidence_fail_closed(self):
        from PIL import Image
        image=Image.new('RGB',(100,100),'white')
        with patch.object(c,'IRS_HEADER_OCR') as ocr:
            self.assertEqual(c.irs_scanned_header_period([(0,image)],'131624103',2024,'https://state',c.time.monotonic()-1),{})
            ocr.assert_not_called()
        rows=[([[0,0],[90,0],[90,10],[0,10]],'8879-TE',.8)]
        with patch.object(c,'IRS_HEADER_TITLE_OCR',return_value=(rows,None)) as ocr:
            self.assertEqual(c.irs_scanned_header_period([(0,Image.new('RGB',(100,100),'white'))],'131624103',2024,'https://state',c.time.monotonic()+2),{})
            self.assertEqual(ocr.call_count,1)
    def test_irs_lag_uses_exact_year_ein_public_filing_not_latest_unrelated(self):
        c.TAX_PERIOD_EVIDENCE_CACHE.clear()
        older=evidence(start='2023-07-01',end='2024-06-30');older['tax_year_label']=2023
        with patch.object(c,'irs_latest_period',return_value=older),patch.object(c,'identity_fetch',return_value=b'<html>public filing</html>') as fetch,patch.object(c,'hi_attachment_period',return_value=evidence()) as attachment:
            r=c.irs_period_for_label('13-1624103',2024,c.time.monotonic()+10)
        self.assertEqual(r['period_end'],'2025-06-30');self.assertEqual(attachment.call_args.args[1:3],('131624103',2024))
        self.assertEqual(fetch.call_args.kwargs['headers']['Accept'],'text/html')
        c.TAX_PERIOD_EVIDENCE_CACHE.clear()
    def test_attachment_url_must_have_same_ein_and_year(self):
        html='<a rel="/charity/attachments/irs/999999999/2024/other.pdf">Attachment_IRSForm_1</a><a rel="/charity/attachments/irs/131624103/2023/old.pdf">Attachment_IRSForm_1</a>'
        with patch.object(c,'identity_fetch') as fetch:
            self.assertEqual(c.hi_attachment_period(html,'13-1624103',2024,c.time.monotonic()+10),{})
        fetch.assert_not_called()
    def test_weekend_and_emancipation_adjustment(self):
        self.assertEqual(c.irs_base_return_due(date(2026,6,30)),date(2026,11,16))
        self.assertEqual(c.irs_base_return_due(date(2022,11,30)),date(2023,4,18))
    def test_or_actual_period_not_shifted(self):
        self.assertEqual(c.or_next_due_from_period_end(date(2024,6,30)),date(2025,11,15))
    def test_ky_calls_exact_state_year(self):
        row=('1001','YWCA USA Inc','2024','')
        with patch.object(c,'load_ky_snapshot_records',return_value=[row]),patch.object(c,'fiscal_year_end_for_ein',return_value=(6,30)),patch.object(c,'irs_period_for_label',return_value=evidence()) as period:
            r=c.search_ky_strict_snapshot(c.checker.Organization('YWCA USA Inc','13-1624103'))
        self.assertEqual(period.call_args.args[1],2024);self.assertEqual(r.computed_due_date,'11/16/2026')
    def test_ma_extension_only_when_evidence_says_applied(self):
        r=result('MA');r.ma_filing_evidence={'automatic_extension_inferred':True,'base_due':'5/15/2026','extended_due':'11/15/2026'}
        with patch.object(c,'comments_for_result_base',return_value='Base explanation.'):
            self.assertIn('Automatic extension applied:',c.comments_for_result(r,'','Upcoming Filing'))
            r.ma_filing_evidence={}
            self.assertNotIn('Automatic extension applied:',c.comments_for_result(r,'','Delinquent'))
    def test_md_extension_comment_does_not_change_status_or_query_profile(self):
        r=result('MD');r.raw_status_text='Current | Last Report 2025'
        context={'due_date':date(2026,11,15),'extended_due_date':date(2026,11,15),'base_due_date':date(2026,6,30)}
        with patch.dict(c.PUBLIC_PROFILE_CACHE,{'131624103':{}}),patch.object(c,'filing_context',return_value=context),patch.object(c,'comments_for_result_base',return_value='Base explanation.'):
            self.assertIn('Automatic extension applied: 6/30/2026',c.comments_for_result(r,'','Upcoming Filing'))
            self.assertEqual(r.status,'Current')
            r.raw_status_text='Pending'
            self.assertNotIn('Automatic extension applied:',c.comments_for_result(r,'','Pending'))

if __name__=='__main__':unittest.main()
