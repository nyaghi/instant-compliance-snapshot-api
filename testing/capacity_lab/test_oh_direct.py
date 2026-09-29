"""Ohio public HTTP transport preserves the browser's interpretation."""
import ast
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import registry_snapshot_server as m

ROOT=Path(__file__).resolve().parents[2]
FIX=ROOT/'testing/fixtures/oh-direct-public'

class OhioDirectTests(unittest.TestCase):
    def setUp(self):
        self.org=m.checker.Organization('National Low Income Housing Coalition','52-1089824')
        self.search=(FIX/'521089824-search.html').read_bytes()
        self.detail=(FIX/'521089824-11811319-detail.html').read_bytes()

    def lookup(self, search=None, detail=None):
        with patch.object(m,'identity_fetch',side_effect=[search or self.search, detail or self.detail]):
            return m.search_oh_direct_details(self.org)

    def test_complete_ein_query_and_detail_uses_same_registry_record(self):
        result,body=self.lookup()
        self.assertTrue(result.success)
        self.assertEqual(result.matched_registry_identifier,'11811319')
        self.assertEqual(result.matched_registry_name,'National Low Income Housing Coalition & Low Income Housing')
        self.assertIn('Most Recent Report Filing Year: 2024',result.raw_status_text)
        self.assertIn('Fiscal Year End',body)

    def test_unconfirmed_form_wrong_ein_or_partial_response_falls_back(self):
        for source in (self.search.replace(b'52-1089824',b'11-1111111'),
                       self.search.replace(b'</html>',b''),
                       self.search.replace(b'Page 1 of 1',b'Page 1 of 2')):
            with self.subTest(source=source[-50:]):
                self.assertIsNone(self.lookup(search=source))
        for detail in (self.detail.replace(b'52-1089824',b'11-1111111'),
                       self.detail.replace(b'</html>',b''),
                       self.detail.replace(b'Fiscal Year End',b'Detail Not Loaded')):
            self.assertIsNone(self.lookup(detail=detail))

    def test_no_record_and_timeout_keep_existing_browser_search(self):
        self.assertIsNone(self.lookup(search=(FIX/'271635830-search.html').read_bytes()))
        with patch.object(m,'identity_fetch',side_effect=TimeoutError('source incomplete')):
            self.assertIsNone(m.search_oh_direct_details(self.org))
        with patch.object(m,'search_oh_direct_details',return_value=None), \
             patch.object(m.checker,'sync_playwright',side_effect=RuntimeError('original browser path')):
            with self.assertRaisesRegex(RuntimeError,'original browser path'):
                m.run_state_lookup(self.org.organization_name,self.org.ein,'OH')

    def test_success_avoids_browser_but_capture_still_uses_browser(self):
        result=self.lookup()
        with patch.object(m,'search_oh_direct_details',return_value=result), \
             patch.object(m,'response_data_for_lookup',side_effect=lambda r,*args:r), \
             patch.object(m.checker,'sync_playwright',side_effect=RuntimeError('capture browser')):
            self.assertIs(m.run_state_lookup(self.org.organization_name,self.org.ein,'OH'),result[0])
            with self.assertRaisesRegex(RuntimeError,'capture browser'):
                m.run_state_lookup(self.org.organization_name,self.org.ein,'OH',capture_source_snapshot=True)

    def test_status_interpretation_is_moved_verbatim(self):
        # Compare the moved AST statements with the previous live implementation:
        # transport optimization cannot add/change an Ohio interpretation rule.
        old=ast.parse(subprocess.check_output(['git','show','f28dd63:registry_snapshot_server.py'],cwd=ROOT).decode('utf-8'))
        fn=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name=='search_oh')
        body=next(n for n in fn.body if isinstance(n,ast.Try)).body
        start=next(i for i,n in enumerate(body) if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='site_name')
        new=ast.parse((ROOT/'registry_snapshot_server.py').read_text(encoding='utf-8'))
        moved=next(n for n in new.body if isinstance(n,ast.FunctionDef) and n.name=='oh_result_from_detail_text')
        self.assertEqual([ast.dump(n) for n in body[start:]],[ast.dump(n) for n in moved.body[2:]])

    def test_discovery_still_requires_ein_equals_form(self):
        with patch.object(m,'identity_fetch',return_value=self.search):
            names=m.identity_oh_names('521089824',m.time.monotonic()+2)
        self.assertTrue(names['complete'])
        self.assertTrue(any('Coalition' in n['name'] for n in names['names']))
        with patch.object(m,'identity_fetch',return_value=self.search.replace(b'52-1089824',b'11-1111111')):
            with self.assertRaises(ValueError):m.identity_oh_names('521089824',m.time.monotonic()+2)

if __name__=='__main__':unittest.main()
