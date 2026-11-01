"""Bounded field recognition and fiscal/calendar guards; no live queries."""
import copy,json,sys,time,types,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import registry_snapshot_server as c
FIX=Path(__file__).parent/'fixtures/hi-christian-header'
class FieldPeriod(unittest.TestCase):
    def setUp(self):
        self.rows=json.loads((FIX/'rows.json').read_text())['rows'];self.pic=Image.open(FIX/'header.png');self.addCleanup(self.pic.close)
    def read(self,rows=None,engine=None,ein='226063412',label=2025,deadline=None):
        engine=engine or (lambda *a,**k:([[',20 2026',.96]],None))
        return c.irs_scanned_period_fields(self.pic,self.rows if rows is None else rows,engine,ein,label,'https://state/return.pdf',time.monotonic()+10 if deadline is None else deadline)
    def test_exact_ein_and_fiscal_period_from_observed_rows_and_recognized_field(self):
        result=self.read();self.assertEqual((result['period_begin'],result['period_end']),('2025-07-01','2026-06-30'))
        self.assertFalse(result.get('period_assumed'))
    def test_wrong_ein_label_low_confidence_and_fused_year_remain_unreadable(self):
        self.assertEqual(self.read(ein='999999999'),{});self.assertEqual(self.read(label=2024),{})
        for value,confidence in [(',20 2026',.949),(',202026',.999),('202026',.999),(',20 2099',.999),('unknown',.999)]:
            with self.subTest(value=value,confidence=confidence):self.assertEqual(self.read(engine=lambda *a,**k:([[value,confidence]],None)),{})
    def test_high_confidence_fused_field_must_be_independently_reread(self):
        rows=copy.deepcopy(self.rows);rows[15][2]=.999;calls=[]
        result=self.read(rows,engine=lambda *a,**k:(calls.append(k)or [[',20 2026',.96]],None))
        self.assertEqual(result['period_end'],'2026-06-30');self.assertEqual(len(calls),1);self.assertFalse(calls[0]['use_det'])
        rows[15][1]=',20 2026';calls.clear();self.assertEqual(self.read(rows)['period_end'],'2026-06-30')
    def test_original_deadline_and_two_field_bound_are_enforced(self):
        def denied(*a,**k):raise AssertionError('No OCR after deadline')
        self.assertEqual(self.read(engine=denied,deadline=time.monotonic()-1),{})
        rows=copy.deepcopy(self.rows)
        for i in [12,13,14,15]:rows[i][2]=.94
        count=[]
        def uncertain(*a,**k):count.append(1);return [['7/01',.99]],None
        self.assertEqual(self.read(rows,uncertain),{});self.assertLessEqual(len(count),2)
    def test_unreadable_scanned_override_raises_and_cannot_assume_calendar(self):
        title=[[[[0,0],[50,0],[50,20],[0,20]],'Form 990 Return of Organization Exempt From Income Tax',.999]]
        def ocr(pic,**kw):return ([[',202026',.99]],None) if kw.get('use_det')is False else (self.rows,None)
        with patch.dict(sys.modules,{'rapidocr_onnxruntime':types.SimpleNamespace(RapidOCR=lambda **k:None)}),patch.object(c,'IRS_HEADER_OCR',ocr),patch.object(c,'IRS_HEADER_TITLE_OCR',lambda *a,**k:(title,None)):
            with self.assertRaises(c.FilingPeriodReadIncomplete):c.irs_scanned_header_period([(0,self.pic.copy())],'226063412',2025,'https://state',time.monotonic()+10,require_complete=True)
    def test_valid_text_layer_calendar_path_is_preserved(self):
        text='Form 990 EIN 22-6063412';line='For the 2025 calendar year, or tax year beginning and ending'
        result=c.form990_header_period(text,line,'226063412',2025,'https://state')
        self.assertEqual((result['period_begin'],result['period_end']),('2025-01-01','2025-12-31'))
if __name__=='__main__':unittest.main()
