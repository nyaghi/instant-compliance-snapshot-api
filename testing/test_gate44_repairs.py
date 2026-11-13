from time import perf_counter
from unittest import TestCase
from unittest.mock import Mock, patch

import registry_snapshot_server as m
from deployment import state_snapshots
from deployment.source_visual_adapters import wv_open_selected_search


class Gate44Controls(TestCase):
    name = "American Committee for the Weizmann Institute of Science, Inc."
    registry_name = "AMERICAN COMMITTEE FOR THE WEIZMANN INSTITUTE FOR SCIENCE INC"
    ein = "131623886"
    href = "CredSummaryDetails.aspx?chid=697240&h=1052191889"

    def test_ri_uses_existing_slot_without_reordering_legal_and_reviewed_names(self):
        org = m.checker.Organization(self.name, self.ein)
        queries = []
        def search(query, *_):
            queries.append(query)
            return []
        with patch.object(m, "known_names_for_ein", return_value=[]), \
             patch.object(m, "registry_json_request", return_value={"access_token": "fixture"}), \
             patch.object(m, "ri_charity_search", side_effect=search):
            required, generated = m.licensed_charity_names(org, literal_suffix_priority=True)
            result = m.search_ri(org)
        self.assertEqual(len(queries), len(required + generated))
        self.assertEqual(queries[:2], (required + generated)[:2])
        self.assertEqual(queries[-1], "WEIZMANN")
        self.assertEqual(result.status, "Not Registered")

    def test_ri_keeps_normal_and_already_useful_plans(self):
        for name, fallback in [
            ("Rhode Island Food Bank", ["Rhode Island", "Food Bank"]),
            (self.name, ["American Committee For", "Weizmann Institute"]),
            (self.name, ["American Committee For", "American Committee For The", "Weizmann"]),
        ]:
            self.assertEqual(m.ri_distinctive_fallback(name, fallback), fallback)

    def test_wi_exact_credential_with_one_word_difference_requires_corroboration(self):
        name = self.registry_name
        row = (f'| 5995-800 | Charitable Organization | [{name}]({self.href}) '
               '| NEW YORK, NY | 05/02/1997 | 07/31/2027 |')
        detail = (f'Name: {name} Credential Type: CHARITABLE ORGANIZATION (800) '
                  'Credential Number: 5995-800 Location: MESA, AZ '
                  'Status License is current (Active)')
        for decision, confirmed in [('corroborated', True), ('unavailable', False),
                                     ('conflict', False), ('different_ein', False)]:
            with self.subTest(decision=decision), \
                 patch.object(m, 'wi_reader_text', return_value=detail), \
                 patch.object(m, 'registry_address_evidence', return_value={'decision': decision}), \
                 patch.object(m, 'registry_cross_state_identity', return_value={}), \
                 patch.object(m, 'registry_identity_preference', return_value=0):
                candidate = m.wi_candidate_from_markdown_row(row, [self.name], self.name, self.ein)
                self.assertEqual(candidate['license_number'], '5995-800')
                self.assertEqual(not candidate['identity_conflict'], confirmed)
        for wrong in (name + ' Foundation', name.replace('SCIENCE', 'RESEARCH'),
                      name.replace('INSTITUTE FOR', 'UNIVERSITY FOR')):
            self.assertFalse(m.wi_institute_preposition_variant(self.name, wrong))

    def test_wi_different_number_type_url_or_detail_name_never_verifies(self):
        name = self.registry_name
        candidate = {'registry_name': name, 'license_number': '5995-800', 'detail_href': self.href}
        detail = (f'Name: {name} Credential Type: CHARITABLE ORGANIZATION (800) '
                  'Credential Number: 5995-800 Location: MESA, AZ '
                  'Status License is current (Active)')
        checks = [
            (candidate, detail.replace('5995-800', '5996-800')),
            (candidate, detail.replace('CHARITABLE ORGANIZATION', 'COMMERCIAL FUNDRAISER')),
            ({**candidate, 'detail_href': 'https://example.com/' + self.href}, detail),
            (candidate, detail.replace('INSTITUTE FOR', 'INSTITUTE OF')),
        ]
        for row, body in checks:
            with patch.object(m, 'registry_address_evidence', return_value={'decision': 'corroborated'}):
                result = m.wi_verify_candidate_identity(row, [self.name], self.name, self.ein, body)
                self.assertTrue(result['identity_conflict'])
                self.assertTrue(result['identity_detail_unavailable'])

    def test_nm_fiscal_conflict_retains_only_exact_ein_evidence(self):
        org = m.checker.Organization(self.name, self.ein)
        def evidence(query):
            base = {'query': query, 'complete': True}
            if query['operation'] == 'search':
                return dict(base, rows=[{'name': self.name, 'ein': self.ein}], total=1)
            return dict(base, name=self.name, ein=self.ein,
                        history_rows=[['2024', 'Registration Submitted 20244022608235332', '3/23/2026']],
                        financial_periods=[
                            {'tax_year': 2024, 'period_start': '7/1/2024', 'period_end': '6/30/2025'},
                            {'tax_year': 2024, 'period_start': '1/1/2024', 'period_end': '12/31/2024'},
                        ])
        started = perf_counter()
        result = m.nm_browser_lookup(org, evidence)
        data = m.response_data_for_lookup(result, '', org, self.name, self.ein, 'NM', started)
        self.assertFalse(data['success'])
        self.assertEqual(data['status'], 'Unable to Confirm')
        self.assertEqual(data['reason_code'], 'NM_CONFLICTING_FISCAL_PERIODS')
        self.assertEqual(data['matched_registry_identifier'], '13-1623886')
        self.assertIn('conflicting fiscal periods', data['comments'])
        selected = {'state': 'NM', 'ein': self.ein, 'identifier': self.ein, 'record_name': self.name,
                    'operation': 'detail', 'url': '/source/original', 'captured_at': 1}
        different = {**selected, 'identifier': '139999999', 'url': '/source/unrelated'}
        with patch.object(state_snapshots, 'retain_references', return_value=set()):
            linked = state_snapshots.attach_links(data, [selected, different])
            self.assertEqual(linked['evidence_url'], selected['url'])
            self.assertEqual(state_snapshots.attach_links(data, [different])['evidence_url'], '')
        def mismatch(query):
            fields = evidence(query)
            return dict(fields, ein='139999999') if query['operation'] == 'detail' else fields
        with self.assertRaisesRegex(ValueError, 'detail identity mismatch'):
            m.nm_browser_lookup(org, mismatch)

    def test_wv_initial_get_retry_reserves_time_and_never_retries_redirect(self):
        url = 'https://erls.wvsos.gov/OnlineCharitiesSearch/Search'
        for redirect, attempts, result in [('about:blank', 2, True), ('https://wrong.example', 1, False)]:
            with self.subTest(redirect=redirect):
                response = Mock(status=200)
                page = Mock(url=redirect)
                page.goto.side_effect = [TimeoutError(), response]
                fact = {}
                with patch('deployment.source_visual_adapters.time.monotonic', side_effect=[0, 6]):
                    if result:
                        self.assertIs(wv_open_selected_search(page, url, 16, fact), response)
                        self.assertEqual(fact['initial_navigation_retry'], 1)
                    else:
                        with self.assertRaises(TimeoutError):
                            wv_open_selected_search(page, url, 16, fact)
                self.assertEqual(page.goto.call_count, attempts)
                self.assertEqual([c.args for c in page.goto.call_args_list], [(url,)] * attempts)
                self.assertEqual([c.kwargs['timeout'] for c in page.goto.call_args_list], [6000, 5000][:attempts])

    def test_wv_normal_get_and_deadline_do_not_repeat(self):
        url = 'https://erls.wvsos.gov/OnlineCharitiesSearch/Search'
        page = Mock(url='about:blank')
        with patch('deployment.source_visual_adapters.time.monotonic', return_value=0):
            wv_open_selected_search(page, url, 16, {})
            page.goto.assert_called_once()
            page.reset_mock()
            page.goto.side_effect = TimeoutError()
            with self.assertRaises(TimeoutError):
                wv_open_selected_search(page, url, 9, {})
            page.goto.assert_called_once()

    def test_mi_overlong_dba_reaches_full_legal_name_and_alias_within_original_budget(self):
        label = "AMERICAN LEBANESE SYRIAN ASSOCIATED CHARITIES, INC. DBA ST JUDE CHILDREN'S RESEARCH HOSPITAL"
        org = m.checker.Organization(label, '351044585')
        plan = m.mi_name_fallback_queries(org)
        self.assertEqual(plan[:2], ["AMERICAN LEBANESE SYRIAN ASSOCIATED CHARITIES, INC.",
                                    "ST JUDE CHILDREN'S RESEARCH HOSPITAL"])
        self.assertLessEqual(len(plan), 4)
        self.assertTrue(all(len(value) <= 80 for value in plan))
        unsplittable = m.checker.Organization("Association for " + ("Very Long " * 8) + "Research", '351044585')
        self.assertEqual(m.mi_name_fallback_queries(unsplittable), [])
        plain = m.checker.Organization("Equal Justice Initiative Inc", '631136160')
        self.assertEqual(m.mi_name_fallback_queries(plain)[0], plain.organization_name)

    def test_ga_unnumbered_separate_foundation_does_not_veto_exact_numbered_charity(self):
        name = "American Civil Liberties Union, Inc."
        foundation = "American Civil Liberties Union Foundation, Inc."
        org = m.checker.Organization(name, '133871360')
        from testing.run_il_ga_guardrails import ga_html
        keys = {name:'16686506-034e-4696-b852-45bdb86ec44a',foundation:'09c2a1d2-4aef-4374-95a0-140424020db0'}
        rows = [
            {'name':name,'identifier':'CH004137','location':'','detail_key':keys[name]},
            {'name':foundation,'identifier':'','location':'','detail_key':keys[foundation]},
        ]
        def lookup(query):
            if 'identifier' not in query:
                return {'rows':rows}
            selected = name if query['identifier'] else foundation
            return {'body':ga_html(**{'full_name':selected, 'license_no':query['identifier'],
                                       'status':'Active' if selected==name else 'Expired',
                                       'expiry':'12/02/2026' if selected==name else ''})}
        selected={'name':name,'license_category':'Charity','address_evidence':{'decision':'unavailable'}}
        history={m.normalized_match_name(foundation)}
        self.assertTrue(m.ga_separate_foundation_history(org,[name],selected,history))
        self.assertFalse(m.ga_separate_foundation_history(org,[name,foundation],selected,history))
        with patch.object(m, 'known_names_for_ein', side_effect=lambda ein: ['ACLU'] if ein==org.ein else []), \
             patch.object(m, 'registry_address_evidence', return_value={'decision':'unavailable'}):
            actual = m.il_ga_browser_lookup(org,'GA',lookup)
        self.assertEqual(actual.matched_registry_identifier,'CH004137')
        self.assertIn('separately named',actual.source_note)
        self.assertTrue(actual._cc_license_record['_optional_identity_review'])
        self.assertFalse(m.ga_separate_foundation_history(org,[name],{**selected,'name':foundation},history))
        self.assertFalse(m.ga_separate_foundation_history(org,[name],{**selected,'address_evidence':{'decision':'conflict'}},history))
