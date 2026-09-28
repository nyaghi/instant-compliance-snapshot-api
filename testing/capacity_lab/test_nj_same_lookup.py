"""Reuse fresh completed zero queries without skipping untested NJ aliases."""
import ast, copy, json, os, subprocess, unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import registry_snapshot_server as m
from testing.capacity_lab import test_nj_public_query as fixture

ZERO = {'ItemCount': 0, 'Records': [], 'MoreRecords': False, 'PageNumber': 1}
NAMES = ['Example Relief', 'Former Example Relief', 'Example Relief Inc']


def strip_same_lookup(tree):
    from testing.capacity_lab.ny_failed_scope import strip_ny_failed_wakeup
    strip_ny_failed_wakeup(tree)
    helpers = {'NJCompletedPublicQueries', 'nj_zero_reuse_enabled', 'nj_name_fallback_queries',
               'nj_complete_public_zero', 'nj_complete_other_ein_rows', 'nj_same_lookup_zero_queries'}
    nodes = {n.name: n for n in tree.body if getattr(n, 'name', '') in helpers}
    if not nodes:
        return
    assert set(nodes) == helpers
    original_query_call = copy.deepcopy(nodes['nj_name_fallback_queries'].body[0].value)
    tree.body[:] = [n for n in tree.body if getattr(n, 'name', '') not in helpers]
    public = next(n for n in tree.body if getattr(n, 'name', '') == 'search_nj_public_details')
    doc = public.body[0].value
    if 'An explicit lab Sales opt-in' in doc.value:
        doc.value = doc.value.replace(
            '    Ambiguous, incomplete or changed responses keep the existing browser path.\n'
            '    An explicit lab Sales opt-in may also finish the unchanged no-match path\n'
            '    after every planned EIN/name query has completed without a qualifying row.',
            '    Missing, negative, ambiguous, incomplete or changed responses keep the\n'
            '    existing browser/name-fallback path and never become a negative here.')
    removable = [n for n in public.body if isinstance(n, ast.Assign) and (
        any(isinstance(t, ast.Name) and t.id == 'progress' for t in n.targets) or
        any(isinstance(t, ast.Attribute) and t.attr == '_cc_nj_completed_public_queries' for t in n.targets))]
    assert len(removable) == 2
    for n in removable:
        public.body.remove(n)
    removed = 0
    for parent in ast.walk(public):
        for _, children in ast.iter_fields(parent):
            if isinstance(children, list):
                for child in list(children):
                    if isinstance(child, ast.If) and 'nj_complete_public_zero(data)' in ast.unparse(child.test):
                        children.remove(child)
                        removed += 1
    assert removed == 1
    fallback = next(n for n in tree.body if getattr(n, 'name', '') == 'search_nj_with_name_fallback')
    assert ast.unparse(fallback.body[0]) == 'completed = nj_same_lookup_zero_queries(org)'
    assert isinstance(fallback.body[1], ast.If) and 'completed' in ast.unparse(fallback.body[1].test)
    fallback.body[:2] = ast.parse('result = search_nj_direct(page, org)').body
    loop = next(n for n in fallback.body if isinstance(n, ast.For))
    assert ast.unparse(loop.iter) == 'nj_name_fallback_queries(org)'
    loop.iter = original_query_call
    assert ast.unparse(loop.body[0]) == 'if variant in completed:\n    continue'
    loop.body.pop(0)
    assert ast.unparse(fallback.body[-2].test) == 'completed'
    fallback.body.pop(-2)


class SameLookup(unittest.TestCase):
    def setUp(self):
        self.f = fixture.PublicQuery()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.org = self.f.org
        self.queries = []
        self.answers = {}
        self.session = self.f.session
        self.session.request.side_effect = self.request
        for p in [patch.object(m, 'nj_zero_reuse_enabled', return_value=True),
                  patch.object(m, 'nj_name_fallback_queries', return_value=NAMES)]:
            p.start(); self.addCleanup(p.stop)

    def request(self, method, url, **kwargs):
        if '/entity-grid-data.json/' not in url:
            return self.f.request(method, url, **kwargs)
        query = kwargs['json']['search']
        self.queries.append(query)
        answer = self.answers.get(query, ZERO)
        if isinstance(answer, Exception):
            raise answer
        self.f.data = answer
        # Run original payload/transport assertions with just the expected query adapted.
        old = self.f.org.ein
        self.f.org.ein = query
        try:
            return self.f.request(method, url, **kwargs)
        finally:
            self.f.org.ein = old

    def result(self, status='Not Registered', complete=True):
        r = m.checker.StateResult(self.org.organization_name, self.org.ein, 'NJ', status, fixture.BASE)
        r.success = complete
        if not complete:
            r.reason_code = 'NJ_INCOMPLETE_QUERY_RESPONSE'
        return r

    def test_all_planned_queries_complete_before_negative_and_no_duplicate_browser(self):
        with patch.object(m, 'search_nj_direct', side_effect=AssertionError('duplicate browser request')):
            direct, evidence = m.search_nj_public_details(self.org)
        self.assertTrue(direct.success)
        self.assertEqual(m.public_status(direct), 'Not Registered')
        self.assertIn('organization-name queries completed', evidence)
        self.assertEqual(self.queries, [self.org.ein, *NAMES])
        with patch.object(m, 'search_nj_direct', side_effect=AssertionError('duplicate browser request')):
            r = m.search_nj_with_name_fallback(MagicMock(), self.org)
        self.assertTrue(r.success)
        self.assertEqual(m.public_status(r), 'Not Registered')
        self.assertIn('organization-name queries completed', r.source_note)

    def test_positive_name_still_requires_original_browser_identity_confirmation(self):
        self.answers[NAMES[1]] = fixture.DATA
        self.assertIsNone(m.search_nj_public_details(self.org))
        self.assertEqual(self.queries, [self.org.ein, NAMES[0], NAMES[1]])
        with patch.object(m, 'search_nj_direct', return_value=self.result('Current')) as browser, \
             patch.object(m, 'result_registry_name_is_safe', return_value=True) as safe:
            r = m.search_nj_with_name_fallback(MagicMock(), self.org)
        self.assertEqual(m.public_status(r), 'Current')
        self.assertEqual(browser.call_args.args[1].organization_name, NAMES[1])
        safe.assert_called_once()

    def test_unsafe_positive_does_not_bypass_matching_or_other_queries(self):
        self.answers[NAMES[0]] = fixture.DATA
        m.search_nj_public_details(self.org)
        seen = []
        def direct(page, org):
            seen.append(org.organization_name)
            return self.result('Current') if org.organization_name == NAMES[0] else self.result()
        with patch.object(m, 'search_nj_direct', side_effect=direct), \
             patch.object(m, 'result_registry_name_is_safe', return_value=False):
            r = m.search_nj_with_name_fallback(MagicMock(), self.org)
        self.assertEqual(seen, NAMES)
        self.assertEqual(m.public_status(r), 'Not Registered')

    def test_timeout_reuses_only_completed_prefix_and_searches_every_remaining_name(self):
        self.answers[NAMES[1]] = TimeoutError('registry did not finish')
        m.search_nj_public_details(self.org)
        self.assertEqual(m.nj_same_lookup_zero_queries(self.org), {self.org.ein, NAMES[0]})
        seen = []
        def direct(page, org):
            seen.append(org.organization_name)
            return self.result()
        with patch.object(m, 'search_nj_direct', side_effect=direct):
            r = m.search_nj_with_name_fallback(MagicMock(), self.org)
        self.assertEqual(seen, NAMES[1:])
        self.assertEqual(m.public_status(r), 'Not Registered')

    def test_incomplete_public_and_browser_response_never_become_negative(self):
        self.answers[NAMES[0]] = {**ZERO, 'MoreRecords': True}
        m.search_nj_public_details(self.org)
        with patch.object(m, 'search_nj_direct', return_value=self.result('Unable to Confirm', False)):
            r = m.search_nj_with_name_fallback(MagicMock(), self.org)
        self.assertFalse(r.success)
        self.assertNotEqual(m.public_status(r), 'Not Registered')

    def test_all_name_rows_with_other_eins_keep_searching_remaining_aliases(self):
        wrong = copy.deepcopy(fixture.DATA)
        wrong['Records'][0]['Attributes'][-1]['DisplayValue'] = '987654321'
        self.answers[NAMES[0]] = wrong
        m.search_nj_public_details(self.org)
        self.assertEqual(self.queries, [self.org.ein, *NAMES])
        with patch.object(m, 'search_nj_direct', side_effect=AssertionError('known different EIN repeated')):
            r = m.search_nj_with_name_fallback(MagicMock(), self.org)
        self.assertEqual(m.public_status(r), 'Not Registered')

    def test_public_ein_failure_leaves_entire_original_browser_route(self):
        self.answers[self.org.ein] = TimeoutError('EIN incomplete')
        m.search_nj_public_details(self.org)
        with patch.object(m, 'search_nj_direct', return_value=self.result('Site Not Reachable', False)) as browser:
            r = m.search_nj_with_name_fallback(MagicMock(), self.org)
        self.assertIs(browser.call_args.args[1], self.org)
        self.assertFalse(r.success)

    def test_no_cross_lookup_or_cross_organization_result_cache(self):
        m.search_nj_public_details(self.org)
        first = self.org._cc_nj_completed_public_queries
        self.answers[self.org.ein] = TimeoutError('second lookup failed')
        m.search_nj_public_details(self.org)
        self.assertIsNot(first, self.org._cc_nj_completed_public_queries)
        self.assertEqual(m.nj_same_lookup_zero_queries(self.org), set())
        other = m.checker.Organization('Example Relief', '123456789')
        self.assertEqual(m.nj_same_lookup_zero_queries(other), set())
        self.assertEqual(m.curl_requests.Session.call_count, 2)

    def test_original_unique_positive_keeps_exact_ein_and_details(self):
        self.answers[self.org.ein] = fixture.DATA
        result, body = m.search_nj_public_details(self.org)
        self.assertEqual(result.matched_registry_identifier, self.org.ein)
        self.assertEqual(result.status, 'Current')
        self.assertEqual(len(self.f.calls), 6)
        self.assertEqual(self.queries, [self.org.ein])


class GuardAndScope(unittest.TestCase):
    def test_all_other_ein_proof_rejects_partial_same_unknown_and_conflicting_identity(self):
        wrong = copy.deepcopy(fixture.DATA)
        wrong['Records'][0]['Attributes'][-1]['DisplayValue'] = '987654321'
        self.assertTrue(m.nj_complete_other_ein_rows(wrong, '123456789'))
        cases = [fixture.DATA, {**wrong, 'MoreRecords': True}, {**wrong, 'ItemCount': 2},
                 {**wrong, 'Records': [None]}, {**wrong, 'PageNumber': True}, {**wrong, 'Error': 'partial'}]
        for value in ['', 'unknown', '000000000', '12-3456789']:
            row = copy.deepcopy(wrong); row['Records'][0]['Attributes'][-1]['DisplayValue'] = value; cases.append(row)
        row = copy.deepcopy(wrong); row['Records'][0]['Attributes'][-1]['Value'] = '123456789'; cases.append(row)
        row = copy.deepcopy(wrong); row['Records'][0]['Attributes'].append(copy.deepcopy(row['Records'][0]['Attributes'][-1])); cases.append(row)
        row = copy.deepcopy(wrong); row['Records'][0]['Attributes'].pop(); cases.append(row)
        row = copy.deepcopy(wrong); row['Records'][0]['Attributes'].append(None); cases.append(row)
        for value in cases:
            with self.subTest(value=value): self.assertFalse(m.nj_complete_other_ein_rows(value, '123456789'))

    def test_zero_requires_explicit_complete_schema_without_errors(self):
        self.assertTrue(m.nj_complete_public_zero(ZERO))
        for value in [None, [], {}, *[{**ZERO, k: v} for k, v in [
            ('ItemCount', False), ('ItemCount', 0.0), ('ItemCount', 1), ('Records', None),
            ('Records', [{}]), ('MoreRecords', None), ('MoreRecords', True),
            ('PageNumber', True), ('PageNumber', 1.0), ('PageNumber', 2),
            ('Error', 'source failed'), ('errorMessage', 'failed'), ('Success', False)]]]:
            with self.subTest(value=value):
                self.assertFalse(m.nj_complete_public_zero(value))

    def test_only_exact_lab_explicit_sales(self):
        base = {'PUBLIC_BASE_URL': 'https://instant-compliance-snapshot-api-hn4v.onrender.com',
                'CE_LAB_NJ_PUBLIC_QUERY': '1', 'CE_LAB_NJ_ZERO_REUSE': '1'}
        for mode, version, override, want in [
            ('sales', 'x-performance-lab', {}, True), ('standard', 'x-performance-lab', {}, False),
            ('sales', 'staging', {}, False), ('sales', 'x-performance-lab', {'CE_LAB_NJ_ZERO_REUSE': ''}, False),
            ('sales', 'x-performance-lab', {'CE_LAB_NJ_PUBLIC_QUERY': ''}, False),
            ('sales', 'x-performance-lab', {'PUBLIC_BASE_URL': 'https://staging.compliance-express.com'}, False)]:
            with patch.object(m, 'APP_VERSION', version), patch.dict(os.environ, {**base, **override}):
                token = m.LAB_LOOKUP_MODE_CONTEXT.set(mode)
                try: self.assertIs(m.nj_zero_reuse_enabled(), want)
                finally: m.LAB_LOOKUP_MODE_CONTEXT.reset(token)

    def test_wrong_ein_forged_progress_or_old_progress_cannot_skip_queries(self):
        org = m.checker.Organization('Example Relief', '123456789')
        with patch.object(m, 'nj_zero_reuse_enabled', return_value=True):
            for proof in [{'ein': org.ein, 'queries': {org.ein}}, m.NJCompletedPublicQueries('987654321')]:
                org._cc_nj_completed_public_queries = proof
                self.assertEqual(m.nj_same_lookup_zero_queries(org), set())
            proof = m.NJCompletedPublicQueries(org.ein)
            proof.queries.add(org.ein); org._cc_nj_completed_public_queries = proof
            with patch.object(m.time, 'monotonic', return_value=proof.created + 61):
                self.assertEqual(m.nj_same_lookup_zero_queries(org), set())
            with patch.object(m.time, 'monotonic', return_value=proof.created + 1):
                observed = m.nj_same_lookup_zero_queries(org); observed.clear()
                self.assertEqual(proof.queries, {org.ein})

    def test_query_plan_and_every_other_master_operation_identical_to_deployed77(self):
        root = Path(m.__file__).parent
        old = ast.parse(subprocess.check_output(['git', 'show', 'cdebfda:registry_snapshot_server.py'], cwd=root).decode('utf-8'))
        new = ast.parse(Path(m.__file__).read_text(encoding='utf-8'))
        strip_same_lookup(new)
        self.assertEqual(ast.dump(old), ast.dump(new))


if __name__ == '__main__': unittest.main()
