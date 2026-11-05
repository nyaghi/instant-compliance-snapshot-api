"""Packaged IL readiness/capture and DC corporate-link steps in offline Chromium."""
import html,json,subprocess,time,unittest
from pathlib import Path
from playwright.sync_api import sync_playwright
import registry_snapshot_server as m
from deployment.state_snapshots import il_selected_detail_snapshot
ROOT=Path(__file__).resolve().parents[1]

class Render(unittest.TestCase):
    def test_il_loaded_missing_fein_and_existing_fein_original_fields(self):
        source=(ROOT/'deployment/staging_connector/registry-content.js').read_text(encoding='utf-8')
        marker='  chrome.runtime.onMessage.addListener('
        self.assertEqual(source.count(marker),1)
        source=source.replace(marker,'  window.localIl={open:ilOpenSelectedDetail,fields:snapshotSummaryFields};\n'+marker)
        names=[r['name'] for r in json.loads((ROOT/'testing/fixtures/oct19-cohort.json').read_text(encoding='utf-8'))[:30]]
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                for index,name in enumerate(names):
                    context=browser.new_context(viewport={'width':1280,'height':1000})
                    context.route('**/*',lambda route:route.fulfill(content_type='text/html',body='<p>LOCAL TEST ONLY</p>'))
                    page=context.new_page();page.goto(m.IL_GA_SOURCES['IL'])
                    fein='' if index%2==0 else '<h4>FEIN: 123456789</h4>'
                    page.set_content('<p>LOCAL MODELED FIXTURE — NOT STATE EVIDENCE</p><button title="View Details" onclick="document.querySelector(\'#KendoWindowLevel1\').hidden=false">View Details</button><div id="KendoWindowLevel1" hidden><h2>'+html.escape(name)+'</h2><h4>CO Number: 01100573</h4>'+fein+'<h4>Status: Good Standing</h4><h4>Registration Date: 10/02/2025</h4><h4>Annual Report Due Date: 12/31/2026</h4><ul id="DetailsTabStrip"><li>Annual Financials (2)</li></ul></div>')
                    page.evaluate("window.chrome={runtime:{id:'local',onMessage:{addListener(){}}}}")
                    page.add_script_tag(content=source)
                    started=time.monotonic()
                    result=page.evaluate("async()=>await localIl.open({state:'IL',identifier:'01100573'},document.body,()=>{})")
                    self.assertLess(time.monotonic()-started,2)
                    fields=page.evaluate("()=>localIl.fields(document.querySelector('#KendoWindowLevel1')).map(e=>e.innerText)")
                    self.assertIn('Annual Report Due Date: 12/31/2026',fields)
                    self.assertEqual(il_selected_detail_snapshot({'identifier':'01100573'},result,m.IL_GA_SOURCES['IL'],result['body'],'123456789'),('01100573',name))
                    page.evaluate("document.querySelector('#DetailsTabStrip').remove()")
                    if not fein:self.assertIsNone(page.evaluate("()=>localIl.fields(document.querySelector('#KendoWindowLevel1'))"))
                    context.close()
            finally:browser.close()

    def test_dc_only_clicks_exact_link_and_reads_fitted_entity_profile(self):
        step=subprocess.check_output(['node','-e',"process.stdout.write(require('./deployment/staging_connector/dc-boss-source.js').pageStep.toString())"],cwd=ROOT,text=True)
        text=(ROOT/'testing/fixtures/gate25/dc-corporate.txt').read_text(encoding='utf-8')
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                context=browser.new_context(viewport={'width':1280,'height':1600});calls=[]
                labels=['Record Name','Entity Type','Election Type','Initial File No.','Entity Status','Street Address','Mailing Address','Entity Email','File Date','Purpose']
                lines=[x.strip() for x in text.splitlines() if x.strip()];positions=[lines.index(k) for k in labels]
                markup='<main><h1>LOCAL MODELED CORPORATE FIXTURE</h1>'+''.join('<div class="readonly"><p>'+k+'</p><p>'+html.escape(' '.join(lines[positions[i]+1:positions[i+1]]))+'</p></div>' for i,k in enumerate(labels[:-1]))+'</main>'
                def route(r):
                    calls.append(r.request.url)
                    if r.request.url.endswith('/license-details'):
                        r.fulfill(content_type='text/html',body='<a href="https://boss.dc.gov/business/info">N0000001384</a>')
                    elif r.request.url=='https://boss.dc.gov/business/info':r.fulfill(content_type='text/html',body=markup)
                    else:raise AssertionError('No live traffic')
                context.route('**/*',route);page=context.new_page();page.goto('https://boss.dc.gov/licensing/license-details')
                self.assertEqual(page.evaluate(step,{'phase':'corporate_open','d':{},'linkedIdentifier':'N9999999999'})['error'],'corporate_link_not_unique')
                page.evaluate(step,{'phase':'corporate_open','d':{},'linkedIdentifier':'N0000001384'});page.wait_for_url('https://boss.dc.gov/business/info')
                proof=page.evaluate(step,{'phase':'corporate_position','d':{}})
                self.assertTrue(proof['fit']);self.assertIn('SUNDANCE INSTITUTE',proof['text']);self.assertEqual(len(calls),2)
                context.close()
            finally:browser.close()

if __name__=='__main__':unittest.main(verbosity=2)
