"""Finish negative-name transport without extending Sales or positive lookups."""
import ast,json,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
import registry_snapshot_server as m
from testing.capacity_lab import test_nj_same_lookup as reuse
from testing.capacity_lab import test_nj_public_query as fixture

class NameBudget(unittest.TestCase):
    def setUp(self):
        self.f=reuse.SameLookup();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.addCleanup(self.f.f.doCleanups);self.org=self.f.org
        original=self.f.request
        def request(method,url,**kw):
            if kw.get('json') is not None:kw={**kw,'json':{**kw['json'],'pageSize':10}}
            return original(method,url,**kw)
        self.f.session.request.side_effect=request
        p=patch.object(m,'nj_complete_grid_enabled',return_value=True);p.start();self.addCleanup(p.stop)

    def test_original_clock_allows_completed_negative_plan_after_eighteen_seconds(self):
        self.f.f.advance=3
        with patch.object(m.time,'monotonic',side_effect=lambda:self.f.f.clock[0]):
            r,_=m.search_nj_public_details(self.org)
        self.assertEqual(self.f.f.clock[0],21)
        self.assertEqual(m.public_status(r),'Not Registered');self.assertTrue(r.success)
        self.assertEqual(self.f.queries,[self.org.ein,*reuse.NAMES])

    def test_incomplete_response_after_thirty_seconds_does_not_count_as_zero(self):
        self.f.f.advance=4
        with patch.object(m,'nj_name_fallback_queries',return_value=[*reuse.NAMES,'More Former Names']),patch.object(m.time,'monotonic',side_effect=lambda:self.f.f.clock[0]):
            self.assertIsNone(m.search_nj_public_details(self.org))
            self.assertNotIn('More Former Names',m.nj_same_lookup_zero_queries(self.org))
        self.assertEqual(self.f.f.clock[0],32)

    def test_positive_ein_keeps_eighteen_second_budget(self):
        self.f.answers[self.org.ein]=fixture.DATA;self.f.f.advance=3.1
        with patch.object(m.time,'monotonic',side_effect=lambda:self.f.f.clock[0]):
            self.assertIsNone(m.search_nj_public_details(self.org))
        self.assertAlmostEqual(self.f.f.clock[0],18.6)

    def test_flag_off_preserves_original_negative_budget(self):
        self.f.f.advance=3
        with patch.object(m,'nj_complete_grid_enabled',return_value=False),patch.object(m.time,'monotonic',side_effect=lambda:self.f.f.clock[0]):
            self.assertIsNone(m.search_nj_public_details(self.org))
        self.assertLessEqual(len(self.f.queries),3)

    def test_entire_other_master_and_deadline_code_unchanged(self):
        from testing.capacity_lab.nj_budget_scope import strip_nj_name_budget
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','be53a50:registry_snapshot_server.py'],cwd=root).decode())
        new=ast.parse(Path(m.__file__).read_text(encoding='utf-8'));strip_nj_name_budget(new)
        self.assertEqual(ast.dump(old),ast.dump(new))
        for p in ['deployment/queue_worker.py']:
            self.assertEqual(subprocess.check_output(['git','show','be53a50:'+p],cwd=root).decode().replace('\r\n','\n'),(root/p).read_text())

if __name__=='__main__':unittest.main()
