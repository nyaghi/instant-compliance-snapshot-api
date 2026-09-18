"""Discovery saturation must not starve independent sources or leak identities."""
import concurrent.futures
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c


class CapacityControls(unittest.TestCase):
    def setUp(self):
        c.IDENTITY_SOURCE_CACHE.clear()

    def test_fifteen_discoveries_keep_http_names_when_browsers_are_saturated(self):
        release=threading.Event(); barrier=threading.Barrier(15)
        direct=set((*c.IDENTITY_STATES,'IRS'))-c.IDENTITY_BROWSER_STATES
        def source(state,ein,deadline):
            if state in c.IDENTITY_BROWSER_STATES:
                release.wait(3)
                raise TimeoutError('Simulated blocked browser source')
            return {'source':state,'complete':True,'names':[c.identity_candidate(f'{state} Identity {ein}',state,'Registered name','https://example.test')]}
        def discover(index):
            barrier.wait()
            return c.discover_organization_names(f'Organization {index}',f'12{index:07}')
        with patch.object(c,'identity_source_result',side_effect=source),patch.object(c,'IDENTITY_DEADLINE_SECONDS',.5):
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=15) as pool:
                    results=list(pool.map(discover,range(15)))
                for index,result in enumerate(results):
                    self.assertEqual({s['source'] for s in result['sources'] if s.get('complete')},direct)
                    self.assertEqual(len(result['names']),len(direct))
                    self.assertTrue(all(n['name'].endswith(f'12{index:07}') for n in result['names']))
                    self.assertTrue(result['partial'])
            finally:release.set()
        # Drain only this suite's four blocked workers; no registry calls occur.
        drains=[c.IDENTITY_BROWSER_POOL.submit(lambda:None) for _ in range(4)]
        for f in drains:f.result(timeout=3)

    def test_cached_browser_evidence_does_not_wait_for_browser_admission(self):
        ein='123456789'; value={'source':'MA','complete':True,'names':[c.identity_candidate('Confirmed Name','MA','Registered name','https://example.test')]}
        c.IDENTITY_SOURCE_CACHE[(ein,'MA','live-v2')]=(time.time()+60,value)
        with patch.object(c,'IDENTITY_STATES',('MA',)),patch.object(c,'identity_source_result',return_value={'source':'IRS','complete':True,'names':[]}),patch.object(c.IDENTITY_BROWSER_POOL,'submit',side_effect=AssertionError('Cached evidence queued')):
            result=c.discover_organization_names('Input Name',ein)
        self.assertEqual(result['names'][0]['name'],'Confirmed Name')
        self.assertTrue(next(s for s in result['sources'] if s['source']=='MA')['cache_hit'])
        self.assertIsNone(c.identity_cached_source_result('MA','999999999'))

    def test_expired_cache_is_not_used(self):
        c.IDENTITY_SOURCE_CACHE[('123456789','MA','live-v2')]=(time.time()-1,{'source':'MA','complete':True,'names':[]})
        self.assertIsNone(c.identity_cached_source_result('MA','123456789'))

    def test_browser_pool_and_slots_stay_separate_from_registration(self):
        self.assertIsNot(c.IDENTITY_BROWSER_POOL,c.IDENTITY_SOURCE_POOL)
        self.assertIsNot(c.IDENTITY_BROWSER_SLOTS,c.BROWSER_LOOKUP_SEMAPHORE)
        self.assertEqual(c.IDENTITY_BROWSER_POOL._max_workers,4)


if __name__=='__main__':unittest.main(verbosity=2)
