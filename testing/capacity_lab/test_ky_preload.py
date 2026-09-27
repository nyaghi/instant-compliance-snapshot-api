"""Pure public-name warmup cannot cache a match or bypass source freshness."""
import ast
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import registry_snapshot_server as c

ROOT = Path(c.__file__).parent
tree = ast.parse((ROOT / 'deployment/engine_preload.py').read_text(encoding='utf-8'))
node = next(n for n in tree.body if getattr(n, 'name', '') == 'preload_ky_public_names')
namespace = {'json': json}
exec(compile(ast.Module(body=[node], type_ignores=[]), 'pure KY preload', 'exec'), namespace)
warm = namespace['preload_ky_public_names']


class KentuckyPreload(unittest.TestCase):
    def setUp(self):
        c.normalized_match_name.cache_clear()
        self.addCleanup(c.normalized_match_name.cache_clear)

    def test_unusable_source_never_uses_network_or_old_snapshot(self):
        master = Mock()
        master.weekly_asset.return_value = None
        warm(master)
        self.assertEqual(master.mock_calls, [unittest.mock.call.weekly_asset('KY', 'downloadable-data/KY-records.json')])

    def test_only_actual_legal_and_dba_strings_are_normalized(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rows.json'
            path.write_text(json.dumps([['1', 'Legal Inc. | DBA: Other Name', '2024', 'row']]), encoding='utf-8')
            master = Mock()
            master.weekly_asset.return_value = path
            master.ky_registry_name_variants.side_effect = c.ky_registry_name_variants
            warm(master)
            self.assertEqual(master.normalized_match_name.call_args_list,
                             [unittest.mock.call('Legal Inc.'), unittest.mock.call('Other Name')])
            master.load_ky_live_pdf_records.assert_not_called()
            master.search_ky_strict_snapshot.assert_not_called()

    def test_real_source_warms_existing_immutable_string_cache(self):
        path = c.weekly_asset('KY', 'downloadable-data/KY-records.json')
        self.assertIsNotNone(path)
        warm(c)
        names = [name for row in json.loads(path.read_text(encoding='utf-8'))
                 for name in c.ky_registry_name_variants(row[1])]
        before = c.normalized_match_name.cache_info()
        for name in names:
            self.assertIsInstance(c.normalized_match_name(name), str)
        after = c.normalized_match_name.cache_info()
        self.assertEqual(after.misses, before.misses)
        self.assertEqual(after.hits - before.hits, len(names))

    def test_warm_names_cannot_supply_missing_registration_source(self):
        warm(c)
        with patch.object(c, 'weekly_asset', return_value=None), patch.object(c, 'load_ky_live_pdf_records', return_value=[]):
            with self.assertRaisesRegex(RuntimeError, 'unavailable/stale'):
                c.search_ky_strict_snapshot(c.checker.Organization('No Such Charity', '000000001'))

    def test_replacement_names_are_independent_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rows.json'
            def write(name):
                path.write_text(json.dumps([['1', name, '2024', 'row']]), encoding='utf-8')
            with patch.object(c, 'weekly_asset', return_value=path):
                write('First Name'); warm(c)
                write('Other Name'); warm(c)
            self.assertEqual(c.normalized_match_name('First Name'), 'first name')
            self.assertEqual(c.normalized_match_name('Other Name'), 'other name')

    def test_all_master_matching_status_and_date_code_is_identical(self):
        for name in ('registry_snapshot_server.py', 'Charity_Checker_Script for 13_states.py'):
            before = subprocess.check_output(['git', 'show', '3821cba:' + name], cwd=ROOT)
            self.assertEqual((ROOT / name).read_text(encoding='utf-8'), before.decode('utf-8').replace('\r\n', '\n'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
