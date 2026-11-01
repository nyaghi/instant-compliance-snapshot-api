"""Actual packaged source UI steps against intercepted public-route fixtures."""
import html,json,os,subprocess,unittest
from pathlib import Path
from playwright.sync_api import sync_playwright
from testing.dc_period_frontend_cases import cases
from testing.test_dc_period_reconciliation import F
URL='https://boss.dc.gov/business/business-license-search'
DETAIL='https://boss.dc.gov/licensing/license-details'
ROOT=Path(__file__).resolve().parents[1]
class PeriodBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases=cases();cls.step=subprocess.check_output(['node','-e',"process.stdout.write(require('./deployment/staging_connector/dc-boss-source.js').pageStep.toString())"],cwd=ROOT,text=True)
        cls.p=sync_playwright().start();cls.browser=cls.p.chromium.launch(headless=True)
    @classmethod
    def tearDownClass(cls):cls.browser.close();cls.p.stop()
    def page(self,case,*,wrong=None):
        d=case['base']['desktop_evidence_request'];fields={**F['fields'],'Licensee':case['update']['dc_source_reconciliation']['source_name'],'License Number':d['identifier']}
        rowname='Other Foundation'if wrong=='name'else fields['Licensee']
        number='999999999999'if wrong=='number'else d['identifier']
        activity='Charitable Exempt'if wrong=='activity'else'Charitable Solicitation'
        row='<tr><td class="mat-column-licenseNumber">'+number+'</td><td class="mat-column-licenseeName"><a href="'+DETAIL+'">'+html.escape(rowname)+'</a></td><td class="mat-column-licenseActivity">'+activity+'</td></tr>'
        source='''<h1>LOCAL MODELED FIXTURE — NOT STATE EVIDENCE</h1>
<button id="entityApplicantType" onclick="document.getElementById('options').hidden=false">Business Name</button>
<div id="options" hidden><button role="option" onclick="document.getElementById('entityApplicantType').textContent=this.textContent;this.parentElement.hidden=true">License Number</button></div>
<input id="searchValue_no_autofill_123">
<mat-radio-button><label><input type="radio" name="compare" checked>Contains</label></mat-radio-button>
<mat-radio-button><label><input type="radio" name="compare">Exact Match</label></mat-radio-button>
<button aria-label="Search records" onclick="document.getElementById('receipt').textContent=document.getElementById('entityApplicantType').textContent+'|'+document.querySelector('input[id^=searchValue]').value+'|'+document.querySelector('input[type=radio]:checked').closest('mat-radio-button').innerText;document.getElementById('results').hidden=false">Search</button>
<p id="receipt"></p><div id="results" hidden><button role="tab" aria-selected="true">Licensing Results</button><table aria-label="grid-table">'''+row+(row if wrong=='duplicate'else'')+'</table></div>'
        detail='<h1>LOCAL MODELED FIXTURE — NOT STATE EVIDENCE</h1><h2>License Information</h2>'+''.join('<p>'+html.escape(k)+'</p><p>'+html.escape(v)+'</p>'for k,v in fields.items())+'<h2>Licensee Information</h2>'
        context=self.browser.new_context(viewport={'width':1280,'height':1100});self.addCleanup(context.close);requests=[]
        def route(r):
            requests.append(r.request.url)
            if r.request.url not in {URL,DETAIL}:raise AssertionError('No live request allowed')
            r.fulfill(status=200,content_type='text/html; charset=utf-8',body=source if r.request.url==URL else detail)
        context.route('**/*',route);page=context.new_page();page.goto(URL)
        return context,page,d,requests
    def search(self,page,d):
        phase='type'
        for _ in range(6):
            result=page.evaluate(self.step,{'phase':phase,'d':d})
            if result.get('error'):return result
            phase=result.get('next',phase)
            if phase=='row':break
        self.assertEqual(phase,'row')
        self.assertEqual(page.locator('#receipt').inner_text(),'License Number|'+d['identifier']+'|Exact Match')
        return page.evaluate(self.step,{'phase':'row','d':d})
    def test_thirty_exact_license_workflows_select_one_bound_row_and_retain_original_pixels(self):
        texts=[]
        for i,case in enumerate(self.cases):
            context,page,d,requests=self.page(case)
            with page.expect_navigation(wait_until='domcontentloaded'):result=self.search(page,d)
            self.assertEqual(result,{'next':'metadata'});metadata=page.evaluate(self.step,{'phase':'capture_position','d':d})
            self.assertEqual(metadata['url'],DETAIL);self.assertEqual(requests,[URL,DETAIL])
            image=page.screenshot(type='jpeg',full_page=True)
            texts.append({'d':d,'url':metadata['url'],'text':metadata['text']})
            if i==0 and os.environ.get('CC_DC_LOCAL_RESULTS'):
                Path(os.environ['CC_DC_LOCAL_RESULTS'],'MODELED-EXACT-LICENSE.jpg').write_bytes(image)
            context.close()
        code="const fs=require('fs'),a=require('./deployment/staging_connector/dc-boss-source.js');const x=JSON.parse(fs.readFileSync(0,'utf8'));if(!x.every(r=>a.fields(r.url,r.text,r.d)))process.exit(1);console.log(x.length)"
        r=subprocess.run(['node','-e',code],cwd=ROOT,input=json.dumps(texts),capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout.strip(),'30')
    def test_wrong_or_nonunique_record_never_opens_a_detail(self):
        for wrong in ['name','number','duplicate','activity']:
            context,page,d,requests=self.page(self.cases[0],wrong=wrong);r=self.search(page,d)
            self.assertEqual(r,{'error':'selected_license_not_unique_or_absent'});self.assertEqual(requests,[URL]);context.close()

if __name__=='__main__':unittest.main()
