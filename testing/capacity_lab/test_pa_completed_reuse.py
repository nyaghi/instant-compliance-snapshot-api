"""Only completed same-lookup evidence may suppress the old duplicate pass."""
import ast,copy,os,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
import registry_snapshot_server as m

class CompletedReuse(unittest.TestCase):
    def setUp(self):
        self.org=m.checker.Organization('Example Relief','123456789')
        self.result=m.checker.StateResult('Example Relief','123456789','PA',m.checker.STATUS_NOT_REGISTERED,'https://www.charities.pa.gov/')
        self.result.success=True;self.result.queries_attempted=['Example Relief']
        self.rows=[{'step':'search','ein':'123456789','name':'','complete':True,'http_status':200,'row_eins':[]},
                   {'step':'search','ein':'','name':'Example Relief','complete':True,'http_status':200,'row_eins':[]}]
        token=m.LAB_LOOKUP_MODE_CONTEXT.set('sales');self.addCleanup(m.LAB_LOOKUP_MODE_CONTEXT.reset,token)
        for p in [patch.object(m,'APP_VERSION','test-performance-lab'),patch.dict(os.environ,{'PUBLIC_BASE_URL':'https://instant-compliance-snapshot-api-hn4v.onrender.com','CE_LAB_PA_COMPLETED_ZERO_REUSE':'1'})]:
            p.start();self.addCleanup(p.stop)

    def test_only_full_guard_proof_skips_duplicate(self):
        self.assertFalse(m.lab_pa_completed_no_match(self.result,self.org))
        result=m.pa_guard_search_completion(self.result,self.org,self.rows)
        self.assertEqual(m.public_status(result),'Not Registered');self.assertTrue(m.lab_pa_completed_no_match(result,self.org))
        self.assertFalse(m.lab_pa_completed_no_match(result,m.checker.Organization('Other Name','123456789')))
        self.assertFalse(m.lab_pa_completed_no_match(result,m.checker.Organization('Example Relief','987654321')))

    def test_partial_failed_mismatched_queries_and_missed_ein_rows_never_skip(self):
        for index,changes in [(0,{'complete':False}),(0,{'ein':'987654321'}),(0,{'row_eins':['123456789']}),(1,{'complete':False}),(1,{'name':'Other Name'}),(1,{'http_status':503}),(1,{'failure':'Network failed'})]:
            with self.subTest(changes=changes):
                result=copy.deepcopy(self.result);rows=copy.deepcopy(self.rows);rows[index].update(changes)
                result._cc_pa_completed_negative=(self.org.organization_name,self.org.ein)
                result=m.pa_guard_search_completion(result,self.org,rows)
                self.assertFalse(m.lab_pa_completed_no_match(result,self.org))
                self.assertIsNone(result._cc_pa_completed_negative)

    def test_standard_wrong_environment_and_disabled_preserve_duplicate(self):
        result=m.pa_guard_search_completion(self.result,self.org,self.rows)
        for mode,version,env in [('standard','x-performance-lab',{}),('sales','staging',{}),('sales','x-performance-lab',{'PUBLIC_BASE_URL':'https://staging.compliance-express.com'}),('sales','x-performance-lab',{'CE_LAB_PA_COMPLETED_ZERO_REUSE':'0'})]:
            token=m.LAB_LOOKUP_MODE_CONTEXT.set(mode)
            try:
                with patch.object(m,'APP_VERSION',version),patch.dict(os.environ,env):self.assertFalse(m.lab_pa_completed_no_match(result,self.org))
            finally:m.LAB_LOOKUP_MODE_CONTEXT.reset(token)

    def test_positive_and_failed_result_cannot_reuse_old_proof(self):
        result=m.pa_guard_search_completion(self.result,self.org,self.rows)
        result.status='Current';self.assertFalse(m.lab_pa_completed_no_match(result,self.org))
        result.status=m.checker.STATUS_NOT_REGISTERED;result.success=False;self.assertFalse(m.lab_pa_completed_no_match(result,self.org))

    def test_all_other_master_behavior_is_unchanged(self):
        from testing.capacity_lab.pa_completed_scope import strip_pa_completed
        from testing.capacity_lab.wa_public_scope import strip_wa_public
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','d85391e:registry_snapshot_server.py'],cwd=root).decode())
        new=ast.parse(Path(m.__file__).read_text(encoding='utf-8'));strip_pa_completed(new)
        # WA's separately tested request allowance and passive trace are the
        # other authorized lab-only change in this release.
        strip_wa_public(old);strip_wa_public(new)
        self.assertEqual(ast.dump(old),ast.dump(new))

if __name__=='__main__':unittest.main()
