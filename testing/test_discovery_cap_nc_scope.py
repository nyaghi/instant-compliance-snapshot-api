"""Discovery selection and mixed NC source-category controls; no live I/O."""
import copy
import time
import unittest
from unittest.mock import patch

import registry_snapshot_server as cc
from testing.run_final_four_source_guardrails import NC, NC_PROFILE


CONSULTANT = {
    'CSL Legal Name': 'Magnuson Corporation', 'display_name': 'Real Estate for Charities',
    'aliases': ['Magnuson Corporation'], 'CSL Type': 'Fund-Raising Consultant',
    'Status': 'Cancelled', 'License': 'SL100586', 'Expiration Date': '3/31/2010',
    'profile_url': 'https://www.sosnc.gov/online_services/search/charities_profile/7922923',
}


class DiscoveryCap(unittest.TestCase):
    def name(self, name, kind='DBA', *, historical=False, sources=('OH',)):
        return {'name': name, 'verified': True, 'historical': historical,
                'evidence': [{'source': source, 'type': kind} for source in sources]}

    def test_small_discoveries_keep_order_and_evidence(self):
        names = [self.name(f'Alias {i}') for i in range(7)]
        self.assertEqual(cc.prioritized_discovery_names('Entered Name', names), names)

    def test_overflow_prioritizes_entered_current_legal_and_corroborated_names(self):
        names = [self.name(f'Campaign {i}') for i in range(28)] + [
            self.name('Former Legal Name', 'Registered name', historical=True),
            self.name('Corroborated Brand', sources=('OH', 'PA', 'VA')),
            self.name('Current Legal Name', 'Legal name'),
            self.name('Entered Name', 'Registered name')]
        before = copy.deepcopy(names)
        selected = cc.prioritized_discovery_names('Entered Name', names)
        self.assertEqual(len(selected), 7)
        self.assertEqual([n['name'] for n in selected[:4]],
                         ['Entered Name', 'Current Legal Name', 'Former Legal Name', 'Corroborated Brand'])
        self.assertEqual(names, before)
        self.assertTrue(all(item in names for item in selected))

    def test_conflicting_names_do_not_displace_supported_names(self):
        names = [self.name(f'Confirmed Name {i}') for i in range(7)]
        conflict = {**self.name('Entered Name', 'Legal name'), 'identity_conflict': True, 'verified': False}
        self.assertNotIn(conflict, cc.prioritized_discovery_names('Entered Name', [conflict, *names]))

    def test_weekly_registered_name_keeps_legal_name_priority(self):
        names = [self.name(f'Campaign {i}', sources=('OH', 'VA')) for i in range(8)]
        legal = self.name('Registered Legal Identity', 'Registered name — weekly data', sources=('OR',))
        self.assertEqual(cc.prioritized_discovery_names('Entered Name', [*names, legal])[0], legal)

    def test_discovery_response_caps_after_merging_and_keeps_source_limitations(self):
        names = [self.name(f'Campaign Name {i}') for i in range(31)] + [self.name('Legal Identity', 'Legal name')]
        def source(state, ein, deadline):
            return {'source': state, 'complete': state != 'HI', 'names': names if state == 'CA' else []}
        with patch.object(cc, 'identity_cached_source_result', return_value=None), \
                patch.object(cc, 'identity_source_result', side_effect=source):
            result = cc.discover_organization_names('Legal Identity', '12-3456789')
        self.assertEqual(len(result['names']), 7)
        self.assertEqual(result['names'][0]['name'], 'Legal Identity')
        self.assertEqual(result['names_omitted'], 25)
        self.assertTrue(result['partial'])
        self.assertEqual(len(result['sources']), 15)

    def test_manual_names_and_generated_variants_have_not_been_capped(self):
        manual = [f'Known Identity {i}' for i in range(10)]
        self.assertEqual(cc.normalize_reviewed_names(manual), manual)
        variants = cc.organization_name_variants('Community Education Institute — CEI', '')
        self.assertIn('Community Education Institute CEI', variants)
        self.assertEqual(cc.licensed_compound_retrieval_names('Community Education Institute — CEI'),
                         ['Community Education Institute', 'CEI'])


class NorthCarolinaScope(unittest.TestCase):
    def payload(self, rows, **changes):
        query = {'state': 'NC', 'operation': 'search', 'name': 'REAL ESTATE'}
        return {'state': 'NC', 'query': query, 'complete': True, 'verification_pending': False,
                'search_mode': 'STARTS_WITH', 'total': len(rows), 'rows': copy.deepcopy(rows), **changes}

    def test_complete_consultant_is_excluded_after_validation(self):
        evidence = self.payload([CONSULTANT])
        self.assertEqual(cc.final_four_clean_evidence(evidence, evidence['query']), evidence)
        self.assertEqual(cc.final_four_search_evidence(evidence, 'NC', evidence['query']), [])

    def test_mixed_grid_keeps_charity_and_exempt_records_in_either_order(self):
        exempt = {**NC, 'CSL Type': 'CSL Exempt Organization', 'License': 'EX123456',
                  'CSL Legal Name': 'Independent Education Foundation'}
        for rows in ([CONSULTANT, NC, exempt], [NC, exempt, CONSULTANT]):
            evidence = self.payload(rows)
            parsed = cc.final_four_search_evidence(evidence, 'NC', evidence['query'])
            self.assertEqual({row['identifier'] for row in parsed}, {NC['License'], 'EX123456'})

    def test_independent_consultant_shape_uses_category_not_organization(self):
        card = {**CONSULTANT, 'CSL Legal Name': 'Independent Consultant Company',
                'display_name': 'Independent Consultant Company', 'aliases': [], 'License': 'SL123456',
                'profile_url': 'https://www.sosnc.gov/online_services/search/charities_profile/1234567'}
        evidence = self.payload([card])
        self.assertEqual(cc.final_four_search_evidence(evidence, 'NC', evidence['query']), [])

    def test_malformed_unknown_and_duplicate_rows_still_fail(self):
        changes = [{'CSL Type': 'Unknown Category'}, {'CSL Type': ''}, {'License': 'EX100586'},
                   {'License': ''}, {'profile_url': 'https://unrelated.invalid/profile/7922923'},
                   {'Status': ''}, {'Expiration Date': ''}, {'Expiration Date': 'not a date'},
                   {'aliases': []}]
        for changed in changes:
            evidence = self.payload([{**CONSULTANT, **changed}])
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                cc.final_four_clean_evidence(evidence, evidence['query'])
        evidence = self.payload([CONSULTANT, CONSULTANT])
        with self.assertRaises(ValueError):
            cc.final_four_clean_evidence(evidence, evidence['query'])
        for field in CONSULTANT:
            if field in {'aliases', 'display_name'}:
                continue
            card = copy.deepcopy(CONSULTANT); del card[field]
            evidence = self.payload([card])
            with self.subTest(missing=field), self.assertRaises(ValueError):
                cc.final_four_clean_evidence(evidence, evidence['query'])

    def test_incomplete_or_miscounted_grid_cannot_prove_absence(self):
        for changes in ({'complete': False}, {'total': 0}, {'verification_pending': True},
                        {'search_mode': 'EXACT_MATCH'}):
            evidence = self.payload([CONSULTANT], **changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                cc.final_four_clean_evidence(evidence, evidence['query'])

    def lookup(self, *, later_positive=False, later_failure=False, mode='standard'):
        name = 'Independent Education Foundation' if later_positive else 'USA Homeownership Foundation — VAREP'
        org = cc.checker.Organization(name, '45-2458485')
        calls = []
        def provider(query):
            calls.append(copy.deepcopy(query))
            if query['operation'] == 'detail':
                return {'query': query, 'complete': True, 'fields': {
                    **NC_PROFILE, 'Name': 'Independent Education Foundation', 'Status': 'Current Active',
                    'Expiration Date': '5/15/2027', 'Extension End Date': ''}}
            if query['name'] == 'Later Full Alias' and later_failure:
                raise TimeoutError('Fixture source became unavailable')
            rows = [CONSULTANT] if query['name'] == 'REAL ESTATE' else []
            if query['name'] == 'Later Full Alias' and later_positive:
                rows = [{**NC, 'CSL Legal Name': 'Independent Education Foundation', 'Status': 'Current Active',
                         'Expiration Date': '5/15/2027', 'Extension End Date': ''}]
            return {'state': 'NC', 'query': query, 'complete': True, 'verification_pending': False,
                    'search_mode': query.get('search_mode', 'STARTS_WITH'), 'rows': rows, 'total': len(rows)}
        aliases = ('Independent Education Foundation',) if mode == 'standard' else ()
        token = cc.REVIEWED_NAME_CONTEXT.set({'452458485': aliases})
        try:
            with patch.object(cc, 'trial_identity', return_value={'origin': 'fixture'}), \
                    patch.object(cc, 'licensed_charity_names', return_value=([name, 'REAL ESTATE', 'Later Full Alias'], [])), \
                    patch.object(cc, 'reconciled_registry_address', return_value={'decision': 'corroborated', 'basis': 'Fixture EIN-linked office'}), \
                    patch.object(cc, 'licensed_charity_street_evidence', return_value={}):
                result = cc.final_four_browser_lookup(org, 'NC', provider, time.monotonic()+10)
                return result, calls
        finally:
            cc.REVIEWED_NAME_CONTEXT.reset(token)

    def test_reported_no_record_case_finishes_remaining_queries_and_audits_exclusion(self):
        result, calls = self.lookup()
        self.assertEqual(result.status, 'Not Registered')
        self.assertTrue(result.success)
        self.assertIn('Later Full Alias', [q.get('name') for q in calls])
        self.assertEqual(result.source_attempts[0]['excluded_non_charity_record']['identifier'], 'SL100586')
        self.assertFalse(any(q['operation'] == 'detail' for q in calls))

    def test_later_charity_can_be_confirmed_after_consultant(self):
        result, calls = self.lookup(later_positive=True)
        self.assertEqual(result.status, 'Current')
        self.assertEqual(result.matched_registry_identifier, NC['License'])

    def test_later_failure_stays_incomplete(self):
        with self.assertRaises(TimeoutError):
            self.lookup(later_failure=True)


if __name__ == '__main__':
    unittest.main()
