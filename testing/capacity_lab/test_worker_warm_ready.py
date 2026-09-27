"""Startup readiness cannot spend a customer deadline or leak credentials."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from deployment import queue_worker as w
from deployment.queue_engine import FloridaTrace

VERSION='fixture-performance-lab'

class WarmReadiness(unittest.TestCase):
    def test_warm_before_registering_capacity(self):
        events=[];q=Mock()
        q.register_worker.side_effect=lambda *a:events.append('register')
        def warm(*a):events.append('warm');return {'ready':True}
        with patch.object(w.sys,'platform','linux'),patch.object(w,'warm_task_engine',side_effect=warm):
            supervisor=w.Supervisor(q,VERSION,env={'CE_LAB_WARM_ENGINE':'1'})
        self.assertEqual(events,['warm','register'])
        self.assertTrue(supervisor.warm_ready['ready'])

    def test_failed_warm_never_advertises_capacity(self):
        q=Mock()
        with patch.object(w.sys,'platform','linux'),patch.object(w,'warm_task_engine',side_effect=RuntimeError('unready')):
            with self.assertRaisesRegex(RuntimeError,'unready'):
                w.Supervisor(q,VERSION,env={'CE_LAB_WARM_ENGINE':'1'})
        q.register_worker.assert_not_called()

    def test_custom_test_command_does_not_start_real_engine(self):
        q=Mock()
        with patch.object(w.sys,'platform','linux'),patch.object(w,'warm_task_engine') as warm:
            w.Supervisor(q,VERSION,command=['fixture'],env={'CE_LAB_WARM_ENGINE':'1'})
        warm.assert_not_called();q.register_worker.assert_called_once()

    def test_warmup_has_no_organization_or_secret_and_always_reaps_child(self):
        tree=Mock();tree.poll.return_value=0
        seen={}
        def create(job,output,directory,env,target):
            seen.update(job=job,env=env)
            Path(output).write_text(json.dumps({'version':VERSION,'ready':True,'template_pid':42}))
            return tree
        settings={'CE_LAB_DATABASE_URL':'private','CE_TEST_DATABASE_URL':'private','RENDER_API_KEY':'private',
                  'CE_APP_VERSION':VERSION,'CE_LAB_DURABLE_QUEUE':'1'}
        with patch.object(w,'ForkProcessTree',side_effect=create):
            self.assertTrue(w.warm_task_engine(VERSION,settings)['ready'])
        self.assertEqual(seen['job'],{'version':VERSION})
        self.assertEqual(seen['env'],{'CE_APP_VERSION':VERSION,'CE_LAB_DURABLE_QUEUE':'0'})
        self.assertEqual(settings['CE_LAB_DURABLE_QUEUE'],'1')
        tree.stop.assert_called_once()

    def test_bad_proof_reaps_child_without_success(self):
        tree=Mock();tree.poll.return_value=0
        def create(job,output,*a,**kw):
            Path(output).write_text(json.dumps({'version':'other','ready':True}))
            return tree
        with patch.object(w,'ForkProcessTree',side_effect=create):
            with self.assertRaisesRegex(RuntimeError,'not confirmed'):
                w.warm_task_engine(VERSION,{})
        tree.stop.assert_called_once()

    def test_failure_trace_survives_without_a_completed_result_and_omits_sensitive_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'result.json';trace=FloridaTrace(output.with_suffix('.trace.json'))
            trace.record('request',host='csapp.fdacs.gov',path='/CSPublicApp/CheckACharity/CheckACharity.aspx',
                         method='GET',headers={'secret':'private'},query='private',body='private')
            self.assertFalse(output.exists())
            with patch('builtins.print') as emit:
                w.log_failure_trace({'output':output,'job':{'state':'FL','id':'fixture'}},'TASK_TIME_LIMIT')
            text=emit.call_args.args[0]
            self.assertIn('request',text);self.assertNotIn('private',text)
            self.assertNotIn('headers',text);self.assertNotIn('query',text);self.assertNotIn('body',text)

    def test_trace_io_failure_does_not_change_source_return_or_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            trace=FloridaTrace(Path(folder)/'absent'/'trace.json')
            trace.record('attempt_start')
            self.assertEqual(len(trace.events),1)
            with patch('builtins.print',side_effect=OSError('unavailable')):
                w.log_failure_trace({'output':Path(folder)/'result.json','job':{'state':'FL','id':'fixture'}},'TASK_TIME_LIMIT')

    def test_persisted_trace_is_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'trace.json';trace=FloridaTrace(path)
            for i in range(100):trace.record('request',request_id=i)
            rows=json.loads(path.read_text())
            self.assertEqual(len(rows),64);self.assertEqual(rows[-1]['request_id'],99)

if __name__=='__main__':unittest.main()
