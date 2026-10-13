"""Offline source replays; no live-registry or performance claim."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc
from testing.run_il_ga_guardrails import ga_html, search_row


class Response:
    def __init__(self, text): self.text = text
    def raise_for_status(self): pass


class Controls(unittest.TestCase):
    def setUp(self):
        p = patch.object(cc, 'known_names_for_ein', return_value=[])
        p.start(); self.addCleanup(p.stop)

    def test_ga_literal_retrieval_preserves_apostrophe_within_bound(self):
        for name, literal in [
            ("AMERICAN CHILDREN'S CANCER FOUNDATION, INC.", "AMERICAN CHILDREN'S CANCER FOUNDATION"),
            ("Children's Literacy Foundation, Inc.", "Children's Literacy Foundation"),
            ("Children’s Literacy Foundation, Inc.", "Children’s Literacy Foundation"),
            ('River Conservation Foundation, Inc.', 'River Conservation Foundation'),
        ]:
            with self.subTest(name=name):
                required, generated = cc.licensed_charity_names(cc.checker.Organization(name, '123456789'), literal_name_priority=True)
                self.assertIn(name.replace('’', "'"), required)
                self.assertEqual(generated[0], literal.replace('’', "'"))
                self.assertLessEqual(len(generated), 3 * len(required))

    def ga(self, failure=False):
        name = "AMERICAN CHILDREN'S CANCER FOUNDATION, INC."
        literal = "AMERICAN CHILDREN'S CANCER FOUNDATION"
        queries = []
        def evidence(query):
            queries.append(query)
            if 'identifier' in query:
                return {'body': ga_html(full_name=literal, license_no='CH010904', status='Expired', expiry='2/3/2020')}
            if query['orgName'] == literal:
                if failure: raise TimeoutError('Blocked literal search')
                return {'rows': [search_row(literal, 'CH010904', 'observed-fixture')]}
            return {'rows': []}
        with patch.object(cc, 'reconciled_registry_address', return_value={'decision':'not_available'}):
            return cc.il_ga_browser_lookup(cc.checker.Organization(name, '272258044'), 'GA', evidence), queries

    def test_ga_reported_record_retrieved_without_bypassing_identity(self):
        result, queries = self.ga()
        self.assertNotEqual(cc.public_status(result), 'Not Registered')
        self.assertTrue(any(q.get('identifier') == 'CH010904' for q in queries))
        self.assertEqual(cc.public_status(result), 'Delinquent')

    def test_ga_literal_transport_failure_is_not_negative(self):
        with self.assertRaises(TimeoutError): self.ga(True)

    def test_ga_completed_empty_is_negative(self):
        result = cc.il_ga_browser_lookup(cc.checker.Organization('No Such Charity, Inc.', '123456789'), 'GA', lambda q: {'rows': []})
        self.assertEqual(cc.public_status(result), 'Not Registered')

    def test_ga_priority_does_not_promote_broad_literal_prefixes(self):
        for name in ['Research Data Access and Preservation Association', 'Consumer Advocates for Smoke-free Alternatives Association — CASAA', 'Sexually Abused Children’s Relief Endeavor — SACRED']:
            org = cc.checker.Organization(name, '123456789')
            self.assertEqual(cc.licensed_charity_names(org), cc.licensed_charity_names(org, literal_name_priority=True))

    def sc(self, candidate='', ein='', problem='', original='Animal Sanctuary of St Croix Valley Inc. DBA Home for Life', later=False):
        session = type('Session', (), {'headers': {}})()
        calls = []
        session.get = lambda *a, **kw: Response('<form></form>')
        def post(url, data, **kw):
            if 'ctl00$MainContent$Hidden_CharityID' in data:
                if problem == 'detail': raise TimeoutError('detail failure')
                if problem == 'detail-malformed': return Response('<h1>Verification required</h1>')
                return Response('<div>Public Id: P87071 Status: Expired</div>')
            query = data['ctl00$MainContent$txt_CharitySearchName']; calls.append(query)
            if len(calls) == 1:
                if problem == 'transport': raise TimeoutError('search failure')
                if problem == 'malformed': return Response('<h1>Performing security verification</h1>')
                if candidate: return Response(f'<a href="javascript:CharityInfo(87071)">{candidate}</a>')
            if later and len(calls) == 2:
                return Response('<a href="javascript:CharityInfo(12345)">Home for Life</a>')
            return Response('<div>No Results Found.</div>')
        session.post = post
        with patch.object(cc.curl_requests, 'Session', return_value=session), patch.object(cc, 'sc_detail_filing_ein', return_value=ein):
            result = cc.sc_official_detail_lookup(cc.checker.Organization(original, '411867244'))
        return result, calls

    def test_sc_observed_collision_and_completed_negative(self):
        result, calls = self.sc('Shaduba Home for Life')
        self.assertEqual(cc.public_status(result), 'Not Registered')
        self.assertGreater(len(calls), 1)
        self.assertLessEqual(len(calls), 18)
        self.assertTrue(result._sc_unrelated_alias_excluded)

    def test_sc_completed_collision_negative_cannot_be_overridden_by_browser(self):
        result, _ = self.sc('Shaduba Home for Life')
        org = cc.checker.Organization('Animal Sanctuary of St Croix Valley Inc. DBA Home for Life', '411867244')
        with patch.object(cc, 'search_with_name_variants', side_effect=AssertionError('weaker fallback must not run')):
            actual = cc.search_sc_resilient(Mock(), org, official_checked=True, official_result=result)
        self.assertEqual(cc.public_status(actual), 'Not Registered')

    def fallback(self, official=None, filing_ein='', registry='Shaduba Home for Life'):
        org = cc.checker.Organization('Animal Sanctuary of St Croix Valley Inc. DBA Home for Life', '411867244')
        result = cc.checker.StateResult(org.organization_name, org.ein, 'SC', 'Delinquent', cc.NAME_SEARCH_PREFLIGHT_URLS['SC'],
            raw_status_text='Expired', matched_registry_name=registry, matched_registry_identifier='P87071',success=True)
        with patch.object(cc, 'preflight_name_search_registry',return_value=(True,'',None)), \
             patch.object(cc,'search_with_name_variants',return_value=result), \
             patch.object(cc,'sc_detail_filing_ein',return_value=filing_ein):
            return cc.search_sc_resilient(Mock(),org,official_checked=True,official_result=official)

    def test_sc_incomplete_official_search_never_assigns_unrelated_browser_status(self):
        result = self.fallback()
        self.assertEqual(cc.public_status(result),'Unable to Confirm')
        self.assertFalse(result.success)
        self.assertFalse(result.matched_registry_identifier)

    def test_sc_completed_ordinary_negative_rejects_foreign_browser_override(self):
        negative, _ = self.sc()
        self.assertFalse(negative._sc_unrelated_alias_excluded)
        self.assertEqual(cc.public_status(self.fallback(negative)), 'Not Registered')

    def test_sc_browser_filing_ein_still_wins(self):
        result = self.fallback(filing_ein='411867244')
        self.assertEqual(cc.public_status(result),'Delinquent')
        self.assertEqual(result.identity_anchor,'EIN')

    def test_sc_browser_exact_alias_behavior_preserved(self):
        self.assertEqual(cc.public_status(self.fallback(registry='Home for Life')),'Delinquent')

    def test_sc_independent_foreign_brand_collision(self):
        result, _ = self.sc('Meridian River Shelter', original='Oakland Animal Refuge Inc. DBA River Shelter')
        self.assertEqual(cc.public_status(result), 'Not Registered')

    def test_sc_exact_alias_positive(self):
        result, _ = self.sc('Home for Life')
        self.assertEqual(cc.public_status(result), 'Delinquent')

    def test_sc_matching_filing_ein_wins(self):
        result, _ = self.sc('Shaduba Home for Life', '411867244')
        self.assertEqual(cc.public_status(result), 'Delinquent')
        self.assertEqual(result.verified_registry_ein, '411867244')

    def test_sc_conflicting_filing_ein_excluded(self):
        result, _ = self.sc('Shaduba Home for Life', '999999999')
        self.assertEqual(cc.public_status(result), 'Not Registered')
        self.assertFalse(result.matched_registry_identifier)

    def test_sc_later_valid_record_survives_unrelated_row(self):
        result, _ = self.sc('Shaduba Home for Life', later=True)
        self.assertEqual(cc.public_status(result), 'Delinquent')
        self.assertEqual(result.matched_registry_name, 'Home for Life')

    def test_sc_related_prefix_retains_unconfirmed_identity(self):
        for candidate in ['Chapter Home for Life', 'Affiliate Home for Life', 'Auxiliary Home for Life']:
            with self.subTest(candidate=candidate):
                self.assertFalse(cc.sc_unrelated_alias_prefix('Animal Refuge DBA Home for Life', candidate))
        result, _ = self.sc('Auxiliary Home for Life')
        self.assertEqual(cc.public_status(result), 'Unable to Confirm')

    def test_sc_reviewed_full_name_not_excluded(self):
        token = cc.REVIEWED_NAME_CONTEXT.set({'411867244': ('Shaduba Home for Life',)})
        try:
            with patch.object(cc, 'known_names_for_ein', wraps=lambda ein: list(cc.REVIEWED_NAME_CONTEXT.get().get(ein, ()))):
                self.assertFalse(cc.sc_unrelated_alias_prefix('Animal Refuge DBA Home for Life', 'Shaduba Home for Life', '411867244'))
        finally: cc.REVIEWED_NAME_CONTEXT.reset(token)

    def test_sc_all_incomplete_paths_preserve_fallback(self):
        for problem in ['transport', 'malformed', 'detail', 'detail-malformed']:
            with self.subTest(problem=problem):
                result, _ = self.sc('Shaduba Home for Life', problem=problem)
                self.assertIsNone(result)

    def test_sc_empty_completed_search(self):
        result, _ = self.sc()
        self.assertEqual(cc.public_status(result), 'Not Registered')


if __name__ == '__main__': unittest.main()
