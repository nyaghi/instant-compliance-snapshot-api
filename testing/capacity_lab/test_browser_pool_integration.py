"""Worker cleanup ordering/deadline and master routing, with no registry I/O."""
import ast,json
from pathlib import Path
import subprocess
import time
import unittest
import uuid
from unittest.mock import Mock,patch
import registry_snapshot_server as m
from deployment.queue_worker import Supervisor


class PoolIntegrationTests(unittest.TestCase):
    def test_master_default_special_args_and_leased_fallback(self):
        from deployment import browser_pool
        p=Mock();leased=object()
        with patch.dict(m.os.environ,{'CE_LAB_BROWSER_POOL_CONFIG':''}):
            self.assertIs(m.launch_lookup_browser(p,headless=True,args=['required']),p.chromium.launch.return_value)
        p.chromium.launch.assert_called_once_with(headless=True,args=['required'])
        p.reset_mock()
        with patch.dict(m.os.environ,{'CE_LAB_BROWSER_POOL_CONFIG':'fixture'}),patch.object(browser_pool,'leased_browser',return_value=leased):
            self.assertIs(m.launch_lookup_browser(p,headless=True),leased)
        p.chromium.launch.assert_not_called()
        with patch.dict(m.os.environ,{'CE_LAB_BROWSER_POOL_CONFIG':'fixture'}),patch.object(browser_pool,'leased_browser',return_value=None):
            self.assertIs(m.launch_lookup_browser(p,headless=True),p.chromium.launch.return_value)

    def run_supervisor(self,fail_cleanup=False,expired=False,start_failure=False):
        events=[];q=Mock();token=str(uuid.uuid4())
        job={'id':'job','token':token,'state':'NJ','weight':1,'run_seconds':-1 if expired else 5}
        q.claim.side_effect=[job,None];q.heartbeat.return_value={'job'}
        s=Supervisor(q,'fixture-performance-lab',command=['fixture'],env={})
        pool=Mock();s.browser_pool=pool
        def owner(path,*args):Path(path).write_text('{}');return {}
        pool.owner.side_effect=owner
        def release(*args):
            events.append('browser_cleanup')
            self.assertIn('process_stopped',events)
            if fail_cleanup:raise RuntimeError('cleanup unconfirmed')
        pool.release.side_effect=release
        class Tree:
            def __init__(self,command,payload,directory,env):
                if start_failure:
                    events.append('process_stopped');raise RuntimeError('start failed')
                Path(command[-1]).write_text(json.dumps({'status':'Current'}))
            def poll(self):return None
            def stop(self):events.append('process_stopped')
        def complete(*args,**kwargs):
            self.assertEqual(events[:2],['process_stopped','browser_cleanup'])
            events.append('persist');s.stop()
        q.complete_many.side_effect=complete;q.complete.side_effect=complete
        with patch('deployment.queue_worker.ProcessTree',Tree):
            if fail_cleanup:
                with self.assertRaisesRegex(RuntimeError,'cleanup unconfirmed'):s.run()
            else:s.run()
        return q,events

    def test_process_and_browser_cleanup_precede_result_persistence(self):
        q,events=self.run_supervisor()
        self.assertIn('persist',events);q.confirm_worker_stopped.assert_called_once()

    def test_unconfirmed_cleanup_keeps_source_capacity_reserved(self):
        q,events=self.run_supervisor(fail_cleanup=True)
        q.complete_many.assert_not_called();q.complete.assert_not_called();q.confirm_worker_stopped.assert_not_called()

    def test_expired_result_is_not_rescued_by_browser_reuse(self):
        q,events=self.run_supervisor(expired=True)
        completed=q.complete_many.call_args.args[1][0]
        self.assertIsNone(completed[2]);self.assertEqual(completed[3],'TASK_TIME_LIMIT')

    def test_start_failure_cleans_lease_before_releasing_job(self):
        q,events=self.run_supervisor(start_failure=True)
        self.assertEqual(q.complete.call_args.kwargs['error'],'WORKER_START_FAILED')

    def test_every_master_status_matching_date_and_timeout_rule_unchanged(self):
        from testing.capacity_lab.parsing_scope import strip_browser_startup_reuse
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','342b201:registry_snapshot_server.py'],cwd=root).decode('utf-8'))
        new=ast.parse(Path(m.__file__).read_text(encoding='utf-8'));strip_browser_startup_reuse(new)
        self.assertEqual(ast.dump(old),ast.dump(new))

    def test_worker_admission_deadlines_and_existing_queue_rules_unchanged(self):
        from testing.capacity_lab.parsing_scope import strip_browser_pool_worker
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','342b201:deployment/queue_worker.py'],cwd=root).decode('utf-8'))
        new=ast.parse((root/'deployment/queue_worker.py').read_text(encoding='utf-8'))
        strip_browser_pool_worker(new)
        self.assertEqual(ast.dump(old),ast.dump(new))


if __name__=='__main__':unittest.main()
