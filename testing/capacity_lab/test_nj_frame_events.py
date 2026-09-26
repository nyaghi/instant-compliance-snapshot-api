"""A pending detail navigation needs the browser event loop, not Python sleep."""
import ast
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import registry_snapshot_server as m


class NewJerseyFrameEventsTests(unittest.TestCase):
    def test_real_delayed_frame_previously_missed_now_read_within_same_budget(self):
        source = subprocess.check_output(['git','show','0d31a72:registry_snapshot_server.py'],
            cwd=Path(m.__file__).parent).decode('utf-8')
        old = next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='nj_loaded_detail_body')
        ns=dict(m.__dict__)
        exec(compile(ast.fix_missing_locations(ast.Module(body=[old],type_ignores=[])), 'old NJ reader','exec'),ns)
        org=SimpleNamespace(organization_name='Example Relief',ein='123456789')
        with m.checker.sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                for reader,should_find in [(ns['nj_loaded_detail_body'],False),(m.nj_loaded_detail_body,True)]:
                    page=browser.new_page()
                    page.route('**/CHR-Public-Details-Page/**',lambda route:route.fulfill(status=200,
                        content_type='text/html',body='<html><body>Example Relief 123456789 Next Filing Due: 12/31/2026</body></html>'))
                    page.set_content('<iframe id="detail"></iframe>')
                    page.evaluate("setTimeout(() => document.querySelector('#detail').src='https://charportal.dca.njoag.gov/CHR-Public-Details-Page/?id=example&rid=filing', 100)")
                    result=reader(page,org,wait_seconds=.75)
                    self.assertEqual(bool(result),should_find)
                    page.close()
            finally:
                browser.close()

    def test_no_frame_keeps_original_budget(self):
        clock=[0.0];page=Mock(frames=[])
        page.wait_for_timeout.side_effect=lambda ms:clock.__setitem__(0,clock[0]+ms/1000)
        with patch.object(m.time,'monotonic',side_effect=lambda:clock[0]):
            self.assertEqual(m.nj_loaded_detail_body(page,SimpleNamespace(ein='123456789',organization_name='Example Relief'),wait_seconds=.6),'')
        self.assertAlmostEqual(clock[0],.6)
        self.assertEqual(page.wait_for_timeout.call_count,3)

    def test_only_polling_mechanism_changed_in_master(self):
        before=subprocess.check_output(['git','show','0d31a72:registry_snapshot_server.py'],cwd=Path(m.__file__).parent).decode('utf-8')
        after=Path(m.__file__).read_text(encoding='utf-8')
        old='time.sleep(min(0.25, remaining))'
        new='page.wait_for_timeout(min(250, remaining * 1000))'
        start=after.index('def nj_loaded_detail_body(')
        end=after.index('\ndef nj_missing_period_result(',start)
        section=after[start:end]
        self.assertEqual(section.count(new),1)
        restored=after[:start]+section.replace(new,old)+after[end:]
        from testing.capacity_lab.parsing_scope import strip_nj_public_detail_optimization, strip_or_snapshot_index_optimization
        tree = ast.parse(restored)
        strip_or_snapshot_index_optimization(tree)
        strip_nj_public_detail_optimization(tree)
        self.assertEqual(ast.dump(tree),ast.dump(ast.parse(before)))


if __name__=='__main__':unittest.main()
