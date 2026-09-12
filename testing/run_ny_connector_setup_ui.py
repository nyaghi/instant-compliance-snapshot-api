"""Rendered ready/missing setup states, including the real Tailwind cascade.

Only the public Tailwind stylesheet compiler is fetched. All app/registry routes
are fixtures. No extension installation or registry check is performed.
"""
import json,subprocess,sys,unittest
from pathlib import Path
from playwright.sync_api import sync_playwright
WORK=Path(__file__).resolve().parents[1]
OUT=WORK.parents[1]/'outputs/fresh45-fixes-20260912/setup-ui'
ORIGIN='https://staging.compliance-express.com'

class SetupUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OUT.mkdir(parents=True,exist_ok=True)
        cls.p=sync_playwright().start();cls.browser=cls.p.chromium.launch(headless=True)
        cls.legacy=subprocess.check_output(['git','show','e4a64b5:web-staging/index.html'],cwd=WORK).decode('utf-8')
    @classmethod
    def tearDownClass(cls):cls.browser.close();cls.p.stop()
    def page(self,ready,guide=False,legacy=False,width=1280,outdated=False):
        context=self.browser.new_context(viewport={'width':width,'height':1000},permissions=['clipboard-read','clipboard-write'])
        self.addCleanup(context.close)
        context.add_init_script('''window.addEventListener('message', event=>{
          const m=event.data;if(event.source===window&&m?.channel==='cc-ny-staging-v1'&&m.direction==='request'&&m.action==='ping')
            window.postMessage({channel:m.channel,direction:'response',id:m.id,ok:READY,version:VERSION,capabilities:CAPABILITIES},location.origin);
        });'''.replace('READY',json.dumps(ready)).replace('VERSION',json.dumps('0.1.2' if outdated else '0.2.0')).replace('CAPABILITIES',json.dumps(['lookup-tab-v1','verification-retry-v1'] if outdated else ['lookup-tab-v1','verification-retry-v1','search-verification-retry-v1','search-schema-errors-v1','nullable-ein-v1','queue-v1'])))
        def route(r):
            from urllib.parse import urlparse
            u=urlparse(r.request.url)
            if u.hostname=='cdn.tailwindcss.com':r.continue_();return
            if u.hostname!='staging.compliance-express.com':r.abort();return
            if u.path=='/ny-connector.js':r.fulfill(content_type='application/javascript',body=(WORK/'web-staging/ny-connector.js').read_text(encoding='utf-8'));return
            if u.path.endswith('.png'):r.fulfill(content_type='image/png',body=(WORK/'web-staging/connector/charityclarity.png').read_bytes());return
            if u.path not in ['/','/connector/']:r.abort();return
            body=(WORK/'web-staging/connector/index.html').read_text(encoding='utf-8') if guide else self.legacy if legacy else (WORK/'web-staging/index.html').read_text(encoding='utf-8')
            r.fulfill(content_type='text/html',body=body)
        context.route('**/*',route)
        page=context.new_page();page.goto(ORIGIN+('/connector/' if guide else '/'))
        if not guide:
            # Wait for the real CSS compiler; missing CSS masked the original bug.
            page.wait_for_function("getComputedStyle(document.querySelector('#appShell')).display === 'none'",timeout=30000)
            page.locator('#stagingEmail').fill('fixture@compliance-express.com')
            page.locator('#stagingPasscode').fill('fixture-only');page.locator('#stagingUnlockButton').click()
        page.wait_for_function("document.querySelector('#nyConnectorSetup').dataset.state === '"+('update' if outdated else 'ready' if ready else 'missing')+"'")
        return page
    def test_previous_markup_reproduces_visible_hidden_link(self):
        page=self.page(True,legacy=True)
        self.assertTrue(page.locator('[data-connector-install]').evaluate('(e)=>e.hidden'))
        self.assertTrue(page.locator('[data-connector-install]').is_visible())
    def test_ready_main_has_no_install_link(self):
        page=self.page(True)
        self.assertFalse(page.locator('[data-connector-install]').is_visible())
        self.assertEqual(page.get_by_role('link',name='Set up New York in 3 steps').count(),0)
        page.locator('#nyConnectorSetup').screenshot(path=str(OUT/'main-ready.png'))
    def test_missing_main_offers_three_step_setup(self):
        page=self.page(False)
        self.assertTrue(page.get_by_role('link',name='Set up New York in 3 steps').is_visible())
        page.locator('#nyConnectorSetup').screenshot(path=str(OUT/'main-missing.png'))
    def test_missing_guide_has_three_steps_and_working_copy_button(self):
        page=self.page(False,guide=True)
        self.assertEqual(page.locator('ol > li').count(),3)
        self.assertTrue(page.get_by_role('link',name='Download connector ZIP').is_visible())
        self.assertFalse(page.locator('[data-connector-ready]').is_visible())
        page.get_by_role('button',name='Copy address').click()
        self.assertEqual(page.evaluate('navigator.clipboard.readText()'),'chrome://extensions')
        self.assertIn('Extract all',page.locator('ol > li').first.inner_text())
        page.screenshot(path=str(OUT/'guide-missing-desktop.png'),full_page=True)
    def test_ready_guide_shows_done_without_download_or_install_steps(self):
        page=self.page(True,guide=True)
        self.assertTrue(page.get_by_role('heading',name='You’re all set').is_visible())
        self.assertFalse(page.locator('ol').is_visible())
        self.assertEqual(page.get_by_role('link',name='Download connector ZIP').count(),0)
        self.assertEqual(page.get_by_role('link',name='Return to CharityClarity').count(),1)
        page.screenshot(path=str(OUT/'guide-ready-desktop.png'),full_page=True)
    def test_missing_guide_fits_mobile_width(self):
        page=self.page(False,guide=True,width=390)
        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
        self.assertTrue(page.get_by_role('button',name='Copy address').is_visible())
        page.screenshot(path=str(OUT/'guide-missing-mobile.png'),full_page=True)

    def test_old_connector_requires_update_on_main_and_guide(self):
        page=self.page(True,outdated=True)
        self.assertTrue(page.get_by_role('link',name='Update New York in 3 steps').is_visible())
        self.assertNotIn('is ready',page.locator('#nyConnectorSetup').inner_text())
        guide=self.page(True,guide=True,outdated=True)
        self.assertEqual(guide.locator('ol > li').count(),3)
        self.assertTrue(guide.get_by_role('heading',name='Reload the connector in Chrome').is_visible())
        self.assertFalse(guide.get_by_role('heading',name='Add the folder to Chrome').is_visible())
        self.assertTrue(guide.get_by_role('link',name='Download connector ZIP').is_visible())
        self.assertFalse(guide.locator('[data-connector-ready]').is_visible())
        guide.screenshot(path=str(OUT/'guide-update-desktop.png'),full_page=True)

if __name__=='__main__':unittest.main(verbosity=2)
