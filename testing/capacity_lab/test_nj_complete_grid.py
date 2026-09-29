"""Large public grids must preserve EIN, alias, completeness and fallback controls."""
import ast, copy, json, os, subprocess, unittest
from pathlib import Path
from unittest.mock import patch
import registry_snapshot_server as m
from testing.capacity_lab import test_nj_public_query as fixture
from testing.capacity_lab import test_nj_same_lookup as reuse
ZERO, NAMES = reuse.ZERO, reuse.NAMES

def row(name='Unrelated Animal Shelter', ein='987654321', credential='CH12345'):
    fields = {'name': name, 'accountnumber': credential}
    if ein is not None: fields['crsm_federalein'] = ein
    return {'Attributes': [{'Name': k, 'Value': v, 'DisplayValue': v} for k, v in fields.items()]}

def grid(rows):
    return {'ItemCount': len(rows), 'MoreRecords': False, 'PageNumber': 1, 'Records': rows}

class CompleteGrid(unittest.TestCase):
    def setUp(self): self.org = m.checker.Organization('Example Relief', '123456789')

    def test_other_eins_and_unrelated_missing_ein_rows_can_be_excluded(self):
        data = grid([row(credential='CH'+str(i)) for i in range(15)] + [row(ein=None, credential='CH99')])
        self.assertTrue(m.nj_complete_grid_excludes_org(data, self.org))

    def test_matching_unknown_or_malformed_ein_requires_browser(self):
        for name, ein in [('Example Relief', None), ('Example Relief Inc', ''),
                          ('Unrelated Animal Shelter', '123456789'), ('Unrelated Animal Shelter', '12-3456789'),
                          ('Unrelated Animal Shelter', '000000000'), ('Unrelated Animal Shelter', 'unavailable')]:
            with self.subTest(name=name, ein=ein):
                self.assertFalse(m.nj_complete_grid_excludes_org(grid([row(name, ein)]), self.org))

    def test_known_alias_without_ein_keeps_identity_fallback(self):
        with patch.object(m, 'organization_match_target_variants', return_value=['Example Relief', 'Former Relief']):
            self.assertFalse(m.nj_complete_grid_excludes_org(grid([row('Former Relief', None)]), self.org))

    def test_same_name_other_ein_is_not_the_requested_organization(self):
        self.assertTrue(m.nj_complete_grid_excludes_org(grid([row('Example Relief', '987654321')]), self.org))

    def test_partial_empty_duplicate_and_error_grids_are_not_negative_evidence(self):
        good = grid([row()])
        cases = [None, {}, ZERO, grid([row(), row()]), grid([row(credential='invalid')]),
                 grid([row(name='', ein=None)]), grid([row(credential='CH'+str(i)) for i in range(51)])]
        cases += [{**good, key: value} for key, value in [
            ('MoreRecords', True), ('MoreRecords', None), ('ItemCount', True), ('ItemCount', 2),
            ('PageNumber', 2), ('PageNumber', True), ('Records', [None]), ('Error', 'timeout'), ('Success', False)]]
        conflict = copy.deepcopy(good); conflict['Records'][0]['Attributes'][-1]['Value'] = '123456789'; cases.append(conflict)
        duplicate = copy.deepcopy(good); duplicate['Records'][0]['Attributes'].append(duplicate['Records'][0]['Attributes'][-1]); cases.append(duplicate)
        for data in cases:
            with self.subTest(data=data): self.assertFalse(m.nj_complete_grid_excludes_org(data, self.org))

    def test_gated_to_existing_lab_sales_path_and_explicit_flag(self):
        for parent in [False, True]:
            for flag in ['', '1']:
                with patch.object(m, 'nj_zero_reuse_enabled', return_value=parent), patch.dict(os.environ, CE_LAB_NJ_COMPLETE_GRID=flag):
                    self.assertEqual(m.nj_complete_grid_enabled(), parent and flag == '1')

    def test_every_other_master_function_is_unchanged(self):
        from testing.capacity_lab.nj_grid_scope import strip_nj_complete_grid
        root = Path(m.__file__).parent
        old = ast.parse(subprocess.check_output(['git', 'show', '45bddd3:registry_snapshot_server.py'], cwd=root).decode())
        new = ast.parse(Path(m.__file__).read_text(encoding='utf-8'))
        strip_nj_complete_grid(new)
        self.assertEqual(ast.dump(old), ast.dump(new))

class CompleteGridFlow(unittest.TestCase):
    def setUp(self):
        self.f = reuse.SameLookup(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.addCleanup(self.f.f.doCleanups)
        self.org = self.f.org
        self.sizes = []
        original = self.f.request
        def request(method, url, **kw):
            if '/entity-grid-data.json/' in url:
                self.sizes.append((kw['json']['search'], kw['json']['pageSize']))
                # Existing shared fixture only accepts the former default size.
                kw = {**kw, 'json': {**kw['json'], 'pageSize': 10}}
            return original(method, url, **kw)
        self.f.session.request.side_effect = request
        p = patch.object(m, 'nj_complete_grid_enabled', return_value=True); p.start(); self.addCleanup(p.stop)

    def test_complete_large_grid_finishes_unchanged_plan_without_browser(self):
        self.f.answers[NAMES[0]] = grid([row(credential='CH'+str(i)) for i in range(20)] + [row(ein=None, credential='CH99')])
        with patch.object(m, 'search_nj_direct', side_effect=AssertionError('duplicate lookup')):
            result, _ = m.search_nj_public_details(self.org)
        self.assertEqual(m.public_status(result), 'Not Registered'); self.assertTrue(result.success)
        self.assertEqual(self.f.queries, [self.org.ein, *NAMES])
        self.assertEqual(self.sizes, [(self.org.ein, 10), *[(n, 50) for n in NAMES]])

    def test_unresolved_alias_or_partial_large_grid_retains_browser(self):
        for data in [grid([row('Former Example Relief', None)]), {**grid([row()]), 'MoreRecords': True}]:
            self.f.answers[NAMES[0]] = data
            with patch.object(m, 'organization_match_target_variants', return_value=NAMES):
                self.assertIsNone(m.search_nj_public_details(self.org))
            self.assertEqual(m.nj_same_lookup_zero_queries(self.org), {self.org.ein})

    def test_large_name_grid_has_bounded_allowance_without_changing_ein_limit(self):
        self.f.answers[NAMES[0]] = {**grid([row(ein=None)]), 'Unused': 'x' * 1_100_000}
        result, _ = m.search_nj_public_details(self.org)
        self.assertEqual(m.public_status(result), 'Not Registered')
        self.f.answers[NAMES[0]]['Unused'] = 'x' * 2_000_000
        self.assertIsNone(m.search_nj_public_details(self.org))
        self.assertEqual(m.nj_same_lookup_zero_queries(self.org), {self.org.ein})
        self.f.answers[self.org.ein] = {**ZERO, 'Unused': 'x' * 1_100_000}
        self.assertIsNone(m.search_nj_public_details(self.org))
        self.assertEqual(m.nj_same_lookup_zero_queries(self.org), set())

if __name__ == '__main__': unittest.main()
