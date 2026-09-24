"""Reported mixed-mode failures and unchanged identity/performance boundaries."""
import json, sys, time, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

def filing(ein='941730465'):
    return dict(ein=ein, tax_year_label=2024, period_begin='2024-07-01', period_end='2025-06-30')

class FollowupControls(unittest.TestCase):
    def setUp(self):
        c.TAX_PERIOD_EVIDENCE_CACHE.clear()

    def test_damaged_apostrophe_and_clean_input_have_same_search_variants(self):
        name='Trust for America\u2019s Health'
        damaged=name.encode('utf-8').decode('cp1252')
        self.assertEqual(c.canonical_name_punctuation(damaged), "Trust for America's Health")
        self.assertEqual(c.organization_name_variants(damaged), c.organization_name_variants(name))

    def test_unicode_letters_and_distinct_chapters_are_preserved(self):
        for name in ('S\u00e3o Paulo Foundation', 'Fondation Andr\u00e9', 'Beacon Foundation - Milwaukee'):
            self.assertEqual(c.canonical_name_punctuation(name), name)
        self.assertNotEqual(c.normalized_match_name('Beacon Foundation - Milwaukee'), c.normalized_match_name('Beacon Foundation'))

    def test_maine_literal_and_is_planned_without_discovery(self):
        with patch.object(c, 'known_names_for_ein', return_value=[]):
            for name in ('Foundation for Food & Agriculture Research', 'Foundation for Food and Agriculture Research'):
                queries=c.me_fast_direct_query_variants(c.checker.Organization(name,'471559027'))
                self.assertTrue(any('food and agriculture' in q.lower() for q in queries), queries)
                self.assertTrue(any('food & agriculture' in q.lower() for q in queries), queries)
                self.assertLessEqual(len(queries), c.ME_FAST_DIRECT_CONFIRMATION_MAX_VARIANTS)

    def test_maine_does_not_split_and_into_other_organizations(self):
        with patch.object(c, 'known_names_for_ein', return_value=[]):
            queries=c.me_fast_direct_query_variants(c.checker.Organization('Beacon and Harbor Foundation','123456789'))
        self.assertFalse(any(q.lower() in {'beacon','harbor foundation'} for q in queries))

    def test_partial_discovery_cache_retries_header_without_name_history(self):
        profile={'organization':{'ein':941730465,'latest_object_id':'202601289349303040'}}
        with patch.object(c,'identity_cached_source_result',return_value={'complete':False,'names':[]}), \
             patch.dict(c.PUBLIC_PROFILE_CACHE,{'941730465':profile}), \
             patch.object(c,'identity_source_result',side_effect=AssertionError('must not run discovery')), \
             patch.object(c,'irs_return_header',side_effect=[TimeoutError(),{'filing':filing()}]) as header:
            start=time.monotonic(); evidence=c.irs_period_for_label('941730465',2024,start+14)
        self.assertEqual(evidence['period_end'],'2025-06-30')
        self.assertEqual(header.call_count,2)
        self.assertEqual(header.call_args.args[2],start+14)

    def test_warm_confirmed_period_avoids_extra_requests(self):
        with patch.object(c,'identity_cached_source_result',return_value={'filing':filing()}), patch.object(c,'identity_fetch') as fetch:
            self.assertEqual(c.irs_period_for_label('941730465',2024,time.monotonic()+14)['period_end'],'2025-06-30')
        fetch.assert_not_called()

    def test_failed_read_is_not_calendar_year_evidence(self):
        with patch.object(c,'irs_latest_period',side_effect=TimeoutError()), patch.object(c,'identity_fetch',side_effect=TimeoutError()):
            e=c.irs_period_for_label('941730465',2024,time.monotonic()+14)
        self.assertTrue(e['period_unconfirmed']); self.assertNotIn('period_end',e)
        self.assertNotIn(('941730465',2024),c.TAX_PERIOD_EVIDENCE_CACHE)

    def test_ky_incomplete_period_does_not_become_false_delinquent(self):
        e={'ein':'941730465','tax_year_label':2024,'period_unconfirmed':True}
        with patch.object(c,'load_ky_snapshot_records',return_value=[('123','Earthjustice','2024','')]), \
             patch.object(c,'fiscal_year_end_for_ein',return_value=(6,30)), patch.object(c,'irs_period_for_label',return_value=e):
            result=c.search_ky_strict_snapshot(c.checker.Organization('Earthjustice','941730465'))
        self.assertEqual(result.status,'Unable to Confirm')
        self.assertFalse(getattr(result,'tax_period_evidence',{}).get('period_assumed'))

if __name__=='__main__': unittest.main(verbosity=2)
