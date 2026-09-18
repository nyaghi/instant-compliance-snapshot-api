"""Bound a fragile public source without starving other identity sources."""
import concurrent.futures,io,sys,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class WashingtonQueue(unittest.TestCase):
    def test_slow_wa_response_has_own_budget_and_retains_absolute_deadline(self):
        seen=[]
        def response(request,timeout):
            seen.append((request.full_url,timeout))
            return io.BytesIO(b'[]')
        with patch.object(c.urllib.request,'urlopen',side_effect=response):
            self.assertTrue(c.identity_wa_names('123456789',time.monotonic()+60)['complete'])
            self.assertTrue(c.identity_wa_names('123456789',time.monotonic()+4)['complete'])
            c.identity_fetch('https://example.test/other-source',time.monotonic()+60)
        self.assertEqual(seen[0][1],35.0)
        self.assertGreater(seen[1][1],3.0)
        self.assertLessEqual(seen[1][1],4.0)
        self.assertEqual(seen[2][1],6.0)

    def test_fifteen_distinct_discoveries_keep_every_alias_with_three_wa_requests(self):
        c.IDENTITY_SOURCE_CACHE.clear();lock=threading.Lock();barrier=threading.Barrier(15)
        active=0;maximum=0;calls=[]
        def source(state,ein,deadline):
            nonlocal active,maximum
            if state=='WA':
                with lock:active+=1;maximum=max(maximum,active);calls.append(ein)
                try:time.sleep(.035)
                finally:
                    with lock:active-=1
            return {'source':state,'complete':True,'names':[c.identity_candidate(f'{state} Confirmed Alias {ein}',state,'Registered name','https://example.test')]}
        def one(i):barrier.wait();return c.discover_organization_names(f'Organization {i}',f'12{i:07}')
        with patch.object(c,'IDENTITY_STATES',('WA','CO')),patch.object(c,'identity_source_result',side_effect=source):
            with concurrent.futures.ThreadPoolExecutor(max_workers=15) as pool:results=list(pool.map(one,range(15)))
        self.assertEqual(maximum,3);self.assertEqual(len(set(calls)),15)
        for i,r in enumerate(results):
            self.assertFalse(r['partial']);self.assertEqual(len(r['names']),3)
            self.assertTrue(all(n['name'].endswith(f'12{i:07}') for n in r['names']))
        self.assertIsNot(c.IDENTITY_WA_POOL,c.IDENTITY_SOURCE_POOL)
        self.assertIsNot(c.IDENTITY_WA_POOL,c.IDENTITY_BROWSER_POOL)

    def test_queued_expiry_is_partial_and_frees_admission_for_next_run(self):
        c.IDENTITY_SOURCE_CACHE.clear();release=threading.Event();entered=threading.Barrier(4)
        def occupy():entered.wait();release.wait(2)
        busy=[c.IDENTITY_WA_POOL.submit(occupy) for _ in range(3)];entered.wait()
        def source(state,ein,deadline):return {'source':state,'complete':True,'names':[]}
        try:
            with patch.object(c,'IDENTITY_STATES',('WA',)),patch.object(c,'IDENTITY_DEADLINE_SECONDS',.04),patch.object(c,'identity_source_result',side_effect=source):
                result=c.discover_organization_names('Example','123456789')
            self.assertTrue(result['partial']);wa=next(s for s in result['sources'] if s['source']=='WA')
            self.assertFalse(wa['complete']);self.assertIn('time limit',wa['limitation'])
        finally:
            release.set()
            for f in busy:f.result(timeout=2)
        with patch.object(c,'IDENTITY_STATES',('WA',)),patch.object(c,'identity_source_result',side_effect=source):
            self.assertFalse(c.discover_organization_names('Next Example','987654321')['partial'])

    def test_source_failure_remains_partial_without_starving_other_names(self):
        c.IDENTITY_SOURCE_CACHE.clear()
        def source(state,ein,deadline):
            if state=='WA':raise TimeoutError('Source failed')
            return {'source':state,'complete':True,'names':[c.identity_candidate('Verified Other Name',state,'Registered name','https://example.test')]}
        with patch.object(c,'IDENTITY_STATES',('WA','CO')),patch.object(c,'identity_source_result',side_effect=source):
            result=c.discover_organization_names('Example','123456789')
        self.assertTrue(result['partial']);self.assertEqual(result['names'][0]['name'],'Verified Other Name')
        self.assertFalse(next(s for s in result['sources'] if s['source']=='WA')['complete'])

if __name__=='__main__':unittest.main(verbosity=2)
