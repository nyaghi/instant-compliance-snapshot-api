"""One live-DOM read preserves visibility, order, row limit, text and matching."""
import ast,os,subprocess,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from playwright.sync_api import sync_playwright
import registry_snapshot_server as m

class Rows(unittest.TestCase):
    def setUp(self):
        self.token=m.LAB_LOOKUP_MODE_CONTEXT.set('sales');self.addCleanup(m.LAB_LOOKUP_MODE_CONTEXT.reset,self.token)
        for p in [patch.object(m,'APP_VERSION','fixture-performance-lab'),patch.dict(os.environ,{'PUBLIC_BASE_URL':'https://instant-compliance-snapshot-api-hn4v.onrender.com','CE_LAB_PA_ROW_SNAPSHOT':'1'})]:
            p.start();self.addCleanup(p.stop)

    def test_standard_nonlab_and_flag_off_keep_original_locator(self):
        for mode,version,flag,url in [('standard','x-performance-lab','1','https://instant-compliance-snapshot-api-hn4v.onrender.com'),('sales','staging','1','https://instant-compliance-snapshot-api-hn4v.onrender.com'),('sales','x-performance-lab','0','https://instant-compliance-snapshot-api-hn4v.onrender.com'),('sales','x-performance-lab','1','https://staging.compliance-express.com')]:
            page=Mock();token=m.LAB_LOOKUP_MODE_CONTEXT.set(mode)
            try:
                with patch.object(m,'APP_VERSION',version),patch.dict(os.environ,{'PUBLIC_BASE_URL':url,'CE_LAB_PA_ROW_SNAPSHOT':flag}):
                    self.assertIs(m.pa_name_rows(page,'tr'),page.locator.return_value)
                    page.locator.return_value.evaluate_all.assert_not_called()
            finally:m.LAB_LOOKUP_MODE_CONTEXT.reset(token)

    def test_incomplete_malformed_or_failed_snapshot_uses_original(self):
        for data in [None,{},[{}],[{'visible':True,'count':-1,'text':'x','first':'','fifth':''}],{'error':'incomplete'}]:
            page=Mock();page.locator.return_value.evaluate_all.return_value=data
            self.assertIs(m.pa_name_rows(page,'tr'),page.locator.return_value)
        page=Mock();page.locator.return_value.evaluate_all.side_effect=TimeoutError()
        self.assertIs(m.pa_name_rows(page,'tr'),page.locator.return_value)

    def test_real_browser_rows_match_original_including_hidden_and_headers(self):
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                page=browser.new_page();page.set_content('''<table><thead><tr><th>Name</th></tr></thead><tbody>
                <tr><td>Legal <b>Organization</b></td><td>12-3456789</td><td>Active</td><td>City</td><td>09/30/2027</td></tr>
                <tr style="display:none"><td>Wrong hidden organization</td></tr>
                <tr style="visibility:hidden"><td>Wrong invisible organization</td></tr>
                <tr style="opacity:0"><td>Transparent but visible to Playwright</td></tr>
                <tr><td>Empty dates</td><td></td><td></td><td></td><td></td></tr></tbody></table>
                <div role="row">Also known as<br>Former Name</div>''')
                for selector in ('tr','tbody tr',"[role='row']"):
                    original=page.locator(selector);snapshot=m.pa_name_rows(page,selector)
                    self.assertEqual(snapshot.count(),original.count())
                    for index in range(original.count()):
                        a,b=original.nth(index),snapshot.nth(index)
                        self.assertEqual(a.is_visible(),b.is_visible(timeout=750))
                        if not a.is_visible():continue
                        self.assertEqual(a.inner_text(),b.inner_text(timeout=1500))
                        ac,bc=a.locator('td'),b.locator('td');self.assertEqual(ac.count(),bc.count())
                        if ac.count()>=5:
                            for j in (0,4):self.assertEqual(ac.nth(j).inner_text(),bc.nth(j).inner_text(timeout=1500))
                page.set_content('<table>'+''.join('<tr><td>Row '+str(i)+'</td></tr>' for i in range(130))+'</table>')
                snapshot=m.pa_name_rows(page,'tr');self.assertEqual(snapshot.count(),100)
                self.assertEqual(snapshot.nth(99).inner_text(),'Row 99')
            finally:browser.close()

    def test_whole_master_changes_only_row_acquisition(self):
        from testing.capacity_lab.pa_rows_scope import strip_pa_rows
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','faf4db4:registry_snapshot_server.py'],cwd=root).decode())
        new=ast.parse(Path(m.__file__).read_text(encoding='utf-8'));strip_pa_rows(new)
        self.assertEqual(ast.dump(old),ast.dump(new))

if __name__=='__main__':unittest.main()
