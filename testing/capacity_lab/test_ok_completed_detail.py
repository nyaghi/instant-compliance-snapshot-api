"""Selected completed document required; identity/status interpretation unchanged."""
import ast, os, subprocess, time, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from playwright.sync_api import sync_playwright
import registry_snapshot_server as m
from testing.capacity_lab.ok_detail_scope import strip_ok_completed_detail

SETTINGS={'PUBLIC_BASE_URL':'https://instant-compliance-snapshot-api-hn4v.onrender.com',
          'CE_LAB_OK_COMPLETED_DETAIL':'1'}
SOURCE='https://www.sos.ok.gov/corp/charitysearch.aspx'
TARGET='https://www.sos.ok.gov/corp/charityDetail.aspx?id=1234567890'

class ReadyDetail(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,SETTINGS);self.env.start();self.addCleanup(self.env.stop)
        self.version=patch.object(m,'APP_VERSION','test-performance-lab');self.version.start();self.addCleanup(self.version.stop)
        token=m.LAB_LOOKUP_MODE_CONTEXT.set('sales');self.addCleanup(m.LAB_LOOKUP_MODE_CONTEXT.reset,token)

    def test_standard_and_nonlab_keep_original_waits(self):
        for mode,version,host,flag in [('standard','v-performance-lab',SETTINGS['PUBLIC_BASE_URL'],'1'),
                ('sales','production',SETTINGS['PUBLIC_BASE_URL'],'1'),
                ('sales','v-performance-lab','https://staging.compliance-express.com','1'),
                ('sales','v-performance-lab',SETTINGS['PUBLIC_BASE_URL'],'0')]:
            with patch.object(m,'APP_VERSION',version),patch.dict(os.environ,{'PUBLIC_BASE_URL':host,'CE_LAB_OK_COMPLETED_DETAIL':flag}):
                token=m.LAB_LOOKUP_MODE_CONTEXT.set(mode)
                try:
                    page,link,module=Mock(),Mock(),Mock()
                    m.ok_open_selected_detail(page,link,None,module,'1234567890')
                    link.click.assert_called_once_with(timeout=5000)
                    module.safe_wait_for_network_idle.assert_called_once_with(page,timeout=20000)
                    page.wait_for_timeout.assert_called_once_with(2500)
                    page.expect_navigation.assert_not_called()
                finally:m.LAB_LOOKUP_MODE_CONTEXT.reset(token)

    def test_completed_document_avoids_fixed_pause_and_ignores_unrelated_traffic(self):
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                page=browser.new_page();calls=[]
                def route(r):
                    calls.append(r.request.url)
                    if r.request.url==SOURCE:
                        return r.fulfill(content_type='text/html',body='<a href="charityDetail.aspx?id=1234567890">1234567890</a>')
                    if r.request.url==TARGET:
                        return r.fulfill(content_type='text/html',body='<p>Status: Active</p><table><tr><td>Complete filing history</td></tr></table>')
                    r.abort()
                page.route('**/*',route);page.goto(SOURCE)
                module=Mock();start=time.monotonic()
                m.ok_open_selected_detail(page,page.get_by_role('link'),None,module,'1234567890')
                self.assertLess(time.monotonic()-start,2.5)
                self.assertIn('Complete filing history',page.inner_text('body'))
                module.safe_wait_for_network_idle.assert_not_called()
                self.assertEqual(calls,[SOURCE,TARGET])
            finally:browser.close()

    def test_failed_redirected_or_wrong_record_never_yields_completed_detail(self):
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                for kind in ['http_error','aborted','wrong_record','wrong_origin']:
                    page=browser.new_page()
                    href={'wrong_record':'charityDetail.aspx?id=999','wrong_origin':'https://evil.test/'}.get(kind,TARGET)
                    def route(r):
                        if r.request.url==SOURCE:return r.fulfill(content_type='text/html',body=f'<a href="{href}">1234567890</a>')
                        if kind=='aborted':return r.abort('connectionreset')
                        return r.fulfill(status=503,body='Unusable')
                    page.route('**/*',route);page.goto(SOURCE)
                    with self.subTest(kind=kind),self.assertRaises(Exception):
                        m.ok_open_selected_detail(page,page.get_by_role('link'),None,Mock(),'1234567890')
                    page.close()
            finally:browser.close()

    def test_entire_matching_queries_certificate_and_classification_preserved(self):
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','162676d:registry_snapshot_server.py'],cwd=root).decode())
        new=ast.parse(Path(m.__file__).read_text());strip_ok_completed_detail(new)
        self.assertEqual(ast.dump(old),ast.dump(new))

    def test_expired_budget_cannot_start_detail(self):
        page,link,module=Mock(),Mock(),Mock()
        org=SimpleNamespace(ok_search_deadline=time.perf_counter()-1)
        with self.assertRaises(TimeoutError):m.ok_open_selected_detail(page,link,org,module,'1234567890')
        link.click.assert_not_called();link.get_attribute.assert_not_called()

    def test_delayed_document_cannot_complete_early(self):
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                page=browser.new_page()
                def route(r):
                    if r.request.url==SOURCE:
                        return r.fulfill(content_type='text/html',body=f'<a href="{TARGET}">1234567890</a>')
                    time.sleep(.4)
                    return r.fulfill(content_type='text/html',body='<p>Status: Canceled</p><div>Final filing row</div>')
                page.route('**/*',route);page.goto(SOURCE);start=time.monotonic()
                m.ok_open_selected_detail(page,page.get_by_role('link'),None,Mock(),'1234567890')
                self.assertGreaterEqual(time.monotonic()-start,.4)
                self.assertIn('Final filing row',page.inner_text('body'))
            finally:browser.close()

if __name__=='__main__': unittest.main(verbosity=2)
