"""Original retained state PDF pages only; no live queries or reconstruction."""
import base64,hashlib,io,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deployment import state_snapshots as s
import registry_snapshot_server as c
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1]
class OriginalPDFs(unittest.TestCase):
    def test_thirty_actual_retained_ky_dba_records_keep_original_pages(self):
        indexes=json.loads((ROOT/'deployment/source-page-indexes.json').read_text())
        entry=indexes['KY'];reader=PdfReader(ROOT/entry['asset'])
        records=[(i,n) for i,n in entry['record_names'].items() if ' | DBA: ' in n and i in entry['pages']][:30]
        self.assertEqual(len(records),30)
        for ident,name in records:
            with self.subTest(credential=ident),patch.object(c.urllib.request,'urlopen',side_effect=AssertionError('No source queries')):
                result={'organization_name':name,'ein':'123456789','state':'KY','status':'Current','success':True,
                    'matched_registry_name':name,'matched_registry_identifier':ident}
                with s.CaptureRun(name,'123456789','KY') as run:
                    s.downloaded_record(c,result);out=run.finish(result)
                assets=out.get('_worker_source_archives',[]);self.assertEqual(len(assets),1)
                meta,raw=s.validate_asset(assets[0],ein='123456789',state='KY',run_id=assets[0]['run_id'])
                self.assertEqual(meta['kind'],'source_pdf');self.assertEqual(s.render_pdf(meta,raw),raw)
                saved=PdfReader(io.BytesIO(raw));originals=[reader.pages[n] for n in entry['pages'][ident]]
                for page in saved.pages:
                    same=next((source for source in originals if page.get_contents().get_data()==source.get_contents().get_data()),None)
                    self.assertIsNotNone(same)
                    # PDF serialization rounds decimal coordinates by a few
                    # millionths of a point; drawing commands stay byte-exact.
                    for actual,expected in zip(page.mediabox,same.mediabox):
                        self.assertAlmostEqual(float(actual),float(expected),places=4)
    def test_thirty_dba_names_require_both_original_columns(self):
        cohort=json.loads((ROOT/'testing/fixtures/oct19-cohort.json').read_text())[:30]
        for org in cohort:
            legal=org['name'];dba='Distinct Public Program';name=legal+' | DBA: '+dba
            self.assertTrue(s.source_name_present(name,legal+'\n'+dba,'KY'))
            self.assertFalse(s.source_name_present(name,legal,'KY'))
            self.assertFalse(s.source_name_present(name,dba,'KY'))
            self.assertFalse(s.source_name_present(name,legal+'\n'+dba,'NH'))
    def test_nh_record_with_no_published_number_can_use_its_original_page(self):
        name='Revolution Show Ministries';index=json.loads((ROOT/'deployment/source-page-indexes.json').read_text())['NH']
        self.assertTrue(index['pages'].get(''))
        with s.CaptureRun(name,'123456789','NH') as run:
            result={'organization_name':name,'ein':'123456789','state':'NH','status':'Current','success':True,
                'matched_registry_name':name,'matched_registry_identifier':''}
            s.downloaded_record(c,result);out=run.finish(result)
        self.assertEqual(out['_worker_source_archives'][0]['kind'],'source_pdf')
if __name__=='__main__':unittest.main(verbosity=2)
