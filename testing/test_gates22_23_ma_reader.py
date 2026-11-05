"""Replay retained original TIFF and actual OCR through reader/public status.

Record/URL IDs below are fixture bindings; the TIFF, EIN, name and OCR output
are retained source material. Live selected-record binding remains a live gate.
"""
import json,sys,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,Mock,patch
import registry_snapshot_server as m

class Reader(unittest.TestCase):
    def test_observed_ocr_reaches_latest_form_reader_and_public_status(self):
        root=Path(__file__).parent/'fixtures/gates22-23'
        lines=json.loads((root/'cleveland-ma-ocr-lines.json').read_text(encoding='utf-8'))
        org=m.checker.Organization('The Cleveland Clinic Foundation','340714585')
        url='https://masscharities.my.site.com/FilingSearch/sfc/servlet.shepherd/document/download/069000000000001AAA'
        record={'ago_account':'046070','ein':org.ein,'name':'THE CLEVELAND CLINIC FOUNDATION',
                'record_id':'a09000000000001AAA','registry_status':'In-Progress'}
        completed={'record':record,'filings':{'046070':{'annual_scans':[
            {'year':'2020','title':'FY2020 PC - Form PC/Annual RPT.tiff','url':url}], 'document_years':['2020']}},
            'registration_documents':{'046070':{'annual_scans':[]}}}
        page=MagicMock();page.get_by_role.return_value.all_inner_texts.return_value=['2020 FY2020 PC - Form PC/Annual RPT']
        page.locator.return_value.inner_text.return_value='AG Account Number 046070'
        response=page.context.request.get.return_value;response.ok=True
        response.body.return_value=(root/'cleveland-ma-2020.tiff').read_bytes()
        result=m.checker.StateResult(org.organization_name,org.ein,'MA','Unable to Confirm',url)
        with patch.dict(sys.modules,{'rapidocr_onnxruntime':SimpleNamespace(RapidOCR=Mock())}), \
             patch.object(m,'_MA_LEGACY_OCR',return_value=(lines,0)):
            evidence=m.ma_read_latest_form_pc(page,result,'AG Account Number 046070',completed)
        self.assertEqual(evidence['period_start'],'1/1/2020')
        self.assertEqual(evidence['period_end'],'12/31/2020')
        self.assertEqual(evidence['ago_account'],'046070')
        self.assertTrue(evidence['legacy_scanned_form_pc'])
        result=m.annotate_ma_visible_form_pc_due(result,evidence)
        result.matched_registry_name=org.organization_name
        with patch.object(m,'trial_identity',return_value=False):
            public=m.response_data_for_lookup(result,result.raw_status_text,org,org.organization_name,org.ein,'MA',time.perf_counter())
        self.assertEqual(public['status'],'Delinquent');self.assertEqual(public['last_year_on_record'],2020)
        self.assertEqual(public['ma_filing_evidence']['period_end'],'12/31/2020')
        self.assertIn('2022',public['computed_due_date'])

if __name__=='__main__':unittest.main(verbosity=2)
