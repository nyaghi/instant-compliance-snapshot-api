"""Original DOM pixels, signed identity context, and stale-image rejection offline."""
import copy,hashlib,json,time,unittest
from pathlib import Path
from unittest.mock import patch
import registry_snapshot_server as c
from deployment import nj_unnumbered_review as n,state_snapshots as s
F=Path(__file__).parent/'fixtures'
DATA=json.loads((F/'nj-christian-unnumbered.json').read_text(encoding='utf-8'))['modeled_response']
# Public DOM is retained verbatim. These CSS dimensions and the input are modeled.
HTML='''<style>body{font:16px Arial;margin:20px}[role=grid]{width:1500px}
[role=row],[data-automationid=DetailsRowFields]{display:flex}
[role=gridcell]{box-sizing:border-box;padding:8px;flex-shrink:0;overflow:hidden}
button{font:inherit;white-space:nowrap;max-width:100%;overflow:hidden;text-overflow:ellipsis;border:0;background:white}
[data-automationid=DetailsRow]{height:42px;overflow:hidden;border-bottom:1px solid #ccc}</style>
<h1>Charity Registration — public search</h1><input placeholder="Search" value="Christian Research Institute">'''+(F/'nj-christian-grid.html').read_text(encoding='utf-8')

class UnnumberedPixels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=c.checker.sync_playwright().start();cls.browser=cls.p.chromium.launch(headless=True)
    @classmethod
    def tearDownClass(cls):cls.browser.close();cls.p.stop()
    def setUp(self):
        self.context=self.browser.new_context(viewport={'width':1680,'height':927});self.addCleanup(self.context.close)
        self.page=self.context.new_page();self.requests=[]
        def route(r):
            self.requests.append(r.request.url)
            if r.request.url==n.URL:r.fulfill(status=200,content_type='text/html; charset=utf-8',body=HTML)
            else:r.abort()
        self.page.route('**/*',route);self.page.goto(n.URL)
        self.data=copy.deepcopy(DATA);self.page._cc_nj_query_incomplete=False
        self.page._cc_nj_completed_data=self.data;self.page._cc_nj_query_diagnostic={'query':'Christian Research Institute'}
        self.org=c.checker.Organization('Christian Research Institute Inc.','226063412')
        self.run=s.CaptureRun(self.org.organization_name,self.org.ein,'NJ')
        token=s.CURRENT.set(self.run);self.addCleanup(s.CURRENT.reset,token)
        token=s.DEADLINE.set(time.monotonic()+15);self.addCleanup(s.DEADLINE.reset,token)
        token=c.NJ_NAME_QUERY_DEADLINE.set(time.monotonic()+12);self.addCleanup(c.NJ_NAME_QUERY_DEADLINE.reset,token)
        self.row={'state':'NJ','ein':self.org.ein,'organization_name':self.org.organization_name,
            'status':'Needs Review','success':False,'_worker_identity_review':{'records':[{
            'name':'CHRISTIAN RESEARCH INSTITUTE','identifier':'','status':'Exempt','url':n.URL}],'search_complete':False}}
    def photo(self):n.capture(c,self.page,self.org,self.data)
    def test_retained_name_is_fully_visible_and_original_pixels_bind_to_review_row(self):
        self.photo();self.assertEqual(len(self.run.documents),1)
        result=self.run.finish(self.row);self.assertEqual(result['evidence_capture'],'captured')
        asset=result['_worker_source_archives'][0];self.assertEqual(asset['record_name'],'CHRISTIAN RESEARCH INSTITUTE');self.assertEqual(asset['identifier'],'')
        self.assertEqual(self.requests,[n.URL]);self.assertEqual(self.run.visual_adapter_facts[-1]['outcome'],'captured')
        expected={k:str(next(a['DisplayValue']for a in self.data['Records'][0]['Attributes']if a['Name']==k)or'')for k in n.KEYS}
        view=self.page.evaluate(n.VIEW,{'expected':expected,'query':'Christian Research Institute','prepare':False});self.assertTrue(view['name_fits']);self.assertEqual(view['fields'],expected)
        # Generic context-close photography must not replace the proven image.
        self.run.page(self.page);self.assertEqual(len(self.run.documents),1)
    def test_wrong_query_changed_row_and_incomplete_response_do_not_produce_an_asset(self):
        for action in ['wrong_query','wrong_name','partial','other_ein']:
            with self.subTest(action=action):
                if action=='wrong_query':self.page.locator('input').fill('Unrelated')
                elif action=='wrong_name':self.page.locator('input').fill('Christian Research Institute');self.page.locator('[data-automation-key=name] button').evaluate("el=>el.textContent='Unrelated'")
                elif action=='partial':self.data['MoreRecords']=True
                else:self.data['MoreRecords']=False;next(a for a in self.data['Records'][0]['Attributes']if a['Name']=='crsm_federalein')['DisplayValue']='999999999'
                self.photo();self.assertEqual(self.run.documents,[])
        self.assertNotIn('_worker_source_archives',self.run.finish(self.row))
    def test_changed_during_photo_rejects_original_and_generic_fallback(self):
        original=self.page.screenshot
        def changed(**kwargs):
            image=original(**kwargs);self.page.locator('[data-automation-key=name] button').evaluate("el=>el.textContent='Different Charity'");return image
        with patch.object(self.page,'screenshot',side_effect=changed) as shot:self.photo()
        self.assertEqual(shot.call_count,1)
        self.assertEqual(self.run.documents,[])
        self.run.document(n.URL,original(type='jpeg'),'image','CHRISTIAN RESEARCH INSTITUTE Exempt')
        self.assertNotIn('_worker_source_archives',self.run.finish(self.row))
    def test_transient_name_reflow_recaptures_same_candidate_and_only_keeps_second_image(self):
        original=self.page.screenshot
        images=[]
        def reflow(**kwargs):
            images.append(original(**kwargs))
            if len(images)==1:
                self.page.locator('[data-automation-key=name] button').evaluate("el=>{el.style.width='2000px';el.style.maxWidth='none';}")
                # Distinguish the two images without changing any candidate value.
                self.page.locator('h1').evaluate("el=>el.style.color='blue'")
            return images[-1]
        with patch.object(self.page,'screenshot',side_effect=reflow):self.photo()
        self.assertEqual(len(images),2)
        self.assertNotEqual(images[0],images[1])
        self.assertEqual(len(self.run.documents),1)
        self.assertEqual(set(self.run.nj_unnumbered_image_bindings),{hashlib.sha256(images[1]).hexdigest()})
        self.assertEqual(self.run.visual_adapter_facts[-1]['capture_attempts'],2)
        self.assertEqual(self.run.finish(self.row)['evidence_capture'],'captured')
    def test_exhausted_allowance_never_takes_photo_or_reuses_unbound_image(self):
        token=c.NJ_NAME_QUERY_DEADLINE.set(time.monotonic()-.1)
        try:
            with patch.object(self.page,'screenshot',side_effect=AssertionError('No late photograph')):self.photo()
        finally:c.NJ_NAME_QUERY_DEADLINE.reset(token)
        self.assertEqual(self.run.visual_adapter_facts[-1]['outcome'],'deadline_reserve');self.assertEqual(self.run.documents,[])

if __name__=='__main__':unittest.main()
