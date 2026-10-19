"""Real local headless rendering, modeled source responses, zero live searches."""
from pathlib import Path
import json,sys,time,unittest,html,tempfile,io
import faulthandler
from unittest.mock import patch
from types import SimpleNamespace
from datetime import date
from contextlib import nullcontext
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c
from deployment import state_snapshots as s
from deployment.queue_engine import execute
from pypdf import PdfReader
COHORT=json.loads((Path(__file__).parent/'fixtures/oct19-cohort.json').read_text())[:30]
HERE=Path(__file__).resolve().parents[2]
class Today(date):
    @classmethod
    def today(cls):return cls(2026,10,19)

class BrowserBoundary(unittest.TestCase):
    def test_thirty_real_headless_capture_original_lookup_worker_and_pdf(self):
        timings=[];counts=[]
        with tempfile.TemporaryDirectory() as temp, c.checker.sync_playwright() as p:
            browser=p.chromium.launch(headless=True);store=s.SQLiteStore(Path(temp)/'snapshots.sqlite')
            class Lease:
                def __getattr__(self,k):return getattr(browser,k)
                def close(self):pass
                def new_context(self,**kwargs):return browser.new_context(**kwargs)
            try:
                for org in COHORT:
                    print('Local browser fixture:',org['name'],flush=True)
                    faulthandler.dump_traceback_later(20)
                    requests=[]
                    def source(page,target,state):
                        url='https://justice.oregon.gov/Charities/Charity/details?charityID=80579'
                        body=f'''<html><body><h1>LOCAL REPLAY FIXTURE - NOT A LIVE REGISTRY CAPTURE</h1>
                        <h2>{html.escape(org['name'])}</h2><p>Federal EIN: {html.escape(org['ein'])}</p>
                        <p>Status: Registered</p><p>Registration: #69938</p>
                        <p>Reports 2024 Fiscal Year Beginning 7/1/2024 and Ending 6/30/2025</p>
                        <p>Report Year: 2024</p></body></html>'''
                        def fulfill(route):
                            requests.append(route.request.url)
                            if route.request.url!=url:raise AssertionError('Unmodeled source request')
                            route.fulfill(status=200,body=body,content_type='text/html')
                        page.route('**/*',fulfill);page.goto(url)
                        ext=SimpleNamespace(status='Upcoming Filing',raw_status_text='Status: Registered | Latest Report Year: 2024 | Fiscal Year End: 6/30/2025 | Next Due: 11/15/2026',
                            success=True,matched_registry_name=org['name'],matched_registry_identifier='69938',source_url=url)
                        return c.copy_external_result(target,'OR',ext)
                    job={'state':'OR','version':c.APP_VERSION,'payload':{'ein':org['ein'],'organization_name':org['name'],'alternate_names':[],'mode':'standard'}}
                    started=time.perf_counter()
                    with patch.object(c,'date',Today),patch.object(c,'trial_identity',return_value={'origin':'https://fixture.onrender.com'}),patch.object(c,'or_snapshot_result_for_ein',return_value=None),patch.object(c,'launch_lookup_browser',side_effect=lambda *a,**kw:s.BrowserCaptureProxy(Lease())),patch.object(c,'search_bundled_extension_state',side_effect=source),patch.object(c,'reconciled_registry_address',return_value={'decision':'corroborated'}),patch.object(c,'known_names_for_ein',return_value=[]),patch.object(c.urllib.request,'urlopen',side_effect=AssertionError('No live source HTTP in local replay')):
                        with patch.object(c.checker,'sync_playwright',return_value=nullcontext(p)),patch.dict(c.os.environ,{'CE_FINAL_FOUR_CHILD':'1'}):
                            result=execute(c,job)
                    self.assertEqual(result['status'],'Upcoming Filing',result)
                    self.assertEqual(result['evidence_capture'],'captured',result)
                    assets=result.get('_worker_source_archives',[]);self.assertEqual(len(assets),1)
                    self.assertEqual(assets[0]['kind'],'image')
                    with patch.object(s,'PostgresStore',return_value=store):result=s.persist_worker_result(SimpleNamespace(pool=None),result,job)
                    self.assertTrue(result['evidence_url']);self.assertNotIn('_worker_source_archives',result)
                    ident=result['evidence_url'].split('/')[-1][:-4]
                    meta,pdf=s.saved_pdf(ident,store);self.assertEqual(meta['identifier'],'69938')
                    self.assertEqual(len(PdfReader(io.BytesIO(pdf)).pages),1)
                    self.assertEqual(PdfReader(io.BytesIO(pdf)).pages[0].extract_text(),'')
                    timings.append({'name':org['name'],'ein':org['ein'],'seconds':round(time.perf_counter()-started,4),'capture_ms':result['evidence_capture_ms']})
                    counts.append(len(requests));self.assertEqual(len(requests),1)
                    faulthandler.cancel_dump_traceback_later()
            finally:browser.close()
        (HERE/'browser-boundary-results.json').write_text(json.dumps({'organizations':30,'source_requests_per_fixture':counts,'timings':timings,'scope':'Real isolated headless browser and worker/HTTP/PDF code with modeled source documents, not live registry performance.'},indent=2))

if __name__=='__main__':unittest.main(verbosity=2)
