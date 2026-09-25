"""Exact computation reuse: rule parity, alias isolation and source invalidation."""
import concurrent.futures
import socket
import unittest
from unittest.mock import patch
import registry_snapshot_server as m

def blocked(*a,**k):raise AssertionError('Network is disabled in CPU controls')
socket.getaddrinfo=blocked
socket.socket.connect=blocked

class CpuReuseTests(unittest.TestCase):
    def setUp(self):
        self.token=m.REVIEWED_NAME_CONTEXT.set({})
        self.addCleanup(m.REVIEWED_NAME_CONTEXT.reset,self.token)
        m.organization_match_target_variants.cache_clear()

    def test_target_generation_matches_original_for_representative_names(self):
        # Deterministic controls span punctuation, aliases, local chapters,
        # articles, campuses and the original performance hot spot.
        cases=[("Make-A-Wish Foundation of America",['Make-A-Wish','MAWF','MAKE- A- WISH FOUNDATION OF AMERICA']),
            ("America's Charities",['NATIONAL SERVICE AGENCIES','NATIONAL UNITED SERVICE AGENCIES']),
            ('YWCA USA',['National Board of the YWCA of the USA']),
            ('Ronald McDonald House Global / RMHC',['Ronald McDonald House Charities Inc']),
            ('Trust for America\u00e2\u20ac\u2122s Health',["Trust for America's Health"]),
            ('Foundation for Food & Agriculture Research',[]),
            ('Coptic Orphans Support Association',['Coptic Orphans Support Organization']),
            ('University Medical Center - Madison',['University Medical Center']),
            ('End Violence Against Women International (EVAWI)',[]),
            ('Tides Foundation, The',[])]
        for name,aliases in cases:
            m.REVIEWED_NAME_CONTEXT.set({'123456789':tuple(aliases)})
            with self.subTest(name=name):
                self.assertEqual(m.organization_match_target_variants(name,'123456789'),
                                 m.organization_match_target_variants.__wrapped__(name,'123456789'))

    def test_cached_list_cannot_be_mutated_by_caller(self):
        original=m.organization_match_target_variants('Example Foundation')
        altered=m.organization_match_target_variants('Example Foundation')
        altered.append('Unrelated Chapter')
        self.assertEqual(m.organization_match_target_variants('Example Foundation'),original)

    def test_removed_alias_is_not_restored_and_eins_do_not_leak(self):
        name='Primary Foundation'
        m.REVIEWED_NAME_CONTEXT.set({'123456789':('Other Legal Identity',)})
        self.assertIn('Other Legal Identity',m.organization_match_target_variants(name,'123456789'))
        self.assertNotIn('Other Legal Identity',m.organization_match_target_variants(name,'987654321'))
        m.REVIEWED_NAME_CONTEXT.set({'123456789':()})
        self.assertNotIn('Other Legal Identity',m.organization_match_target_variants(name,'123456789'))

    def test_concurrent_same_ein_different_reviewed_aliases_are_isolated(self):
        def one(i):
            aliases=(f'Alternate Legal Identity {i}',)
            token=m.REVIEWED_NAME_CONTEXT.set({'123456789':aliases})
            try:
                for _ in range(10):
                    self.assertEqual(m.organization_match_target_variants('Primary Foundation','123456789'),
                                     m.organization_match_target_variants.__wrapped__('Primary Foundation','123456789'))
            finally:m.REVIEWED_NAME_CONTEXT.reset(token)
        with concurrent.futures.ThreadPoolExecutor(15) as pool:list(pool.map(one,range(30)))

    def test_string_keys_preserve_exact_unicode_and_acronym_decisions(self):
        for value in ['YWCA','Tides Foundation, The','End Violence Against Women International (EVAWI)',
                      "Trust for America\u2019s Health",'Children\u00e2\u20ac\u2122s Health','',None]:
            for f in (m.canonical_name_punctuation,m.complete_name_identity_key,m.redundant_bracket_acronym_key):
                with self.subTest(value=value,f=f.__name__):self.assertEqual(f(value),f.__wrapped__(value))

    def test_kansas_identical_workbook_parsed_once_and_changed_bytes_reparsed(self):
        module=m.load_ks_weekly_checker()
        module.records_from_workbook_bytes.cache_clear()
        data=module.load_embedded_workbook_bytes()
        first=module.records_from_workbook_bytes(data)
        again=module.records_from_workbook_bytes(bytes(bytearray(data)))
        self.assertIs(first,again)
        self.assertEqual(module.records_from_workbook_bytes.cache_info().misses,1)
        # ZIP permits a harmless trailer. Different bytes must miss even if the
        # parsed records are equal, rather than depending on a refresh timestamp.
        changed=module.records_from_workbook_bytes(data+b'\n')
        self.assertEqual(first,changed)
        self.assertEqual(module.records_from_workbook_bytes.cache_info().misses,2)

    def test_kansas_source_metadata_is_not_cached(self):
        module=m.load_ks_weekly_checker()
        with patch.object(module,'SNAPSHOT_SOURCE_URL','https://example.test/new-source'):
            self.assertEqual(module.load_live_records()[1],'https://example.test/new-source')

    def test_all_caches_are_bounded(self):
        for f in (m.organization_match_target_variants,m.canonical_name_punctuation,
                  m.complete_name_identity_key,m.redundant_bracket_acronym_key,
                  m.load_ks_weekly_checker().records_from_workbook_bytes):
            self.assertGreater(f.cache_info().maxsize,0)
            self.assertLessEqual(f.cache_info().maxsize,8192)

if __name__=='__main__':unittest.main(verbosity=2)
